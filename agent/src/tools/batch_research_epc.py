"""Batch EPC research tool — research multiple projects in parallel.

Called from chat_agent.py with special-case handling for SSE progress streaming.
The execute() function runs the batch and returns a summary dict; the chat agent
streams per-project progress updates via an injected _progress_callback.
"""

from __future__ import annotations

DEFINITION = {
    "name": "batch_research_epc",
    "description": (
        "Research EPC contractors for multiple projects in parallel. "
        "Use this when the user asks to research 3+ projects at once. "
        "First call search_projects to get project IDs, then pass them here. "
        "Streams real-time progress updates as each project completes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of project IDs to research.",
            },
            "concurrency": {
                "type": "integer",
                "description": "Max concurrent research tasks (default 5, max 10).",
            },
        },
        "required": ["project_ids"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Run batch EPC research on multiple projects.

    The chat agent injects a _progress_callback into tool_input for SSE streaming.
    """
    # Deferred imports to avoid circular import (tools -> batch -> research -> tools)
    from .. import db
    from ..batch import run_batch

    project_ids = tool_input["project_ids"]
    if len(project_ids) > 50:
        return {
            "error": (
                f"Too many projects ({len(project_ids)}). Maximum is 50 per batch. "
                "Narrow your search or split into multiple batches."
            ),
            "results": [],
            "total": 0,
            "completed": 0,
            "errors": 0,
        }
    concurrency = min(tool_input.get("concurrency", 5), 10)

    # Fetch project records
    projects = []
    for pid in project_ids:
        p = db.get_project(pid)
        if p:
            projects.append(p)

    if not projects:
        return {
            "error": "No valid projects found",
            "results": [],
            "total": 0,
            "completed": 0,
            "errors": 0,
        }

    # The chat agent injects this callback for SSE streaming
    progress_callback = tool_input.get("_progress_callback")
    cancel_event = tool_input.get("_cancel_event")

    async def on_progress(update: dict):
        if progress_callback:
            await progress_callback(update)

    batch_results = await run_batch(
        projects, on_progress, concurrency=concurrency, cancel_event=cancel_event
    )

    completed = sum(1 for r in batch_results if r.get("status") == "completed")
    errors = sum(1 for r in batch_results if r.get("status") == "error")

    # Enrich with project names for the frontend BatchProgressCard
    for r in batch_results:
        pid = r.get("project_id")
        proj = next((p for p in projects if p["id"] == pid), None)
        if proj:
            r["project_name"] = proj.get("project_name") or proj.get("queue_id")

    return {
        "results": batch_results,
        "total": len(projects),
        "completed": completed,
        "errors": errors,
    }
