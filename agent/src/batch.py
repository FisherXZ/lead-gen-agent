"""Batch EPC discovery with concurrency control and progress streaming."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

from .research import run_research
from .db import get_active_discovery, store_discovery
from .knowledge_base import build_knowledge_context


async def _research_one(
    project: dict,
    semaphore: asyncio.Semaphore,
    on_progress: Callable[[dict], Awaitable[None]],
) -> dict:
    """Research a single project under semaphore control."""
    project_id = project["id"]
    project_label = project.get("project_name") or project["queue_id"]

    # Skip projects that already have an accepted discovery
    existing = get_active_discovery(project_id)
    if existing and existing["review_status"] == "accepted":
        result = {
            "project_id": project_id,
            "project_name": project_label,
            "status": "skipped",
            "reason": "already_accepted",
        }
        await on_progress(result)
        return result

    async with semaphore:
        await on_progress({
            "project_id": project_id,
            "status": "started",
            "project_name": project_label,
        })

        try:
            knowledge_context = build_knowledge_context(project)
            agent_result, agent_log, total_tokens = await run_research(
                project, knowledge_context
            )
            discovery = store_discovery(
                project_id, agent_result, agent_log, total_tokens,
                project=project,
            )
            result = {
                "project_id": project_id,
                "project_name": project_label,
                "status": "completed",
                "discovery": discovery,
            }
        except Exception:
            result = {
                "project_id": project_id,
                "project_name": project_label,
                "status": "error",
                "error": traceback.format_exc(),
            }

        await on_progress(result)
        return result


async def run_batch(
    projects: list[dict],
    on_progress: Callable[[dict], Awaitable[None]],
    concurrency: int = 10,
) -> list[dict]:
    """Run EPC discovery on multiple projects concurrently.

    Args:
        projects: List of project dicts from DB.
        on_progress: Async callback called for each status update.
        concurrency: Max concurrent agent runs (default 10).

    Returns:
        List of result dicts, one per project.
    """
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        _research_one(project, semaphore, on_progress)
        for project in projects
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Normalize: convert any bare Exception objects to error dicts
    results: list[dict] = []
    for i, r in enumerate(raw_results):
        if isinstance(r, BaseException):
            project_id = projects[i]["id"] if i < len(projects) else "unknown"
            logger.error(
                "Uncaught exception in _research_one for %s: %s",
                project_id, r,
            )
            error_dict = {
                "project_id": project_id,
                "status": "error",
                "error": f"Uncaught exception: {type(r).__name__}: {r}",
            }
            await on_progress(error_dict)
            results.append(error_dict)
        else:
            results.append(r)

    # Batch summary
    completed = sum(1 for r in results if r.get("status") == "completed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")
    logger.info(
        "Batch complete: %d projects — %d completed, %d skipped, %d errors",
        len(results), completed, skipped, errors,
    )

    return results
