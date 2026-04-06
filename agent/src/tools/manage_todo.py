"""Agent self-managed task list.

Inspired by Manus's todo.md pattern and Claude Code's TaskCreate/TaskUpdate.
Adapted for our stack: single tool with create/update/read operations,
stored in the existing research_scratch table via Supabase.

The todo list persists across context compaction because it's DB-backed.
The agent can recover its plan by calling read after compaction.
"""

from __future__ import annotations

import logging

from ..db import read_scratch, upsert_scratch

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "manage_todo",
    "description": (
        "Manage your research task list. Create a plan at the start, "
        "check off tasks as you complete them, and review remaining work. "
        "Your todo list persists across context compaction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create", "update", "read"],
                "description": (
                    "create: Set the full task list. "
                    "update: Mark task(s) done or add new tasks. "
                    "read: Get current state."
                ),
            },
            "session_id": {
                "type": "string",
                "description": "Research session identifier (provided in project details).",
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done", "skipped"],
                        },
                        "result_summary": {
                            "type": "string",
                            "description": "Brief note on what was found (when marking done).",
                        },
                    },
                },
                "description": "For create: full task list. For update: tasks to modify (by id).",
            },
        },
        "required": ["operation", "session_id"],
    },
}

_TODO_KEY = "todo"


async def execute(tool_input: dict) -> dict:
    operation = tool_input["operation"]
    session_id = tool_input["session_id"]

    if operation == "create":
        return _create(session_id, tool_input.get("tasks", []))

    if operation == "update":
        return _update(session_id, tool_input.get("tasks", []))

    if operation == "read":
        return _read(session_id)

    return {"error": f"Unknown operation: {operation}"}


def _create(session_id: str, tasks: list[dict]) -> dict:
    ids = [t.get("id") for t in tasks if t.get("id") is not None]
    if len(ids) != len(set(ids)):
        return {"error": "Duplicate task IDs found. Each task must have a unique id."}

    for task in tasks:
        task.setdefault("status", "pending")
        task.setdefault("result_summary", "")

    upsert_scratch(session_id, _TODO_KEY, {"tasks": tasks})
    logger.info("Todo created for session %s: %d tasks", session_id, len(tasks))
    return {"status": "created", "task_count": len(tasks)}


def _update(session_id: str, updates: list[dict]) -> dict:
    existing = read_scratch(session_id, key=_TODO_KEY)
    if not existing:
        return {
            "error": (
                "No todo list exists for this session. "
                "Call manage_todo with operation='create' first."
            )
        }

    current_data = existing[0].get("value", {})
    current_tasks: list[dict] = current_data.get("tasks", [])
    task_map = {t["id"]: t for t in current_tasks if "id" in t}

    updated_ids = []
    added_ids = []

    for update in updates:
        task_id = update.get("id")
        if task_id is None:
            continue

        if task_id in task_map:
            # Update existing task
            for key, value in update.items():
                task_map[task_id][key] = value
            updated_ids.append(task_id)
        else:
            # Add new task
            update.setdefault("status", "pending")
            update.setdefault("result_summary", "")
            current_tasks.append(update)
            task_map[task_id] = update
            added_ids.append(task_id)

    upsert_scratch(session_id, _TODO_KEY, {"tasks": current_tasks})
    return {
        "status": "updated",
        "updated_ids": updated_ids,
        "added_ids": added_ids,
        "total_tasks": len(current_tasks),
    }


def _read(session_id: str) -> dict:
    existing = read_scratch(session_id, key=_TODO_KEY)
    if not existing:
        return {
            "tasks": [],
            "message": "No plan created yet. Call manage_todo with operation='create' to start.",
        }

    current_data = existing[0].get("value", {})
    tasks: list[dict] = current_data.get("tasks", [])

    # Compute summary stats
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    skipped = sum(1 for t in tasks if t.get("status") == "skipped")
    pending = sum(1 for t in tasks if t.get("status") == "pending")
    in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")

    return {
        "tasks": tasks,
        "summary": {
            "total": total,
            "done": done,
            "skipped": skipped,
            "pending": pending,
            "in_progress": in_progress,
            "completion_rate": round(done / total, 2) if total > 0 else 0,
        },
    }
