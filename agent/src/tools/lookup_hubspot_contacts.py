"""Look up existing contacts in HubSpot CRM for a given company.

Searches HubSpot by company name (and optionally domain), retrieves associated
contacts with their deal history and last activity date.  Results are cached
for 1 hour using the shared Supabase-backed cache.

API flow:
  1. Search companies by name (+ domain filter if provided)
  2. If found, fetch associated contacts via CRM associations endpoint
  3. For each contact, fetch full properties + associated deals
  4. Return consistent envelope with status/data/source
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field

from ._base import cache_get, cache_set

logger = logging.getLogger(__name__)

HUBSPOT_API = "https://api.hubapi.com"
_TIMEOUT = 15.0
_CACHE_TTL_HOURS = 1
_TOOL_NAME = "lookup_hubspot_contacts"

# ---------------------------------------------------------------------------
# Pydantic input schema
# ---------------------------------------------------------------------------


class Input(BaseModel):
    company_name: str = Field(..., description="EPC company name to search")
    company_domain: str | None = Field(None, description="Company domain for precise matching")


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

DEFINITION = {
    "name": _TOOL_NAME,
    "description": (
        "Search HubSpot CRM for existing contacts at a given EPC company. "
        "Looks up the company by name (and domain if provided), then returns "
        "all associated contacts with their title, email, phone, last activity "
        "date, and deal history. Use this to check whether a company and its "
        "key contacts are already in CRM before outreach. Results are cached "
        "for 1 hour."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "EPC company name to search in HubSpot.",
            },
            "company_domain": {
                "type": "string",
                "description": "Company domain (e.g. acmesolar.com) for precise matching. Optional.",
            },
        },
        "required": ["company_name"],
    },
}


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


async def execute(tool_input: dict) -> dict:
    """Look up contacts in HubSpot for a company."""
    company_name: str = tool_input.get("company_name", "").strip()
    company_domain: str | None = tool_input.get("company_domain") or None

    # --- API key ---
    from ..hubspot import get_settings
    settings = get_settings()
    if not settings:
        return {
            "status": "error",
            "error": (
                "HubSpot is not connected. Ask the user to configure their "
                "HubSpot Private App token in Settings first."
            ),
            "error_category": "api_error",
        }

    token: str | None = settings.get("api_key")
    if not token:
        return {
            "status": "error",
            "error": "HubSpot token could not be decrypted.",
            "error_category": "api_error",
        }

    # --- Cache check ---
    cache_params = {"company_name": company_name, "company_domain": company_domain}
    cached = cache_get(_TOOL_NAME, cache_params)
    if cached is not None:
        return cached

    # --- HubSpot search ---
    try:
        result = await _fetch_company_contacts(company_name, company_domain, token)
    except Exception as exc:
        logger.exception("HubSpot lookup failed for %s", company_name)
        return {
            "status": "error",
            "error": f"HubSpot API error: {exc}",
            "error_category": "api_error",
        }

    # --- Cache and return ---
    cache_set(_TOOL_NAME, cache_params, result, ttl_hours=_CACHE_TTL_HOURS)
    return result


# ---------------------------------------------------------------------------
# Internal HubSpot helpers
# ---------------------------------------------------------------------------


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _fetch_company_contacts(
    company_name: str,
    company_domain: str | None,
    token: str,
) -> dict:
    """Main HubSpot query: company search → contact associations → details."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # 1. Search for the company
        company_id = await _search_company(client, company_name, company_domain, token)
        if not company_id:
            return {
                "status": "success",
                "data": {
                    "company_found": False,
                    "hubspot_company_id": None,
                    "contacts": [],
                },
                "source": "hubspot",
            }

        # 2. Get associated contact IDs
        contact_ids = await _get_associated_contact_ids(client, company_id, token)

        # 3. Fetch each contact's details + deals
        contacts = []
        for contact_id in contact_ids:
            contact = await _get_contact_with_deals(client, contact_id, token)
            if contact:
                contacts.append(contact)

    return {
        "status": "success",
        "data": {
            "company_found": True,
            "hubspot_company_id": company_id,
            "contacts": contacts,
        },
        "source": "hubspot",
    }


async def _search_company(
    client: httpx.AsyncClient,
    company_name: str,
    company_domain: str | None,
    token: str,
) -> str | None:
    """Search HubSpot companies by name (+ domain). Returns company ID or None."""
    filters = [
        {
            "propertyName": "name",
            "operator": "EQ",
            "value": company_name,
        }
    ]
    if company_domain:
        filters.append({
            "propertyName": "domain",
            "operator": "EQ",
            "value": company_domain,
        })

    payload = {
        "filterGroups": [{"filters": filters}],
        "properties": ["name", "domain"],
        "limit": 1,
    }

    resp = await client.post(
        f"{HUBSPOT_API}/crm/v3/objects/companies/search",
        headers=_headers(token),
        json=payload,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    return None


async def _get_associated_contact_ids(
    client: httpx.AsyncClient,
    company_id: str,
    token: str,
) -> list[str]:
    """Fetch all contact IDs associated with a HubSpot company."""
    resp = await client.get(
        f"{HUBSPOT_API}/crm/v3/objects/companies/{company_id}/associations/contacts",
        headers=_headers(token),
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [r["id"] for r in results]


async def _get_contact_with_deals(
    client: httpx.AsyncClient,
    contact_id: str,
    token: str,
) -> dict | None:
    """Fetch a single contact's properties and associated deals."""
    # Contact properties
    props = "firstname,lastname,jobtitle,email,phone,hs_last_activity_date"
    resp = await client.get(
        f"{HUBSPOT_API}/crm/v3/objects/contacts/{contact_id}",
        headers=_headers(token),
        params={"properties": props},
    )
    resp.raise_for_status()
    contact_data = resp.json()
    p = contact_data.get("properties", {})

    first = p.get("firstname") or ""
    last = p.get("lastname") or ""
    full_name = f"{first} {last}".strip() or None

    # Associated deals
    deals_resp = await client.get(
        f"{HUBSPOT_API}/crm/v3/objects/contacts/{contact_id}/associations/deals",
        headers=_headers(token),
    )
    deals_resp.raise_for_status()
    deal_results = deals_resp.json().get("results", [])
    deals = [
        {
            "hubspot_deal_id": d.get("id"),
            "dealname": d.get("properties", {}).get("dealname"),
            "dealstage": d.get("properties", {}).get("dealstage"),
            "amount": d.get("properties", {}).get("amount"),
        }
        for d in deal_results
    ]

    return {
        "hubspot_contact_id": contact_id,
        "full_name": full_name,
        "title": p.get("jobtitle") or "",
        "email": p.get("email") or "",
        "phone": p.get("phone") or "",
        "last_activity": p.get("hs_last_activity_date") or "",
        "deals": deals,
    }
