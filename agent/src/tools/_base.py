"""Shared types and helpers for tool modules.

Includes CachedTool — a Supabase-backed cache for structured data source tools.

Cache flow:
  cache_get(tool, key) ──hit──▶ return cached data
    │ miss
    ▼
  (caller fetches from external source)
    │
    ▼
  cache_set(tool, key, data, ttl) ──▶ persisted in tool_cache table
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class ToolDef(TypedDict):
    """Standard tool definition for the Claude API."""

    name: str
    description: str
    input_schema: dict


def validate_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Supabase-backed tool cache
# ---------------------------------------------------------------------------

# In-memory fallback when DB is unreachable
_memory_cache: dict[str, tuple[float, Any]] = {}


def _make_cache_key(tool_name: str, query_params: dict) -> str:
    """Deterministic cache key from tool name + query parameters."""
    raw = json.dumps(query_params, sort_keys=True, default=str)
    h = hashlib.sha256(f"{tool_name}:{raw}".encode()).hexdigest()[:24]
    return f"{tool_name}:{h}"


def cache_get(tool_name: str, query_params: dict) -> Any | None:
    """Check Supabase cache for a hit. Falls back to in-memory on DB error.

    Returns cached data dict if found and not expired, else None.
    """
    key = _make_cache_key(tool_name, query_params)

    try:
        from ..db import get_client
        client = get_client()
        resp = (
            client.table("tool_cache")
            .select("data, expires_at")
            .eq("cache_key", key)
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expires_at > datetime.now(timezone.utc):
                return row["data"]
            # Expired — clean up
            client.table("tool_cache").delete().eq("cache_key", key).execute()
    except Exception:
        logger.debug("Cache DB read failed for %s, checking in-memory", key)
        # Fall back to in-memory
        import time
        if key in _memory_cache:
            cached_at, data = _memory_cache[key]
            if time.time() - cached_at < 3600:  # 1h fallback TTL
                return data

    return None


def cache_set(tool_name: str, query_params: dict, data: Any, ttl_hours: int = 24) -> None:
    """Write to Supabase cache. Falls back to in-memory on DB error."""
    key = _make_cache_key(tool_name, query_params)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    try:
        from ..db import get_client
        client = get_client()
        client.table("tool_cache").upsert({
            "cache_key": key,
            "tool_name": tool_name,
            "data": data,
            "expires_at": expires_at.isoformat(),
        }).execute()
    except Exception:
        logger.debug("Cache DB write failed for %s, using in-memory", key)
        import time
        _memory_cache[key] = (time.time(), data)
