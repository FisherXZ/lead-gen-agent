"""Exa people search tool — AI-powered natural language search for finding contacts.

Uses the Exa API (neural search) to find web pages mentioning people at target
companies. Ideal for discovering project managers, VPs of construction, and
procurement leads at EPC contractors.
"""

from __future__ import annotations

import logging
import os
import time

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

EXA_API_URL = "https://api.exa.ai/search"

# In-memory cache: (query, max_results) -> (timestamp, results)
_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_TTL = 14400  # 4 hours
_MAX_CACHE_SIZE = 200

DEFINITION = {
    "name": "search_exa_people",
    "description": (
        "AI-powered web search for finding people at companies using the Exa neural "
        "search engine. Use natural language queries to discover project managers, "
        "VPs of construction, procurement leads, and other contacts at EPC contractors "
        "and solar developers. Returns web pages that mention relevant people, with "
        "title, URL, and a text snippet. Example query: "
        "'Signal Energy solar project manager Texas'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural language query, e.g. "
                    "'Signal Energy solar project manager Texas'"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 10, max 20).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


class Input(BaseModel):
    query: str = Field(..., description="Natural language query, e.g. 'Signal Energy solar project manager Texas'")
    max_results: int = Field(10, ge=1, le=20)


async def execute(tool_input: dict) -> dict:
    """Run an Exa people search with in-memory caching."""
    inp = Input(**tool_input)
    query = inp.query.strip()
    if not query:
        return {
            "status": "error",
            "error": "Query must not be blank",
            "error_category": "validation_error",
        }
    max_results = inp.max_results

    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "error": "EXA_API_KEY not set. Exa people search is unavailable.",
            "error_category": "api_key_missing",
        }

    # Check cache
    cache_key = (query.strip().lower(), max_results)
    now = time.monotonic()
    if cache_key in _cache:
        cached_at, cached_results = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return {
                "status": "success",
                "data": {"results": cached_results},
                "source": "exa",
                "cached": True,
            }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }
    body = {
        "query": query,
        "type": "auto",
        "category": "people",
        "numResults": max_results,
        "contents": {"text": {"maxCharacters": 500}},
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                EXA_API_URL,
                headers=headers,
                json=body,
                timeout=20.0,
            )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "error": f"Exa API returned {exc.response.status_code}",
            "error_category": "search_tool_error",
            "source": "exa",
        }
    except (httpx.RequestError, ValueError) as exc:
        return {
            "status": "error",
            "error": f"Exa search failed: {exc}",
            "error_category": "search_tool_error",
            "source": "exa",
        }

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "text": (r.get("text") or ""),
            "score": r.get("score", 0) or 0,
        }
        for r in data.get("results", [])
    ]

    _cache[cache_key] = (now, results)

    if len(_cache) > _MAX_CACHE_SIZE:
        # Evict oldest half by timestamp
        sorted_keys = sorted(_cache, key=lambda k: _cache[k][0])
        for k in sorted_keys[: len(sorted_keys) // 2]:
            del _cache[k]

    return {
        "status": "success",
        "data": {"results": results},
        "source": "exa",
    }
