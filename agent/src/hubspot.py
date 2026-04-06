"""HubSpot CRM integration — create Companies, Deals, Contacts.

Uses HubSpot API v3 with Private App token (Fernet-encrypted at rest).
Search-before-create to prevent duplicate companies/contacts.

Push flow:
  push_discovery(project, entity, contacts, token)
    ├── search_company / create_company
    ├── create_deal
    ├── create_contact (×N)
    └── associate all objects
    └── Log each step to hubspot_sync_log
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from .db import get_client

logger = logging.getLogger(__name__)

HUBSPOT_API = "https://api.hubapi.com"
_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Fernet encryption for token storage
# ---------------------------------------------------------------------------

def _get_fernet():
    """Get a Fernet instance using HUBSPOT_ENCRYPTION_KEY env var."""
    from cryptography.fernet import Fernet

    key = os.environ.get("HUBSPOT_ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "HUBSPOT_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Settings management
# ---------------------------------------------------------------------------

def get_settings() -> dict | None:
    """Read HubSpot settings, decrypt token. Returns None if not configured."""
    client = get_client()
    resp = client.table("hubspot_settings").select("*").limit(1).execute()
    if not resp.data:
        return None
    settings = resp.data[0]
    try:
        settings["api_key"] = _decrypt(settings["api_key_encrypted"])
    except Exception as e:
        logger.error("Failed to decrypt HubSpot token: %s", e)
        return None
    return settings


def save_settings(token: str, pipeline_id: str | None = None, deal_stage_id: str | None = None) -> dict:
    """Validate token, encrypt, and save/update settings."""
    # Validate first
    info = validate_token(token)

    encrypted = _encrypt(token)
    client = get_client()

    data = {
        "api_key_encrypted": encrypted,
        "pipeline_id": pipeline_id,
        "deal_stage_id": deal_stage_id,
        "portal_id": str(info.get("portalId", "")),
        "enabled": True,
    }

    # Check if settings row exists
    existing = client.table("hubspot_settings").select("id").limit(1).execute()
    if existing.data:
        resp = client.table("hubspot_settings").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        resp = client.table("hubspot_settings").insert(data).execute()

    return resp.data[0]


def delete_settings() -> None:
    """Remove HubSpot settings (disconnect)."""
    client = get_client()
    client.table("hubspot_settings").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()


# ---------------------------------------------------------------------------
# HubSpot API calls
# ---------------------------------------------------------------------------

def _hs_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def validate_token(token: str) -> dict:
    """Validate a HubSpot Private App token. Returns account info or raises."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            f"{HUBSPOT_API}/account-info/v3/details",
            headers=_hs_headers(token),
        )
        if resp.status_code == 401:
            raise ValueError("Invalid or revoked HubSpot token.")
        resp.raise_for_status()
        return resp.json()


def search_company(name: str, token: str) -> str | None:
    """Search HubSpot for a company by name. Returns hubspot_id or None."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            f"{HUBSPOT_API}/crm/v3/objects/companies/search",
            headers=_hs_headers(token),
            json={
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "name",
                        "operator": "EQ",
                        "value": name,
                    }]
                }],
                "limit": 1,
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["id"]
    return None


def create_company(entity: dict, token: str) -> str:
    """Create a HubSpot Company. Returns hubspot_id."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            f"{HUBSPOT_API}/crm/v3/objects/companies",
            headers=_hs_headers(token),
            json={
                "properties": {
                    "name": entity.get("name", "Unknown"),
                    "industry": "Construction",
                    "description": f"EPC contractor — {', '.join(entity.get('entity_type', []))}",
                },
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]


def create_deal(project: dict, company_hs_id: str, token: str, pipeline_id: str | None = None, deal_stage_id: str | None = None) -> str:
    """Create a HubSpot Deal. Returns hubspot_id."""
    properties = {
        "dealname": f"{project.get('project_name', 'Solar Project')} — {project.get('mw_capacity', '?')}MW",
        "pipeline": pipeline_id or "default",
        "dealstage": deal_stage_id or "appointmentscheduled",
        "description": (
            f"Solar project: {project.get('project_name', '?')}\n"
            f"State: {project.get('state', '?')}\n"
            f"Capacity: {project.get('mw_capacity', '?')}MW\n"
            f"Expected COD: {project.get('expected_cod', '?')}\n"
            f"Developer: {project.get('developer', '?')}"
        ),
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            f"{HUBSPOT_API}/crm/v3/objects/deals",
            headers=_hs_headers(token),
            json={"properties": properties},
        )
        resp.raise_for_status()
        deal_id = resp.json()["id"]

    # Associate deal with company
    _associate("deals", deal_id, "companies", company_hs_id, token)
    return deal_id


def create_contact(contact: dict, company_hs_id: str, token: str) -> str:
    """Create a HubSpot Contact. Returns hubspot_id."""
    name_parts = (contact.get("full_name") or "Unknown").split(" ", 1)
    first = name_parts[0]
    last = name_parts[1] if len(name_parts) > 1 else ""

    properties: dict = {
        "firstname": first,
        "lastname": last,
        "jobtitle": contact.get("title", ""),
    }
    if contact.get("linkedin_url"):
        properties["hs_linkedinid"] = contact["linkedin_url"]

    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            f"{HUBSPOT_API}/crm/v3/objects/contacts",
            headers=_hs_headers(token),
            json={"properties": properties},
        )
        resp.raise_for_status()
        contact_id = resp.json()["id"]

    # Associate contact with company
    _associate("contacts", contact_id, "companies", company_hs_id, token)
    return contact_id


_ASSOCIATION_TYPE_IDS: dict[tuple[str, str], int] = {
    ("deals", "companies"): 342,
    ("contacts", "companies"): 280,
    ("contacts", "deals"): 3,
}


def _associate(from_type: str, from_id: str, to_type: str, to_id: str, token: str) -> None:
    """Create an association between two HubSpot objects."""
    type_id = _ASSOCIATION_TYPE_IDS.get((from_type, to_type))
    if type_id is None:
        logger.error("No association type ID mapped for %s→%s; skipping", from_type, to_type)
        return
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.put(
            f"{HUBSPOT_API}/crm/v4/objects/{from_type}/{from_id}/associations/{to_type}/{to_id}",
            headers=_hs_headers(token),
            json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}],
        )
        # 200 or 201 both fine; log but don't fail on association errors
        if resp.status_code >= 400:
            logger.warning("HubSpot association failed %s→%s: %s", from_type, to_type, resp.text[:200])


# ---------------------------------------------------------------------------
# Push orchestrator
# ---------------------------------------------------------------------------

def push_discovery(
    project: dict,
    entity: dict,
    contacts: list[dict],
    token: str,
    pipeline_id: str | None = None,
    deal_stage_id: str | None = None,
) -> dict:
    """Push a discovery to HubSpot: Company + Deal + Contacts + Associations.

    Logs each step to hubspot_sync_log. On partial failure, continues with
    remaining steps and reports what succeeded.
    """
    db_client = get_client()
    result = {"company": None, "deal": None, "contacts": [], "errors": []}
    now = datetime.now(timezone.utc).isoformat()

    # 1. Company — search before create
    company_hs_id = None
    try:
        # Check sync_log cache first
        existing_sync = db_client.table("hubspot_sync_log").select("hubspot_object_id").eq(
            "entity_id", entity.get("id")
        ).eq("hubspot_object_type", "company").eq("sync_status", "success").limit(1).execute()

        if existing_sync.data:
            company_hs_id = existing_sync.data[0]["hubspot_object_id"]
            result["company"] = {"status": "existing", "hubspot_id": company_hs_id}
        else:
            # Search HubSpot
            company_hs_id = search_company(entity.get("name", ""), token)
            if company_hs_id:
                result["company"] = {"status": "found", "hubspot_id": company_hs_id}
            else:
                company_hs_id = create_company(entity, token)
                result["company"] = {"status": "created", "hubspot_id": company_hs_id}

        # Log success
        db_client.table("hubspot_sync_log").insert({
            "entity_id": entity.get("id"),
            "hubspot_object_type": "company",
            "hubspot_object_id": company_hs_id,
            "sync_status": "success",
            "synced_at": now,
        }).execute()
    except Exception as e:
        error_msg = str(e)[:500]
        result["errors"].append(f"Company: {error_msg}")
        db_client.table("hubspot_sync_log").insert({
            "entity_id": entity.get("id"),
            "hubspot_object_type": "company",
            "sync_status": "error",
            "error_message": error_msg,
            "synced_at": now,
        }).execute()

    if not company_hs_id:
        return result  # Can't create deal/contacts without company

    # 2. Deal
    deal_hs_id = None
    try:
        deal_hs_id = create_deal(project, company_hs_id, token, pipeline_id, deal_stage_id)
        result["deal"] = {"status": "created", "hubspot_id": deal_hs_id}

        db_client.table("hubspot_sync_log").insert({
            "project_id": project.get("id"),
            "entity_id": entity.get("id"),
            "hubspot_object_type": "deal",
            "hubspot_object_id": deal_hs_id,
            "sync_status": "success",
            "synced_at": now,
        }).execute()
    except Exception as e:
        error_msg = str(e)[:500]
        result["errors"].append(f"Deal: {error_msg}")
        db_client.table("hubspot_sync_log").insert({
            "project_id": project.get("id"),
            "hubspot_object_type": "deal",
            "sync_status": "error",
            "error_message": error_msg,
            "synced_at": now,
        }).execute()

    # 3. Contacts
    for contact in contacts:
        try:
            contact_hs_id = create_contact(contact, company_hs_id, token)
            # Associate contact with deal too
            if deal_hs_id:
                _associate("contacts", contact_hs_id, "deals", deal_hs_id, token)

            result["contacts"].append({
                "name": contact.get("full_name"),
                "status": "created",
                "hubspot_id": contact_hs_id,
            })

            db_client.table("hubspot_sync_log").insert({
                "contact_id": contact.get("id"),
                "entity_id": entity.get("id"),
                "hubspot_object_type": "contact",
                "hubspot_object_id": contact_hs_id,
                "sync_status": "success",
                "synced_at": now,
            }).execute()
        except Exception as e:
            error_msg = str(e)[:500]
            result["contacts"].append({
                "name": contact.get("full_name"),
                "status": "error",
                "error": error_msg,
            })
            result["errors"].append(f"Contact {contact.get('full_name')}: {error_msg}")
            try:
                db_client.table("hubspot_sync_log").insert({
                    "contact_id": contact.get("id"),
                    "entity_id": entity.get("id"),
                    "hubspot_object_type": "contact",
                    "sync_status": "error",
                    "error_message": error_msg,
                    "synced_at": now,
                }).execute()
            except Exception:
                pass

    return result
