"""Supabase client for reading projects, discoveries, and chat history."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC

import anthropic
from supabase import Client, create_client

logger = logging.getLogger(__name__)

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
    resp = client.table("epc_discoveries").update(data).eq("id", discovery_id).execute()
    return resp.data[0]


def update_project_epc(project_id: str, epc_company: str) -> dict:
    client = get_client()
    resp = (
        client.table("projects").update({"epc_company": epc_company}).eq("id", project_id).execute()
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
        "reasoning": json.dumps(result.reasoning)
        if isinstance(result.reasoning, dict)
        else result.reasoning,
        "related_leads": result.related_leads,
        "searches_performed": result.searches_performed,
        "review_status": "pending",
        "agent_log": agent_log,
        "tokens_used": total_tokens,
        "source_count": result.source_count,
    }
    discovery = insert_discovery(discovery_data)

    # Populate entity_id from entities table (case-insensitive name match)
    epc_name = result.epc_contractor or "Unknown"
    if epc_name and epc_name != "Unknown":
        entity_resp = (
            get_client().table("entities").select("id").ilike("name", epc_name).limit(1).execute()
        )
        if entity_resp.data:
            entity_id = entity_resp.data[0]["id"]
            discovery = update_discovery(discovery["id"], {"entity_id": entity_id})

    # Write-back to knowledge base
    if project:
        try:
            from .knowledge_base import process_discovery_into_kb

            process_discovery_into_kb(project_id, result, project)
        except Exception:
            import logging

            logging.getLogger(__name__).error(
                "KB write-back failed for project %s", project_id, exc_info=True
            )

    return discovery


def list_discoveries() -> list[dict]:
    client = get_client()
    return client.table("epc_discoveries").select("*").order("created_at", desc=True).execute().data


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
            f"project_name.ilike.%{search}%,developer.ilike.%{search}%,queue_id.ilike.%{search}%"
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
                "project:project_id(id, project_name, developer, mw_capacity, "
                "state, expected_cod, fuel_type, epc_company, lead_score)"
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
            "id, project_name, developer, mw_capacity, state, "
            "expected_cod, fuel_type, epc_company, lead_score, "
            "latest_discovery:epc_discoveries("
            "id, epc_contractor, confidence, review_status, "
            "source_count, created_at)"
        )
        if state:
            query = query.eq("state", state.upper())
        if cod_year is not None:
            query = query.gte("expected_cod", f"{cod_year}-01-01").lte(
                "expected_cod", f"{cod_year}-12-31"
            )
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
        rows = [
            r for r in rows if r.get("developer") and developer.lower() in r["developer"].lower()
        ]
    if mw_min is not None and epc_name:
        rows = [r for r in rows if r.get("mw_capacity") is not None and r["mw_capacity"] >= mw_min]
    if cod_year is not None and epc_name:
        year_str = str(cod_year)
        rows = [r for r in rows if r.get("expected_cod") and r["expected_cod"].startswith(year_str)]

    if confidence_min:
        min_rank = CONFIDENCE_RANK.get(confidence_min, 3)
        rows = [
            r
            for r in rows
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
        results.append(
            {
                "project_id": row["id"],
                "project_name": row.get("project_name"),
                "developer": row.get("developer"),
                "mw_capacity": row.get("mw_capacity"),
                "state": row.get("state"),
                "expected_cod": row.get("expected_cod"),
                "lead_score": row.get("lead_score"),
                "epc_contractor": disc.get("epc_contractor"),
                "confidence": disc.get("confidence"),
                "review_status": disc.get("review_status"),
                "source_count": disc.get("source_count"),
                "discovery_date": disc.get("created_at"),
            }
        )
    return results


def _normalize_epc_first(data: list[dict]) -> list[dict]:
    """Flatten discovery rows with nested project object."""
    results = []
    for row in data:
        proj = row.get("project") or {}
        results.append(
            {
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
            }
        )
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
# Contacts
# ---------------------------------------------------------------------------


def store_contacts(entity_id: str, contacts: list[dict]) -> list[dict]:
    """Upsert contacts for an entity. Handles dedup via ON CONFLICT."""
    if not contacts:
        return []
    client = get_client()
    stored = []
    for c in contacts:
        data = {
            "entity_id": entity_id,
            "full_name": c["full_name"],
            "title": c.get("title"),
            "linkedin_url": c.get("linkedin_url"),
            "source_url": c.get("source_url"),
            "source_method": c.get("source_method"),
            "outreach_context": c.get("outreach_context"),
        }
        try:
            resp = (
                client.table("contacts")
                .upsert(data, on_conflict="entity_id,full_name_lower")
                .execute()
            )
            if resp.data:
                stored.append(resp.data[0])
        except Exception as exc:
            exc_str = str(exc).lower()
            if "duplicate" in exc_str or "conflict" in exc_str or "unique" in exc_str:
                logger.debug("Contact already exists: %s", c["full_name"])
            else:
                logger.warning("Failed to upsert contact %s: %s", c["full_name"], exc)
    return stored


def get_contacts_for_entity(entity_id: str) -> list[dict]:
    """Get all contacts for an entity."""
    client = get_client()
    resp = (
        client.table("contacts")
        .select("*")
        .eq("entity_id", entity_id)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data


def get_contacts_for_project(project_id: str) -> list[dict]:
    """Get contacts for the EPC entity associated with a project.

    Joins through epc_discoveries (accepted) → entities → contacts.
    """
    client = get_client()
    # Find accepted EPC discovery for this project
    disc_resp = (
        client.table("epc_discoveries")
        .select("epc_contractor")
        .eq("project_id", project_id)
        .eq("review_status", "accepted")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not disc_resp.data:
        return []

    epc_name = disc_resp.data[0].get("epc_contractor")
    if not epc_name or epc_name == "Unknown":
        return []

    # Find entity
    entity_resp = client.table("entities").select("id").ilike("name", epc_name).limit(1).execute()
    if not entity_resp.data:
        return []

    return get_contacts_for_entity(entity_resp.data[0]["id"])


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
        resp = client.table("agent_memory").upsert(data, on_conflict="memory_key,scope").execute()
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
    query = client.table("agent_memory").select(
        "id, memory, scope, memory_key, importance, project_id, created_at"
    )

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
    data = {
        "session_id": session_id,
        "key": key,
        "value": value,
        "updated_at": "now()",
    }
    resp = client.table("research_scratch").upsert(data, on_conflict="session_id,key").execute()
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


def create_conversation(title: str | None = None, user_id: str | None = None) -> dict:
    client = get_client()
    data = {}
    if title:
        data["title"] = title[:120]
    if user_id:
        data["user_id"] = user_id
    resp = client.table("chat_conversations").insert(data).execute()
    return resp.data[0]


def save_message(
    conversation_id: str,
    role: str,
    content: str,
    parts: list | None = None,
    user_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    iterations: int | None = None,
) -> dict:
    client = get_client()
    # Validate ownership if user_id is provided
    if user_id:
        conv = (
            client.table("chat_conversations")
            .select("user_id")
            .eq("id", conversation_id)
            .maybe_single()
            .execute()
        )
        if not conv.data or conv.data.get("user_id") != user_id:
            raise PermissionError(
                f"Conversation {conversation_id} does not belong to user {user_id}"
            )
    data: dict = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "parts": parts or [],
    }
    if input_tokens is not None:
        data["input_tokens"] = input_tokens
    if output_tokens is not None:
        data["output_tokens"] = output_tokens
    if cache_read_tokens is not None:
        data["cache_read_tokens"] = cache_read_tokens
    if cache_write_tokens is not None:
        data["cache_write_tokens"] = cache_write_tokens
    if iterations is not None:
        data["iterations"] = iterations
    resp = client.table("chat_messages").insert(data).execute()
    return resp.data[0]


def log_chat_event(
    conversation_id: str,
    turn_number: int,
    event_type: str,
    data: dict,
) -> None:
    """Write one event row to chat_events.

    Synchronous (uses existing sync Supabase client).
    Always call via asyncio.create_task(asyncio.to_thread(log_chat_event, ...))
    so it runs in a thread pool and never blocks the event loop.
    Failures are logged and swallowed — never raised to the caller.
    """
    try:
        client = get_client()
        client.table("chat_events").insert(
            {
                "conversation_id": conversation_id,
                "turn_number": turn_number,
                "event_type": event_type,
                "data": data,
            }
        ).execute()
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "chat_event write failed: %s conversation=%s",
            event_type,
            conversation_id,
        )


def get_conversation_messages(conversation_id: str, user_id: str | None = None) -> list[dict]:
    client = get_client()
    if user_id:
        conv = (
            client.table("chat_conversations")
            .select("user_id")
            .eq("id", conversation_id)
            .maybe_single()
            .execute()
        )
        if not conv.data or conv.data.get("user_id") != user_id:
            return []
    return (
        client.table("chat_messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
        .data
    )


def list_conversations(limit: int = 20, user_id: str | None = None) -> list[dict]:
    client = get_client()
    query = client.table("chat_conversations").select("*")
    if user_id:
        query = query.eq("user_id", user_id)
    return query.order("updated_at", desc=True).limit(limit).execute().data


# ---------------------------------------------------------------------------
# Share links (public snapshot of a conversation — see migration 029)
# ---------------------------------------------------------------------------


def _get_conversation_share_row(conversation_id: str) -> dict | None:
    """Return {user_id, share_token, shared_at} for a conversation, or None."""
    client = get_client()
    resp = (
        client.table("chat_conversations")
        .select("user_id, share_token, shared_at")
        .eq("id", conversation_id)
        .maybe_single()
        .execute()
    )
    if resp and resp.data:
        return resp.data
    return None


def get_share_state(conversation_id: str, user_id: str) -> dict | None:
    """Return current share state for a conversation (for owner preview).

    Shape: {"token": str|None, "shared_at": str|None} or None if not owned.
    """
    row = _get_conversation_share_row(conversation_id)
    if not row or row.get("user_id") != user_id:
        return None
    return {"token": row.get("share_token"), "shared_at": row.get("shared_at")}


def set_share_token(
    conversation_id: str,
    user_id: str,
    token: str,
) -> dict | None:
    """Assign a share token + shared_at to a conversation.

    Idempotent: if the conversation already has a share token, returns the
    existing one unchanged (preserves the original snapshot). To regenerate,
    caller must clear_share_token() first.

    Returns {"token": str, "shared_at": str} or None if not owned.
    """
    row = _get_conversation_share_row(conversation_id)
    if not row or row.get("user_id") != user_id:
        return None

    # Already shared — return existing snapshot
    if row.get("share_token"):
        return {"token": row["share_token"], "shared_at": row.get("shared_at")}

    from datetime import datetime

    client = get_client()
    now_iso = datetime.now(UTC).isoformat()
    resp = (
        client.table("chat_conversations")
        .update({"share_token": token, "shared_at": now_iso})
        .eq("id", conversation_id)
        .execute()
    )
    if not resp.data:
        return None
    updated = resp.data[0]
    return {
        "token": updated.get("share_token"),
        "shared_at": updated.get("shared_at"),
    }


def clear_share_token(conversation_id: str, user_id: str) -> bool:
    """Revoke a conversation's share link. Returns True if updated."""
    row = _get_conversation_share_row(conversation_id)
    if not row or row.get("user_id") != user_id:
        return False

    client = get_client()
    resp = (
        client.table("chat_conversations")
        .update({"share_token": None, "shared_at": None})
        .eq("id", conversation_id)
        .execute()
    )
    return bool(resp.data)


def fetch_shared_conversation(token: str) -> dict | None:
    """Fetch a shared conversation snapshot via the SECURITY DEFINER function.

    Returns a dict shaped like:
        {
            "conversation": {"id": ..., "title": ..., "shared_at": ...},
            "messages": [{"id", "role", "content", "parts", "created_at"}, ...]
        }
    or None if the token is invalid / revoked / snapshot is empty.
    """
    if not token:
        return None
    client = get_client()
    resp = client.rpc("get_shared_conversation", {"p_token": token}).execute()
    rows = resp.data or []
    if not rows:
        return None

    first = rows[0]
    conversation = {
        "id": first.get("conversation_id"),
        "title": first.get("title"),
        "shared_at": first.get("shared_at"),
    }
    messages = [
        {
            "id": r.get("message_id"),
            "role": r.get("role"),
            "content": r.get("content", ""),
            "parts": r.get("parts") or [],
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]
    return {"conversation": conversation, "messages": messages}


def log_share_access(
    token: str,
    conversation_id: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> None:
    """Best-effort audit log write. Never raises."""
    try:
        client = get_client()
        client.table("chat_share_access_log").insert(
            {
                "share_token": token,
                "conversation_id": conversation_id,
                "ip_hash": ip_hash,
                "user_agent": user_agent,
            }
        ).execute()
    except Exception:
        logger.warning("share_access_log write failed token=%s", token[:6])
