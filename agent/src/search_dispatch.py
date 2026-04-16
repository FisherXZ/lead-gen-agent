"""Procedural search dispatcher for v3 research loop.

Executes search → scrape → filter pipeline WITHOUT any LLM calls.
This is the core cost-reduction lever — replacing Claude tool_use
orchestration (30+ LLM turns) with Python function calls (~0 LLM turns).
"""

from __future__ import annotations

import asyncio
import logging
import os

from .context_compressor import ContextCompressor
from .evidence import EvidenceStore
from .models import Finding
from .tools import web_search, brave_search, firecrawl_extract, fetch_page

logger = logging.getLogger(__name__)


async def parallel_search(
    query: str,
    max_results: int = 5,
) -> list[dict]:
    """Run Tavily + Brave in parallel, dedupe by URL, return top results.

    Each result: {"title": str, "url": str, "content": str, "score": float}
    Returns empty list on total failure (both providers error).
    """
    tavily_task = web_search.execute({"query": query, "max_results": max_results})
    brave_task = brave_search.execute({"query": query, "max_results": max_results})

    raw = await asyncio.gather(tavily_task, brave_task, return_exceptions=True)

    seen_urls: set[str] = set()
    combined: list[dict] = []

    for result in raw:
        if isinstance(result, Exception):
            logger.warning("Search provider failed: %s", result)
            continue
        if isinstance(result, dict) and "error" not in result:
            for item in result.get("results", []):
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    combined.append(item)

    # Sort by score (best first), return top N
    combined.sort(key=lambda x: x.get("score", 0), reverse=True)
    return combined[: max_results * 2]  # return more than max_results since we'll filter later


async def smart_scrape(url: str, query: str) -> dict | None:
    """Scrape a URL. Try firecrawl_extract first (JS + structured), fall back to fetch_page.

    Returns: {"url": str, "text": str} or None on failure.
    """
    # Try Firecrawl if key is set (handles JS rendering, PDFs, structured output)
    if os.environ.get("FIRECRAWL_API_KEY"):
        result = await firecrawl_extract.execute({"url": url})
        if "error" not in result:
            extracted = result.get("extracted") or {}
            # Build text from structured fields
            parts = []
            for key in ("epc_contractor", "project_name", "developer", "key_quote"):
                val = extracted.get(key)
                if val:
                    parts.append(f"{key}: {val}")
            if extracted.get("mw_capacity"):
                parts.append(f"mw_capacity: {extracted['mw_capacity']}")
            text = " | ".join(parts) if parts else str(extracted)
            if text.strip():
                return {"url": url, "text": text}

    # Fallback: fetch_page (trafilatura — works for ~70% of sites)
    result = await fetch_page.execute({"url": url})
    if isinstance(result, dict) and "error" not in result:
        text = result.get("text", "")
        if text and len(text) > 100:
            return {"url": url, "text": text}

    return None


async def execute_sub_query(
    query: str,
    evidence: EvidenceStore,
    compressor: ContextCompressor,
    iteration: int = 0,
) -> int:
    """Run one sub-query: search → scrape → filter → add findings.

    Returns count of findings added. Makes NO LLM calls.
    """
    evidence.record_search(query)

    # 1. Search (Tavily + Brave in parallel)
    search_results = await parallel_search(query, max_results=5)
    if not search_results:
        logger.info("No search results for: %s", query)
        return 0

    # 2. Scrape top URLs in parallel (cap at 5 to control cost/time)
    urls = [r["url"] for r in search_results[:5]]
    scraped = await asyncio.gather(*[smart_scrape(u, query) for u in urls])
    docs = [d for d in scraped if d is not None]

    if not docs:
        logger.info("No scrapeable content for: %s", query)
        return 0

    # 3. Filter by semantic relevance (uses embedding similarity)
    try:
        relevant = await compressor.filter(docs, query, max_results=5)
    except Exception as e:
        logger.warning("Context compression failed: %s — using unfiltered", e)
        relevant = [{"url": d["url"], "text": d["text"][:2000], "score": 0.0} for d in docs[:5]]

    # 4. Add to evidence store
    added = 0
    for chunk in relevant:
        if evidence.add(
            Finding(
                text=chunk["text"][:2000],
                source_url=chunk["url"],
                source_tool="parallel_search",
                reliability="medium",
                iteration=iteration,
            )
        ):
            added += 1

    return added
