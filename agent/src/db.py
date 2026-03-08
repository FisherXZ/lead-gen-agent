"""Supabase client for reading projects, discoveries, and chat history."""

from __future__ import annotations

import os

from supabase import create_client, Client


def get_client() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


def get_project(project_id: str) -> dict | None:
    client = get_client()
    resp = client.table("projects").select("*").eq("id", project_id).execute()
    if resp.data:
        return resp.data[0]
    return None


def get_active_discovery(project_id: str) -> dict | None:
    """Get existing non-rejected discovery for a project."""
    client = get_client()
    resp = (
        client.table("epc_discoveries")
        .select("*")
        .eq("project_id", project_id)
        .neq("review_status", "rejected")
        .execute()
    )
    if resp.data:
        return resp.data[0]
    return None


def insert_discovery(data: dict) -> dict:
    client = get_client()
    resp = client.table("epc_discoveries").insert(data).execute()
    return resp.data[0]


def update_discovery(discovery_id: str, data: dict) -> dict:
    client = get_client()
    resp = (
        client.table("epc_discoveries")
        .update(data)
        .eq("id", discovery_id)
        .execute()
    )
    return resp.data[0]


def update_project_epc(project_id: str, epc_company: str) -> dict:
    client = get_client()
    resp = (
        client.table("projects")
        .update({"epc_company": epc_company})
        .eq("id", project_id)
        .execute()
    )
    return resp.data[0]


def reject_pending_discovery(project_id: str) -> None:
    """Reject any existing pending discovery for a project."""
    existing = get_active_discovery(project_id)
    if existing and existing["review_status"] == "pending":
        update_discovery(existing["id"], {"review_status": "rejected"})


def store_discovery(
    project_id: str,
    result,
    agent_log: list[dict],
    total_tokens: int,
    project: dict | None = None,
) -> dict:
    """Store an agent result as a new discovery record.

    Rejects any existing pending discovery first.
    If *project* is provided, also writes to the knowledge base.
    """
    reject_pending_discovery(project_id)

    discovery_data = {
        "project_id": project_id,
        "epc_contractor": result.epc_contractor or "Unknown",
        "confidence": result.confidence,
        "sources": [s.model_dump() for s in result.sources],
        "reasoning": result.reasoning,
        "related_leads": result.related_leads,
        "review_status": "pending",
        "agent_log": agent_log,
        "tokens_used": total_tokens,
    }
    discovery = insert_discovery(discovery_data)

    # Write-back to knowledge base
    if project:
        try:
            from .knowledge_base import process_discovery_into_kb
            process_discovery_into_kb(project_id, result, project)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "KB write-back failed for project %s", project_id, exc_info=True
            )

    return discovery


def list_discoveries() -> list[dict]:
    client = get_client()
    resp = (
        client.table("epc_discoveries")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data


# ---------------------------------------------------------------------------
# Project search
# ---------------------------------------------------------------------------

def search_projects(
    *,
    state: str | None = None,
    iso_region: str | None = None,
    mw_min: float | None = None,
    mw_max: float | None = None,
    developer: str | None = None,
    fuel_type: str | None = None,
    needs_research: bool | None = None,
    has_epc: bool | None = None,
    search: str | None = None,
    cod_min: str | None = "2025-01-01",
    cod_max: str | None = "2028-12-31",
    limit: int = 20,
) -> list[dict]:
    """Dynamic project search with optional filters.

    By default, scopes to projects with expected COD between 2025 and 2028.
    Pass cod_min=None and cod_max=None to disable date filtering.
    """
    client = get_client()
    query = client.table("projects").select("*")

    if cod_min is not None:
        query = query.gte("expected_cod", cod_min)
    if cod_max is not None:
        query = query.lte("expected_cod", cod_max)
    if state:
        query = query.ilike("state", f"%{state}%")
    if iso_region:
        query = query.eq("iso_region", iso_region)
    if mw_min is not None:
        query = query.gte("mw_capacity", mw_min)
    if mw_max is not None:
        query = query.lte("mw_capacity", mw_max)
    if developer:
        query = query.ilike("developer", f"%{developer}%")
    if fuel_type:
        query = query.ilike("fuel_type", f"%{fuel_type}%")
    if has_epc is True:
        query = query.neq("epc_company", None)
    elif has_epc is False:
        query = query.is_("epc_company", "null")
    if needs_research is True:
        query = query.is_("epc_company", "null")
    if search:
        query = query.or_(
            f"project_name.ilike.%{search}%,"
            f"developer.ilike.%{search}%,"
            f"queue_id.ilike.%{search}%"
        )

    query = query.order("mw_capacity", desc=True).limit(limit)
    resp = query.execute()
    return resp.data


def get_discoveries_for_projects(project_ids: list[str]) -> list[dict]:
    """Fetch discoveries for a list of project IDs."""
    if not project_ids:
        return []
    client = get_client()
    resp = (
        client.table("epc_discoveries")
        .select("*")
        .in_("project_id", project_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data


# ---------------------------------------------------------------------------
# Chat conversations
# ---------------------------------------------------------------------------

def create_conversation(title: str | None = None) -> dict:
    client = get_client()
    data = {}
    if title:
        data["title"] = title[:120]
    resp = client.table("chat_conversations").insert(data).execute()
    return resp.data[0]


def save_message(
    conversation_id: str,
    role: str,
    content: str,
    parts: list | None = None,
) -> dict:
    client = get_client()
    resp = (
        client.table("chat_messages")
        .insert({
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "parts": parts or [],
        })
        .execute()
    )
    return resp.data[0]


def get_conversation_messages(conversation_id: str) -> list[dict]:
    client = get_client()
    resp = (
        client.table("chat_messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    return resp.data


def list_conversations(limit: int = 20) -> list[dict]:
    client = get_client()
    resp = (
        client.table("chat_conversations")
        .select("*")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data
