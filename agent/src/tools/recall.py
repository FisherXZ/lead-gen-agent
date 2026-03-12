"""Retrieve relevant memories from persistent storage."""

from __future__ import annotations

DEFINITION = {
    "name": "recall",
    "description": (
        "Retrieve relevant memories from persistent storage. Use at the start "
        "of research to check what's already known, or when a user references "
        "past conversations. Search by keyword, scope, or project."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Search term to match against stored memories.",
            },
            "scope": {
                "type": "string",
                "enum": ["project", "global"],
                "description": "Filter by memory scope.",
            },
            "project_id": {
                "type": "string",
                "description": "Filter memories for a specific project.",
            },
            "limit": {
                "type": "integer",
                "description": "Max memories to return. Default 10.",
                "default": 10,
            },
        },
    },
}


async def execute(tool_input: dict) -> dict:
    from .. import db

    memories = db.search_memories(
        keyword=tool_input.get("keyword"),
        scope=tool_input.get("scope"),
        project_id=tool_input.get("project_id"),
        limit=tool_input.get("limit", 10),
    )
    return {"memories": memories, "count": len(memories)}
