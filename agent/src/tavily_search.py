"""Tavily web search wrapper for the EPC discovery agent."""

from __future__ import annotations

import os
import time

from tavily import TavilyClient

_client: TavilyClient | None = None

# In-memory cache: (query, max_results) -> (timestamp, results)
_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _client


def search(query: str, max_results: int = 5) -> list[dict]:
    """Run a Tavily web search and return simplified results.

    Results are cached for 1 hour to avoid duplicate API calls.
    Each result contains: title, url, content (snippet), score.
    """
    cache_key = (query.strip().lower(), max_results)
    now = time.monotonic()

    # Return cached result if fresh
    if cache_key in _cache:
        cached_at, cached_results = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return cached_results

    client = _get_client()
    response = client.search(
        query=query,
        max_results=max_results,
        include_answer=False,
        search_depth="advanced",
    )
    results = []
    for r in response.get("results", []):
        results.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
        )

    _cache[cache_key] = (now, results)
    return results
