"""Query the knowledge base for developer/EPC profiles and relationships."""

from __future__ import annotations

from ..knowledge_base import query_knowledge_base

DEFINITION = {
    "name": "query_knowledge_base",
    "description": (
        "Query the knowledge base for information about solar developers, EPC "
        "contractors, and their relationships. Returns entity profiles with known "
        "engagements, research history, and EPC activity by state. Use this when "
        "a user asks 'what do we know about [company]?', 'which EPCs are active "
        "in [state]?', or when you need to check prior knowledge before starting "
        "web research on a project. NOTE: Returns ACCEPTED engagements only. "
        "For pending discoveries, use search_projects_with_epc instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_name": {
                "type": "string",
                "description": (
                    "Company name to look up (developer or EPC). "
                    "Must be the full name — partial match not supported."
                ),
            },
            "state": {
                "type": "string",
                "description": (
                    "Two-letter state abbreviation to find active EPCs (e.g. 'TX', 'CA')."
                ),
            },
        },
    },
}


async def execute(tool_input: dict) -> dict:
    """Query the knowledge base."""
    entity_name = tool_input.get("entity_name")
    state = tool_input.get("state")
    if not entity_name and not state:
        return {"error": "Provide at least one of entity_name or state."}
    result = query_knowledge_base(entity_name=entity_name, state=state)

    # Include entity_id so other tools (find_contacts, push_to_hubspot) can use it
    response: dict = {"knowledge": result}
    if entity_name:
        from ..knowledge_base import resolve_entity

        entity = resolve_entity(entity_name)
        if entity:
            response["entity_id"] = entity["id"]
            response["entity_name"] = entity["name"]
            response["entity_type"] = entity.get("entity_type", [])
    return response
