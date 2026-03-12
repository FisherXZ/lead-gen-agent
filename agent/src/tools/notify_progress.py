"""One-way progress notification — does NOT pause execution."""

from __future__ import annotations

DEFINITION = {
    "name": "notify_progress",
    "description": (
        "Send a one-way progress update. Does NOT pause execution. "
        "Use for status updates: search started, candidate found, "
        "verifying source, switching strategy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "stage": {
                "type": "string",
                "enum": [
                    "planning",
                    "searching",
                    "reading",
                    "verifying",
                    "analyzing",
                    "switching_strategy",
                ],
            },
            "message": {
                "type": "string",
                "description": "What you're doing now.",
            },
            "detail": {
                "type": "string",
                "description": "Optional extra context.",
            },
        },
        "required": ["stage", "message"],
    },
}


async def execute(tool_input: dict) -> dict:
    return {"status": "noted", **tool_input}
