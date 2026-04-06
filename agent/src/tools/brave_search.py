"""Brave web search tool — broader coverage for EPC discovery.

Use when Tavily results are insufficient. Surfaces subcontractor pages,
niche blogs, EPC portfolio pages, and regulatory PDFs that Tavily may miss.
"""

from __future__ import annotations

import logging
import os
import time

import httpx
import tenacity

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2

# In-memory cache: (query, count) -> (timestamp, results)
_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"

DEFINITION = {
    "name": "web_search_broad",
    "description": (
        "Search the web using Brave Search for broader coverage than the primary "
        "search engine. Use this as a second opinion when web_search (Tavily) "
        "returns few or no relevant results. Brave surfaces subcontractor pages, "
        "niche construction blogs, EPC portfolio pages, and regulatory PDFs that "
        "Tavily may miss. Returns up to 10 results with title, URL, and snippet. "
        "If a result looks promising, use fetch_page to read the full article."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The search query. Be specific: include developer name, "
                    "project name, state, and 'EPC' or 'construction contractor'."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Run a Brave web search with caching."""
    query = tool_input.get("query", "")
    max_results = min(tool_input.get("max_results", 5), 10)

    if not query.strip():
        return {"error": "Empty search query."}

    api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return {
            "error": (
                "BRAVE_SEARCH_API_KEY not set. "
                "Brave search is unavailable — use web_search instead."
            )
        }

    # Check cache
    cache_key = (query.strip().lower(), max_results)
    now = time.monotonic()
    if cache_key in _cache:
        cached_at, cached_results = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return {"results": cached_results, "cached": True}

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": query,
        "count": min(max_results, 20),
    }

    try:
        data = await _brave_request_with_retry(headers, params)
    except Exception as exc:
        return {"error": f"Brave search failed: {exc}"}

    results = []
    for r in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("description", ""),
                "score": r.get("relevancy_score", 0) or 0,
            }
        )

    _cache[cache_key] = (now, results)
    return {"results": results}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


@tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable),
    stop=tenacity.stop_after_attempt(_MAX_RETRIES + 1),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
    before_sleep=lambda rs: logger.info(
        "brave_search retry #%d: %s",
        rs.attempt_number,
        rs.outcome.exception(),
    ),
)
async def _brave_request_with_retry(headers: dict, params: dict) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(BRAVE_API_URL, headers=headers, params=params, timeout=15.0)
    response.raise_for_status()
    return response.json()
