"""Run contact discovery sub-agent tool.

Launches a focused contact discovery session for an EPC company on a
specific project. Finds people, scores them against the buyer persona,
and enriches top contacts with email/phone.

NOTE: Full sub-agent execution requires the AgentRuntime from the runtime
revamp. For now, this tool returns guidance for the chat agent to use the
individual contact discovery tools directly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Input(BaseModel):
    entity_id: str = Field(..., description="EPC entity UUID")
    project_id: int = Field(..., description="Project ID")


DEFINITION = {
    "name": "run_contact_discovery",
    "description": (
        "Launch a focused contact discovery session for an EPC company on a specific "
        "project. Finds people, scores them against the buyer persona, and enriches "
        "top contacts with email/phone."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "EPC entity UUID"},
            "project_id": {"type": "integer", "description": "Project ID"},
        },
        "required": ["entity_id", "project_id"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Launch contact discovery sub-agent.

    NOTE: Full sub-agent execution requires the AgentRuntime from the
    runtime revamp. For now, returns guidance for the chat agent to
    use the individual contact discovery tools directly.
    """
    entity_id = tool_input.get("entity_id", "")
    project_id = tool_input.get("project_id")

    from ..agents.contact_discovery import CONTACT_DISCOVERY_TOOLS

    return {
        "status": "success",
        "data": {
            "mode": "manual",
            "message": (
                f"Contact discovery sub-agent not yet available (requires runtime revamp). "
                f"Use the individual tools directly: {', '.join(CONTACT_DISCOVERY_TOOLS)}"
            ),
            "entity_id": entity_id,
            "project_id": project_id,
            "available_tools": CONTACT_DISCOVERY_TOOLS,
        },
        "source": "contact_discovery",
    }
