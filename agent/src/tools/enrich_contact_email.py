"""Enrich a contact's email address via waterfall of enrichment providers.

Waterfall order:
  1. EnrichmentAPI  (ENRICHMENT_API_KEY)
  2. Apollo         (APOLLO_API_KEY)

Stops at the first provider that returns an email.
Updates the contacts table with email + email_source on success.
"""

from __future__ import annotations

import logging
import os

import httpx
from pydantic import BaseModel, Field

from ._base import validate_uuid
from ..db import get_client

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "enrich_contact_email",
    "description": (
        "Look up the professional email address for a contact using their LinkedIn URL. "
        "Tries EnrichmentAPI first, then Apollo as fallback. "
        "Updates the contacts table with the found email and source. "
        "Use after a contact has been discovered and has a LinkedIn URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_id": {
                "type": "string",
                "description": "Contact UUID from the contacts table.",
            },
            "linkedin_url": {
                "type": "string",
                "description": "LinkedIn profile URL for the contact.",
            },
        },
        "required": ["contact_id", "linkedin_url"],
    },
}


class Input(BaseModel):
    contact_id: str = Field(..., description="Contact UUID")
    linkedin_url: str = Field(..., description="LinkedIn profile URL for lookup")


async def execute(tool_input: dict) -> dict:
    """Run the email enrichment waterfall."""
    contact_id = tool_input.get("contact_id", "")
    linkedin_url = tool_input.get("linkedin_url", "")

    if not validate_uuid(contact_id):
        return {
            "status": "error",
            "error": f"Invalid contact_id: {contact_id!r} is not a valid UUID.",
            "error_category": "validation_error",
        }

    enrichment_api_key = os.environ.get("ENRICHMENT_API_KEY")
    apollo_api_key = os.environ.get("APOLLO_API_KEY")

    if not enrichment_api_key and not apollo_api_key:
        return {
            "status": "error",
            "error": "No email enrichment API keys configured",
            "error_category": "api_key_missing",
        }

    email: str | None = None
    source: str | None = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ---- Provider 1: EnrichmentAPI ----
        if enrichment_api_key:
            try:
                resp = await client.post(
                    "https://api.enrichmentapi.io/v1/email",
                    json={"linkedin_url": linkedin_url},
                    headers={"Authorization": f"Bearer {enrichment_api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                found = data.get("email") or data.get("data", {}).get("email")
                if found:
                    email = found
                    source = "enrichment_api"
            except Exception as exc:
                logger.debug("EnrichmentAPI failed for %s: %s", contact_id, exc)

        # ---- Provider 2: Apollo ----
        if email is None and apollo_api_key:
            try:
                resp = await client.post(
                    "https://api.apollo.io/v1/people/match",
                    json={"linkedin_url": linkedin_url},
                    headers={"x-api-key": apollo_api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                person = data.get("person") or {}
                found = person.get("email") or data.get("email")
                if found:
                    email = found
                    source = "apollo"
            except Exception as exc:
                logger.debug("Apollo failed for %s: %s", contact_id, exc)

    # ---- Update DB if email found ----
    if email:
        try:
            db = get_client()
            db.table("contacts").update(
                {"email": email, "email_source": source}
            ).eq("id", contact_id).execute()
        except Exception as exc:
            logger.warning("DB update failed for contact %s: %s", contact_id, exc)

    return {
        "status": "success",
        "data": {
            "contact_id": contact_id,
            "email": email,
            "source": source,
        },
        "source": "enrichment",
    }
