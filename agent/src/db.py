"""Supabase client for reading projects, discoveries, and chat history."""

from __future__ import annotations

import json
import os
import re

import anthropic
from supabase import create_client, Client


# ---------------------------------------------------------------------------
# Anthropic API key helpers
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}")


def sanitize_key_from_string(s: str) -> str:
    """Redact any Anthropic API keys found in a string."""
    return _KEY_RE.sub("sk-ant-***REDACTED***", s)


def get_anthropic_client(api_key: str | None = None) -> anthropic.AsyncAnthropic:
    """Create an AsyncAnthropic client, using the provided key or falling back to env."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise KeyError("No Anthropic API key provided")
    return anthropic.AsyncAnthropic(api_key=key)


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
        "reasoning": json.dumps(result.reasoning) if isinstance(result.reasoning, dict) else result.reasoning,
        "related_leads": result.related_leads,
        "searches_performed": result.searches_performed,
        "review_status": "pending",
        "agent_log": agent_log,
        "tokens_used": total_tokens,
        "source_count": result.source_count,
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


def list_pending_discoveries() -> list[dict]:
    """List pending discoveries joined with project metadata, sorted by confidence."""
    client = get_client()
    resp = (
        client.table("epc_discoveries")
        .select("*, project:project_id(id, project_name, developer, mw_capacity, state)")
        .eq("review_status", "pending")
        .execute()
    )
    discoveries = resp.data

    # Sort by confidence rank: confirmed first, unknown last
    confidence_rank = {"confirmed": 0, "likely": 1, "possible": 2, "unknown": 3}
    discoveries.sort(key=lambda d: confidence_rank.get(d.get("confidence", "unknown"), 3))
    return discoveries


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
    min_lead_score: int | None = None,
    sort_by: str = "capacity",
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
    if min_lead_score is not None:
        query = query.gte("lead_score", min_lead_score)
    if search:
        query = query.or_(
            f"project_name.ilike.%{search}%,"
            f"developer.ilike.%{search}%,"
            f"queue_id.ilike.%{search}%"
        )

    order_col = "lead_score" if sort_by == "lead_score" else "mw_capacity"
    query = query.order(order_col, desc=True).limit(limit)
    resp = query.execute()
    return resp.data


CONFIDENCE_RANK = {"confirmed": 0, "likely": 1, "possible": 2, "unknown": 3}


def search_projects_with_epc(
    *,
    state: str | None = None,
    cod_year: int | None = None,
    epc_name: str | None = None,
    developer: str | None = None,
    mw_min: float | None = None,
    confidence_min: str | None = None,
    include_pending: bool = True,
    limit: int = 30,
) -> list[dict]:
    """Search projects joined with their latest EPC discovery.

    Two modes:
    - Project-first (default): queries projects table with foreign-key join to
      latest_discovery. Used when epc_name is not provided.
    - EPC-first: queries epc_discoveries filtered by contractor name. Used when
      epc_name is provided.

    Both modes return the same flat dict shape.
    """
    client = get_client()

    if epc_name:
        # ---- Mode 2: EPC-first ----
        query = (
            client.table("epc_discoveries")
            .select(
                "id, epc_contractor, confidence, review_status, source_count, created_at, "
                "project:project_id(id, project_name, developer, mw_capacity, state, expected_cod, fuel_type, epc_company, lead_score)"
            )
            .ilike("epc_contractor", f"%{epc_name}%")
            .neq("review_status", "rejected")
        )
        if confidence_min:
            # confidence_min filtering done post-query
            pass
        query = query.order("created_at", desc=True).limit(limit)
        try:
            resp = query.execute()
            data = resp.data or []
        except Exception:
            return []
        rows = _normalize_epc_first(data)
    else:
        # ---- Mode 1: Project-first ----
        query = client.table("projects").select(
            "id, project_name, developer, mw_capacity, state, expected_cod, fuel_type, epc_company, lead_score, "
            "latest_discovery:epc_discoveries(id, epc_contractor, confidence, review_status, source_count, created_at)"
        )
        if state:
            query = query.eq("state", state.upper())
        if cod_year is not None:
            query = query.gte("expected_cod", f"{cod_year}-01-01").lte("expected_cod", f"{cod_year}-12-31")
        if developer:
            query = query.ilike("developer", f"%{developer}%")
        if mw_min is not None:
            query = query.gte("mw_capacity", mw_min)
        query = query.order("mw_capacity", desc=True).limit(limit)
        try:
            resp = query.execute()
            data = resp.data or []
        except Exception:
            return []
        rows = _normalize_project_first(data)

    # ---- Post-query filters (both modes) ----
    if state and epc_name:
        rows = [r for r in rows if r.get("state", "").upper() == state.upper()]
    if developer and epc_name:
        rows = [r for r in rows if r.get("developer") and developer.lower() in r["developer"].lower()]
    if mw_min is not None and epc_name:
        rows = [r for r in rows if r.get("mw_capacity") is not None and r["mw_capacity"] >= mw_min]
    if cod_year is not None and epc_name:
        year_str = str(cod_year)
        rows = [r for r in rows if r.get("expected_cod") and r["expected_cod"].startswith(year_str)]

    if confidence_min:
        min_rank = CONFIDENCE_RANK.get(confidence_min, 3)
        rows = [
            r for r in rows
            if r.get("confidence") is None  # keep unresearched projects
            or CONFIDENCE_RANK.get(r["confidence"], 3) <= min_rank
        ]

    if not include_pending:
        rows = [r for r in rows if r.get("review_status") != "pending"]

    return rows[:limit]


def _normalize_project_first(data: list[dict]) -> list[dict]:
    """Flatten project rows with nested latest_discovery list."""
    results = []
    for row in data:
        disc_list = row.get("latest_discovery") or []
        # Filter out rejected, sort by newest first
        disc_list = [d for d in disc_list if d.get("review_status") != "rejected"]
        if disc_list:
            disc_list.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        disc = disc_list[0] if disc_list else {}
        results.append({
            "project_id": row["id"],
            "project_name": row.get("project_name"),
            "developer": row.get("developer"),
            "mw_capacity": row.get("mw_capacity"),
            "state": row.get("state"),
            "expected_cod": row.get("expected_cod"),
            "epc_contractor": disc.get("epc_contractor"),
            "confidence": disc.get("confidence"),
            "review_status": disc.get("review_status"),
            "source_count": disc.get("source_count"),
            "discovery_date": disc.get("created_at"),
        })
    return results


def _normalize_epc_first(data: list[dict]) -> list[dict]:
    """Flatten discovery rows with nested project object."""
    results = []
    for row in data:
        proj = row.get("project") or {}
        results.append({
            "project_id": proj.get("id"),
            "project_name": proj.get("project_name"),
            "developer": proj.get("developer"),
            "mw_capacity": proj.get("mw_capacity"),
            "state": proj.get("state"),
            "expected_cod": proj.get("expected_cod"),
            "lead_score": proj.get("lead_score"),
            "epc_contractor": row.get("epc_contractor"),
            "confidence": row.get("confidence"),
            "review_status": row.get("review_status"),
            "source_count": row.get("source_count"),
            "discovery_date": row.get("created_at"),
        })
    return results


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
# Agent memory
# ---------------------------------------------------------------------------

def save_memory(
    memory: str,
    scope: str,
    memory_key: str | None = None,
    importance: int = 5,
    conversation_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Insert or upsert a memory.

    If memory_key is provided, uses an atomic upsert on (memory_key, scope).
    Otherwise inserts a new row.
    """
    client = get_client()
    data = {
        "memory": memory,
        "scope": scope,
        "importance": max(1, min(10, importance)),
        "memory_key": memory_key,
        "conversation_id": conversation_id,
        "project_id": project_id,
    }

    if memory_key:
        # Atomic upsert — no race condition between select + update
        resp = (
            client.table("agent_memory")
            .upsert(data, on_conflict="memory_key,scope")
            .execute()
        )
    else:
        resp = client.table("agent_memory").insert(data).execute()

    return resp.data[0]


def search_memories(
    keyword: str | None = None,
    scope: str | None = None,
    project_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search memories. Uses ilike for keyword matching.
    Ordered by importance DESC, then created_at DESC.
    """
    client = get_client()
    query = client.table("agent_memory").select("id, memory, scope, memory_key, importance, project_id, created_at")

    if keyword:
        query = query.ilike("memory", f"%{keyword}%")
    if scope:
        query = query.eq("scope", scope)
    if project_id:
        query = query.eq("project_id", project_id)

    query = query.order("importance", desc=True).order("created_at", desc=True).limit(limit)
    try:
        resp = query.execute()
        return resp.data
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Research scratchpad
# ---------------------------------------------------------------------------


def upsert_scratch(session_id: str, key: str, value: dict) -> dict:
    """Upsert a scratchpad entry for a research session."""
    client = get_client()
    resp = (
        client.table("research_scratch")
        .upsert(
            {
                "session_id": session_id,
                "key": key,
                "value": value,
                "updated_at": "now()",
            },
            on_conflict="session_id,key",
        )
        .execute()
    )
    return resp.data[0] if resp.data else {}


def read_scratch(session_id: str, key: str | None = None) -> list[dict]:
    """Read scratchpad entries for a research session."""
    client = get_client()
    query = (
        client.table("research_scratch")
        .select("key, value, updated_at")
        .eq("session_id", session_id)
    )
    if key:
        query = query.eq("key", key)
    query = query.order("updated_at")
    resp = query.execute()
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
