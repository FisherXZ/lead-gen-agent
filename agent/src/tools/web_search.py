"""Web search tool — Tavily API wrapper with in-memory cache."""

from __future__ import annotations

import logging
import os
import time

import tenacity
from tavily import TavilyClient

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2

# In-memory cache: (query, max_results) -> (timestamp, results)
_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour

DEFINITION = {
    "name": "web_search",
    "description": (
        "Search the web for information using the Tavily search engine. "
        "Use this for initial discovery — finding press releases, trade publication "
        "articles, contractor portfolio pages, and news about solar projects and "
        "EPC contractors. Returns up to 10 results, each with a title, URL, and "
        "content snippet (~200 chars). Snippets are short — if a result looks "
        "promising but the snippet doesn't contain the key detail, use fetch_page "
        "to read the full article. Supports site-specific searches like "
        "'site:solarpowerworldonline.com [developer] solar'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific: include developer name, project name, state, and 'EPC' or 'construction contractor'.",
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
    """Run a Tavily web search with caching."""
    query = tool_input.get("query", "")
    max_results = min(tool_input.get("max_results", 5), 10)

    if not query.strip():
        return {"error": "Empty search query."}

    # Check cache
    cache_key = (query, max_results)
    now = time.time()
    if cache_key in _cache:
        cached_at, cached_results = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return {"results": cached_results, "cached": True}

    # Execute search
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set. Web search is unavailable."}

    try:
        response = _tavily_search_with_retry(api_key, query, max_results)
    except Exception as exc:
        return {"error": f"Tavily search failed: {exc}"}
    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0),
        }
        for r in response.get("results", [])
    ]

    # Cache
    _cache[cache_key] = (now, results)

    return {"results": results}


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(Exception),
    stop=tenacity.stop_after_attempt(_MAX_RETRIES + 1),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
    before_sleep=lambda rs: logger.info(
        "tavily_search retry #%d: %s", rs.attempt_number, rs.outcome.exception(),
    ),
)
def _tavily_search_with_retry(api_key: str, query: str, max_results: int) -> dict:
    client = TavilyClient(api_key=api_key)
    return client.search(query, max_results=max_results, search_depth="advanced")
