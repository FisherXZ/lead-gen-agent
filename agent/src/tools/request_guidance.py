"""request_guidance tool — pause research and ask the user for direction.

Used by the chat agent when the AI encounters ambiguous evidence,
conflicting sources, or needs user confirmation before continuing.
The frontend renders this as a GuidanceCard component.

NOT available in batch research — only in interactive chat.
"""

from __future__ import annotations

DEFINITION = {
    "name": "request_guidance",
    "description": (
        "Pause research and ask the user for clarification or direction. "
        "Use when you find ambiguous evidence (multiple possible EPCs), "
        "conflicting sources, or need the user to confirm a finding before "
        "continuing. The user will see your question and can respond in chat. "
        "Only available in interactive chat — not in batch research."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status_summary": {
                "type": "string",
                "description": "Brief summary of research progress and what you've found so far.",
            },
            "question": {
                "type": "string",
                "description": "The specific question you need the user to answer.",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of choices for the user to pick from.",
            },
        },
        "required": ["status_summary", "question"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Execute request_guidance — echo input back for frontend rendering.

    The real handling happens in chat_agent.py which streams the question
    to the frontend as a tool-invocation part. The frontend renders it
    with GuidanceCard. The user responds in chat, and the next round of
    the agent loop picks up the response naturally.
    """
    return {
        "status_summary": tool_input.get("status_summary", ""),
        "question": tool_input.get("question", ""),
        "options": tool_input.get("options", []),
        "awaiting_response": True,
    }
