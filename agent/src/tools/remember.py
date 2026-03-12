"""Store a key fact in persistent memory for use across conversations."""

from __future__ import annotations

DEFINITION = {
    "name": "remember",
    "description": (
        "Store a key fact in persistent memory for use across conversations. "
        "Use this when you learn something important: EPC relationships, "
        "user preferences, company details, research insights. "
        "Memories persist across conversations. Use scope='project' for "
        "project-specific facts and scope='global' for general knowledge. "
        "Use memory_key to update existing memories instead of creating duplicates."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "memory": {
                "type": "string",
                "description": "The fact or insight to remember. Be specific and concise.",
            },
            "scope": {
                "type": "string",
                "enum": ["project", "global"],
                "description": "project = project-specific, global = general knowledge.",
            },
            "memory_key": {
                "type": "string",
                "description": "Optional key for deduplication. Same key+scope = update.",
            },
            "importance": {
                "type": "integer",
                "description": "1 (minor) to 10 (critical). Default 5.",
                "minimum": 1,
                "maximum": 10,
            },
            "project_id": {
                "type": "string",
                "description": "Required when scope is 'project'. Project UUID.",
            },
        },
        "required": ["memory", "scope"],
    },
}


async def execute(tool_input: dict) -> dict:
    from .. import db

    memory = tool_input.get("memory", "").strip()
    scope = tool_input.get("scope", "global")

    if not memory:
        return {"error": "Memory text cannot be empty."}
    if len(memory) > 2000:
        memory = memory[:2000]

    if scope == "project" and not tool_input.get("project_id"):
        return {"error": "project_id is required when scope is 'project'."}

    try:
        result = db.save_memory(
            memory=memory,
            scope=scope,
            memory_key=tool_input.get("memory_key"),
            importance=tool_input.get("importance", 5),
            conversation_id=tool_input.get("_conversation_id"),
            project_id=tool_input.get("project_id"),
        )
    except Exception as e:
        return {"error": f"Failed to save memory: {str(e)}"}
    return {"status": "remembered", "id": result.get("id")}
