"""Batch EPC discovery with concurrency control and progress streaming."""

from __future__ import annotations

import asyncio
import traceback
from typing import Any, Callable, Awaitable

from .agent import run_agent_async
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
            agent_result, agent_log, total_tokens = await run_agent_async(
                project, knowledge_context
            )
            discovery = store_discovery(
                project_id, agent_result, agent_log, total_tokens,
                project=project,
            )
            result = {
                "project_id": project_id,
                "status": "completed",
                "discovery": discovery,
            }
        except Exception:
            result = {
                "project_id": project_id,
                "status": "error",
                "error": traceback.format_exc(),
            }

        await on_progress(result)
        return result


async def run_batch(
    projects: list[dict],
    on_progress: Callable[[dict], Awaitable[None]],
    concurrency: int = 3,
) -> list[dict]:
    """Run EPC discovery on multiple projects concurrently.

    Args:
        projects: List of project dicts from DB.
        on_progress: Async callback called for each status update.
        concurrency: Max concurrent agent runs (default 3).

    Returns:
        List of result dicts, one per project.
    """
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        _research_one(project, semaphore, on_progress)
        for project in projects
    ]
    return await asyncio.gather(*tasks)
