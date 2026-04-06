"""Enrich a contact's phone number via waterfall of enrichment providers.

Waterfall order:
  1. LeadMagic   (LEADMAGIC_API_KEY)
  2. Prospeo     (PROSPEO_API_KEY)
  3. ContactOut  (CONTACTOUT_API_KEY)
  4. PDL         (PDL_API_KEY)

Stops at the first provider that returns a phone number.
Updates the contacts table with phone + phone_source on success.
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
    "name": "enrich_contact_phone",
    "description": (
        "Look up the phone number for a contact using their LinkedIn URL. "
        "Tries LeadMagic, Prospeo, ContactOut, and PDL in order, stopping at "
        "the first provider that returns a result. "
        "Updates the contacts table with the found phone and source."
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


# Each provider entry: (env_var_name, source_label, call_fn)
# call_fn(client, linkedin_url, api_key) -> str | None


async def _call_leadmagic(
    client: httpx.AsyncClient, linkedin_url: str, api_key: str
) -> str | None:
    resp = await client.post(
        "https://api.leadmagic.io/v1/phone",
        json={"linkedin_url": linkedin_url},
        headers={"x-api-key": api_key},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("phone") or data.get("data", {}).get("phone")


async def _call_prospeo(
    client: httpx.AsyncClient, linkedin_url: str, api_key: str
) -> str | None:
    resp = await client.post(
        "https://api.prospeo.io/api/v1/linkedin-phone",
        json={"url": linkedin_url},
        headers={"x-api-key": api_key},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("phone") or data.get("data", {}).get("phone")


async def _call_contactout(
    client: httpx.AsyncClient, linkedin_url: str, api_key: str
) -> str | None:
    resp = await client.post(
        "https://api.contactout.com/v1/people/phone",
        json={"linkedin_url": linkedin_url},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("phone") or data.get("data", {}).get("phone")


async def _call_pdl(
    client: httpx.AsyncClient, linkedin_url: str, api_key: str
) -> str | None:
    resp = await client.post(
        "https://api.peopledatalabs.com/v5/person/enrich",
        json={"profile": linkedin_url},
        headers={"x-api-key": api_key},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    # PDL returns phone_numbers as a list
    phones = data.get("data", {}).get("phone_numbers") or data.get("phone_numbers") or []
    if phones:
        return phones[0]
    return data.get("phone")


_PROVIDERS = [
    ("LEADMAGIC_API_KEY", "leadmagic", _call_leadmagic),
    ("PROSPEO_API_KEY", "prospeo", _call_prospeo),
    ("CONTACTOUT_API_KEY", "contactout", _call_contactout),
    ("PDL_API_KEY", "pdl", _call_pdl),
]


async def execute(tool_input: dict) -> dict:
    """Run the phone enrichment waterfall."""
    inp = Input(**tool_input)

    if not validate_uuid(inp.contact_id):
        return {
            "status": "error",
            "error": f"Invalid contact_id: {inp.contact_id!r} is not a valid UUID.",
            "error_category": "validation_error",
        }

    # Check if any key is configured
    any_key = any(os.environ.get(env_var) for env_var, _, _ in _PROVIDERS)
    if not any_key:
        return {
            "status": "error",
            "error": "No phone enrichment API keys configured",
            "error_category": "api_key_missing",
        }

    phone: str | None = None
    source: str | None = None

    async with httpx.AsyncClient() as client:
        for env_var, provider_name, call_fn in _PROVIDERS:
            api_key = os.environ.get(env_var)
            if not api_key:
                continue
            try:
                result = await call_fn(client, inp.linkedin_url, api_key)
                if result:
                    phone = result
                    source = provider_name
                    break
            except Exception as exc:
                logger.debug("%s failed for %s: %s", provider_name, inp.contact_id, exc)

    # ---- Update DB if phone found ----
    if phone:
        try:
            db = get_client()
            db.table("contacts").update(
                {"phone": phone, "phone_source": source}
            ).eq("id", inp.contact_id).execute()
        except Exception as exc:
            logger.warning("DB update failed for contact %s: %s", inp.contact_id, exc)

    return {
        "status": "success",
        "data": {
            "contact_id": inp.contact_id,
            "phone": phone,
            "source": source,
        },
        "source": "enrichment",
    }
