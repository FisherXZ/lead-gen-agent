"""Batch EPC discovery with concurrency control and progress streaming."""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable

from .db import get_active_discovery, sanitize_key_from_string, store_discovery
from .knowledge_base import build_knowledge_context
from .research import run_research

logger = logging.getLogger(__name__)


async def _research_one(
    project: dict,
    semaphore: asyncio.Semaphore,
    on_progress: Callable[[dict], Awaitable[None]],
    cancel_event: asyncio.Event | None = None,
    api_key: str | None = None,
    shared_findings=None,
) -> dict:
    """Research a single project under semaphore control."""
    project_id = project["id"]
    project_label = project.get("project_name") or project["queue_id"]

    # Check cancellation before doing any work
    if cancel_event and cancel_event.is_set():
        return {
            "project_id": project_id,
            "project_name": project_label,
            "status": "cancelled",
        }

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
        # Check cancellation again after acquiring semaphore
        if cancel_event and cancel_event.is_set():
            return {
                "project_id": project_id,
                "project_name": project_label,
                "status": "cancelled",
            }
        await on_progress(
            {
                "project_id": project_id,
                "status": "started",
                "project_name": project_label,
            }
        )

        try:
            knowledge_context = build_knowledge_context(project)
            agent_result, agent_log, total_tokens = await run_research(
                project, knowledge_context, api_key=api_key,
                shared_findings=shared_findings,
            )
            discovery = store_discovery(
                project_id,
                agent_result,
                agent_log,
                total_tokens,
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
                "error": sanitize_key_from_string(traceback.format_exc()),
            }

        await on_progress(result)
        return result


async def run_batch(
    projects: list[dict],
    on_progress: Callable[[dict], Awaitable[None]],
    concurrency: int = 10,
    cancel_event: asyncio.Event | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Run EPC discovery on multiple projects concurrently.

    Args:
        projects: List of project dicts from DB.
        on_progress: Async callback called for each status update.
        concurrency: Max concurrent agent runs (default 10).
        cancel_event: When set, pending tasks skip instead of starting.
        api_key: Optional user-provided Anthropic API key.

    Returns:
        List of result dicts, one per project.
    """
    from .evidence import EvidenceStore

    # Shared evidence store — propagates findings across sibling research tasks.
    # Project A's discoveries (e.g. "developer X uses EPC Y") immediately benefit
    # project B in the same batch.
    shared_findings = EvidenceStore()

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        _research_one(
            project, semaphore, on_progress, cancel_event,
            api_key=api_key, shared_findings=shared_findings,
        )
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
                project_id,
                r,
            )
            error_dict = {
                "project_id": project_id,
                "status": "error",
                "error": f"Uncaught exception: {type(r).__name__}: {r}",
            }
            try:
                await on_progress(error_dict)
            except Exception:
                logger.warning("Failed to send progress update for %s", project_id)
            results.append(error_dict)
        else:
            results.append(r)

    # Batch summary
    completed = sum(1 for r in results if r.get("status") == "completed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")
    logger.info(
        "Batch complete: %d projects — %d completed, %d skipped, %d errors",
        len(results),
        completed,
        skipped,
        errors,
    )

    return results
