"""Push an EPC discovery to HubSpot CRM.

Creates Company + Deal + Contacts in HubSpot with one call.
Requires HubSpot to be connected (settings configured in /settings).
"""

from __future__ import annotations

import logging

from ._base import validate_uuid

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "push_to_hubspot",
    "description": (
        "Push an EPC discovery to HubSpot CRM. Creates a Company (the EPC), "
        "a Deal (the solar project), and Contacts (discovered leadership) in "
        "HubSpot, with all associations linked. Requires HubSpot to be "
        "connected in Settings. Use after an EPC discovery has been accepted "
        "and contacts have been found."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project ID to push to HubSpot.",
            },
        },
        "required": ["project_id"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Push a discovery to HubSpot."""
    project_id = tool_input.get("project_id", "").strip()

    if not project_id:
        return {"error": "project_id is required."}

    if not validate_uuid(project_id):
        return {"error": f"Invalid project_id: {project_id}"}

    # Check HubSpot settings
    from ..hubspot import get_settings, push_discovery
    settings = get_settings()
    if not settings:
        return {
            "error": "HubSpot is not connected. Ask the user to configure "
            "their HubSpot Private App token in Settings first."
        }

    token = settings.get("api_key")
    if not token:
        return {"error": "HubSpot token could not be decrypted."}

    # Look up project
    from ..db import get_project, get_contacts_for_project
    project = get_project(project_id)
    if not project:
        return {"error": f"Project {project_id} not found."}

    # Find accepted discovery
    from ..db import get_client
    client = get_client()
    disc_resp = (
        client.table("epc_discoveries")
        .select("*")
        .eq("project_id", project_id)
        .eq("review_status", "accepted")
        .limit(1)
        .execute()
    )
    if not disc_resp.data:
        return {"error": "No accepted EPC discovery for this project. Accept a discovery first."}

    discovery = disc_resp.data[0]
    epc_name = discovery.get("epc_contractor")
    if not epc_name or epc_name == "Unknown":
        return {"error": "Discovery has no identified EPC contractor."}

    # Find EPC entity
    from ..knowledge_base import resolve_entity
    entity = resolve_entity(epc_name)
    if not entity:
        return {"error": f"EPC entity '{epc_name}' not found in knowledge base."}

    # Get contacts
    from ..db import get_contacts_for_entity
    contacts = get_contacts_for_entity(entity["id"])

    # Push to HubSpot
    try:
        result = push_discovery(
            project=project,
            entity=entity,
            contacts=contacts,
            token=token,
            pipeline_id=settings.get("pipeline_id"),
            deal_stage_id=settings.get("deal_stage_id"),
        )
    except Exception as exc:
        return {"error": f"HubSpot push failed: {exc}"}

    # Build summary
    summary_parts = []
    if result.get("company"):
        summary_parts.append(f"Company: {result['company'].get('status')} (ID: {result['company'].get('hubspot_id')})")
    if result.get("deal"):
        summary_parts.append(f"Deal: {result['deal'].get('status')} (ID: {result['deal'].get('hubspot_id')})")
    for c in result.get("contacts", []):
        summary_parts.append(f"Contact {c.get('name')}: {c.get('status')}")

    errors = result.get("errors", [])

    return {
        "success": len(errors) == 0,
        "summary": "; ".join(summary_parts),
        "result": result,
        "errors": errors,
        "project_name": project.get("project_name"),
        "epc_name": epc_name,
    }
