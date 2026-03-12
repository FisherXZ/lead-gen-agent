"""Persistent scratchpad for intermediate research findings.

Survives context compaction by writing to Supabase. The agent can
write candidates, dead ends, sources, and assessments, then read
them back if it loses context during long research runs.
"""

from __future__ import annotations

from ..db import read_scratch, upsert_scratch

DEFINITION = {
    "name": "research_scratchpad",
    "description": (
        "Persistent notepad for intermediate research findings. "
        "Survives context compaction. Write candidates, dead ends, "
        "sources, and assessments. Read to recover context after long runs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["write", "read"],
            },
            "session_id": {
                "type": "string",
                "description": "Research session identifier (provided in project details).",
            },
            "key": {
                "type": "string",
                "description": "e.g. 'candidates', 'dead_ends', 'sources_found', 'assessment'",
            },
            "value": {
                "type": "object",
                "description": "Data to write (required for write operation).",
            },
        },
        "required": ["operation", "session_id"],
    },
}


async def execute(tool_input: dict) -> dict:
    operation = tool_input["operation"]
    session_id = tool_input["session_id"]

    if operation == "write":
        key = tool_input.get("key")
        value = tool_input.get("value")
        if not key:
            return {"error": "key is required for write operation"}
        if value is None:
            return {"error": "value is required for write operation"}
        upsert_scratch(session_id, key, value)
        return {"status": "saved", "session_id": session_id, "key": key}

    elif operation == "read":
        key = tool_input.get("key")
        entries = read_scratch(session_id, key=key)
        return {"session_id": session_id, "entries": entries}

    return {"error": f"Unknown operation: {operation}"}
