"""Save a discovered contact to the database.

Upserts into the `contacts` table (dedup on entity_id + lower(full_name))
and optionally links the contact to a project via `project_contacts`.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ._base import validate_uuid
from ..db import get_client

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "save_contact",
    "description": (
        "Persist a discovered contact to the database. "
        "Upserts the contact record (deduped by entity + name) and optionally "
        "links it to a specific project. Use after finding a contact via "
        "search_linkedin, search_exa_people, or other discovery tools."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "EPC entity UUID.",
            },
            "project_id": {
                "type": ["integer", "null"],
                "description": "Project ID to link contact to (optional).",
            },
            "full_name": {
                "type": "string",
                "description": "Contact's full name.",
            },
            "title": {
                "type": ["string", "null"],
                "description": "Job title.",
            },
            "linkedin_url": {
                "type": ["string", "null"],
            },
            "linkedin_headline": {
                "type": ["string", "null"],
            },
            "linkedin_location": {
                "type": ["string", "null"],
            },
            "linkedin_experience": {
                "type": ["array", "null"],
                "items": {"type": "object"},
                "description": "Work history from Apify.",
            },
            "source_method": {
                "type": "string",
                "description": "How found: 'linkedin', 'hubspot', 'exa', 'epc_website', 'osha', 'web_search'.",
            },
            "source_url": {
                "type": ["string", "null"],
            },
            "hubspot_contact_id": {
                "type": ["string", "null"],
            },
            "relevance_note": {
                "type": ["string", "null"],
                "description": "Why this contact is relevant to the project.",
            },
        },
        "required": ["entity_id", "full_name", "source_method"],
    },
}


class Input(BaseModel):
    entity_id: str = Field(..., description="EPC entity UUID")
    project_id: int | None = Field(None, description="Project ID to link contact to")
    full_name: str = Field(..., description="Contact's full name")
    title: str | None = Field(None, description="Job title")
    linkedin_url: str | None = Field(None)
    linkedin_headline: str | None = Field(None)
    linkedin_location: str | None = Field(None)
    linkedin_experience: list[dict] | None = Field(None, description="Work history from Apify")
    source_method: str = Field(..., description="How found: 'linkedin', 'hubspot', 'exa', 'epc_website', 'osha', 'web_search'")
    source_url: str | None = Field(None)
    hubspot_contact_id: str | None = Field(None)
    relevance_note: str | None = Field(None, description="Why this contact is relevant to the project")


async def execute(tool_input: dict) -> dict:
    """Upsert a contact and optionally link it to a project."""
    entity_id = tool_input.get("entity_id", "")
    full_name = tool_input.get("full_name", "")

    if not validate_uuid(entity_id):
        return {"error": f"Invalid entity_id: {entity_id!r}. Must be a valid UUID."}

    client = get_client()

    # Build contact upsert payload — only include columns the table has
    contact_data: dict[str, Any] = {
        "entity_id": entity_id,
        "full_name": full_name,
        "title": tool_input.get("title"),
        "linkedin_url": tool_input.get("linkedin_url"),
        "linkedin_headline": tool_input.get("linkedin_headline"),
        "linkedin_location": tool_input.get("linkedin_location"),
        "linkedin_experience": tool_input.get("linkedin_experience"),
        "source_method": tool_input.get("source_method"),
        "source_url": tool_input.get("source_url"),
        "hubspot_contact_id": tool_input.get("hubspot_contact_id"),
    }
    # Remove None values so Supabase doesn't overwrite existing data on conflict
    contact_data = {k: v for k, v in contact_data.items() if v is not None}
    # entity_id and full_name must always be present even if empty string
    contact_data["entity_id"] = entity_id
    contact_data["full_name"] = full_name

    try:
        resp = (
            client.table("contacts")
            .upsert(contact_data, on_conflict="entity_id,lower(full_name)")
            .execute()
        )
        contact_row = resp.data[0] if resp.data else {}
        contact_id = contact_row.get("id")
        # Determine if this was a fresh insert vs. update:
        # Supabase upsert always returns the row; we can't distinguish easily,
        # so we treat it as "created" if the row was returned with an id.
        created = bool(contact_id)
    except Exception as exc:
        logger.error("Failed to upsert contact %r: %s", full_name, exc)
        return {"error": f"Database error upserting contact: {exc}"}

    # Optionally link to project
    project_linked = False
    project_id = tool_input.get("project_id")
    if project_id is not None and contact_id:
        try:
            pc_data: dict[str, Any] = {
                "project_id": project_id,
                "contact_id": contact_id,
            }
            relevance_note = tool_input.get("relevance_note")
            if relevance_note:
                pc_data["relevance_note"] = relevance_note
            # Use discovered_via to record source_method if available
            source_method = tool_input.get("source_method")
            if source_method:
                pc_data["discovered_via"] = source_method

            client.table("project_contacts").upsert(
                pc_data, on_conflict="project_id,contact_id"
            ).execute()
            project_linked = True
        except Exception as exc:
            logger.warning(
                "Contact %s saved but project link failed (project_id=%s): %s",
                contact_id,
                project_id,
                exc,
            )

    return {
        "status": "success",
        "data": {
            "contact_id": contact_id,
            "created": created,
            "project_linked": project_linked,
        },
        "source": "database",
    }
