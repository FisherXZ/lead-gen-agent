"""Find leadership contacts at an EPC company.

Thin tool wrapper over contact_discovery.discover_contacts().
Checks for cached contacts (30-day TTL) before running the agent.
"""

from __future__ import annotations

import logging

from ._base import cache_get, cache_set, validate_uuid

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 720  # 30 days

DEFINITION = {
    "name": "find_contacts",
    "description": (
        "Find leadership contacts at an EPC company for sales outreach. "
        "Searches the web, company websites, and SEC filings to find "
        "VP/Director-level people in procurement, construction, and solar "
        "divisions. Returns names, titles, and LinkedIn URLs. Use after "
        "an EPC has been identified for a project. Results are cached for "
        "30 days per company."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": (
                    "Entity ID of the EPC company (from query_knowledge_base "
                    "or search_projects_with_epc results)."
                ),
            },
            "entity_name": {
                "type": "string",
                "description": (
                    "Name of the EPC company (e.g., 'McCarthy Building Companies'). "
                    "Used for web searches."
                ),
            },
        },
        "required": ["entity_id", "entity_name"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Find contacts at an EPC company."""
    entity_id = str(tool_input.get("entity_id") or "").strip()
    entity_name = str(tool_input.get("entity_name") or "").strip()

    if not entity_id or not entity_name:
        return {"error": "Both entity_id and entity_name are required."}

    if not validate_uuid(entity_id):
        return {"error": f"Invalid entity_id: {entity_id}"}

    # Check cache
    cache_params = {"entity_id": entity_id}
    cached = cache_get("find_contacts", cache_params)
    if cached is not None:
        return {"contacts": cached, "cached": True, "entity_name": entity_name}

    # Check if contacts already exist in DB
    from ..db import get_contacts_for_entity
    existing = get_contacts_for_entity(entity_id)
    if existing:
        cache_set("find_contacts", cache_params, existing, ttl_hours=_CACHE_TTL_HOURS)
        return {"contacts": existing, "cached": True, "entity_name": entity_name}

    # Run contact discovery agent
    from ..contact_discovery import discover_contacts
    try:
        contacts = await discover_contacts(entity_id, entity_name)
    except Exception as exc:
        return {"error": f"Contact discovery failed: {exc}"}

    if contacts:
        cache_set("find_contacts", cache_params, contacts, ttl_hours=_CACHE_TTL_HOURS)

    return {
        "contacts": contacts,
        "cached": False,
        "entity_name": entity_name,
        "count": len(contacts),
    }
