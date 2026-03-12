"""Look up existing EPC discovery results."""

from __future__ import annotations

from ._base import validate_uuid
from .. import db

DEFINITION = {
    "name": "get_discoveries",
    "description": (
        "Look up raw EPC discovery details from previous research runs. "
        "Returns full discovery records including EPC contractor, confidence level, "
        "sources, reasoning, agent log, and review status. Use this when a user "
        "wants to see detailed research evidence, source URLs, or reasoning for a "
        "specific discovery. For a summary view of projects with their EPC status, "
        "use search_projects_with_epc instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of project UUIDs to filter by. Omit to return all discoveries.",
            },
        },
    },
}


async def execute(tool_input: dict) -> dict:
    """Fetch discoveries, optionally filtered by project IDs."""
    project_ids = tool_input.get("project_ids")
    if project_ids:
        invalid = [pid for pid in project_ids if not validate_uuid(pid)]
        if invalid:
            return {"error": f"Invalid project IDs: {invalid}"}
        discoveries = db.get_discoveries_for_projects(project_ids)
    else:
        discoveries = db.list_discoveries()
    return {"discoveries": discoveries, "count": len(discoveries)}
