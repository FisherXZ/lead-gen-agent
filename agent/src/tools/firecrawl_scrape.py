"""Firecrawl scrape tool — JS-rendered page fetching via Firecrawl API."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from urllib.parse import urlparse

import firecrawl

logger = logging.getLogger(__name__)

_MAX_CHARS = 20_000
_MAX_URL_LENGTH = 2000
_SCRAPE_TIMEOUT_MS = 30_000
_CACHE_TTL = 900  # 15 minutes

# In-memory cache: url -> (timestamp, result_dict)
_cache: dict[str, tuple[float, dict]] = {}

DEFINITION = {
    "name": "firecrawl_scrape",
    "description": (
        "Fetch a web page and extract its content as clean markdown using "
        "Firecrawl. Unlike fetch_page, this tool handles JavaScript-rendered "
        "pages (React/Angular/Vue sites, EPC portfolio pages behind JS "
        "frameworks, cookie consent walls). Use this when fetch_page returns "
        "an error like 'Could not extract article text' or when you know the "
        "target site requires JavaScript. Returns cleaned markdown truncated "
        "to ~20,000 characters. Costs 1 Firecrawl credit per call — prefer "
        "fetch_page for static HTML pages."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (must start with http:// or https://).",
            },
        },
        "required": ["url"],
    },
}


def _validate_url(url: str) -> str | None:
    """Return an error message string, or None if the URL is valid."""
    if not url:
        return "URL must not be empty."

    if len(url) > _MAX_URL_LENGTH:
        return f"URL exceeds maximum length of {_MAX_URL_LENGTH} characters."

    try:
        parsed = urlparse(url)
    except Exception:
        return "URL could not be parsed."

    if parsed.scheme not in ("http", "https"):
        return f"URL scheme '{parsed.scheme}' is not allowed; must be http or https."

    if parsed.username or parsed.password:
        return "URL must not contain credentials (username or password)."

    hostname = parsed.hostname or ""
    if "." not in hostname:
        return f"URL hostname '{hostname}' does not appear to be a valid domain (no dot found)."

    return None


def _scrape_sync(url: str, api_key: str) -> dict:
    """Synchronous wrapper for the Firecrawl SDK. Returns a result dict or error dict."""
    try:
        timeout_seconds = _SCRAPE_TIMEOUT_MS / 1000.0
        app = firecrawl.FirecrawlApp(api_key=api_key, timeout=timeout_seconds)
        doc = app.scrape(url, formats=["markdown"], only_main_content=True)
    except Exception as exc:
        logger.warning("firecrawl_scrape SDK error for %s: %s", url, exc)
        return {"error": str(exc)}

    markdown = doc.markdown
    if not markdown or not markdown.strip():
        return {"error": f"Could not extract content from {url}: page returned empty markdown."}

    status_code = None
    try:
        status_code = doc.metadata.status_code
    except Exception:  # noqa: BLE001
        logger.debug("firecrawl_scrape: could not read status_code from metadata")

    _TRUNCATION_SUFFIX = "[... truncated]"
    if len(markdown) > _MAX_CHARS:
        markdown = markdown[: _MAX_CHARS - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX

    return {
        "url": url,
        "text": markdown,
        "length": len(markdown),
        "source": "firecrawl",
        "status_code": status_code,
    }


async def execute(tool_input: dict) -> dict:
    """Fetch a JS-rendered page via Firecrawl, with in-memory caching."""
    url = tool_input.get("url", "")

    # Validate URL before checking API key so we fail fast on bad inputs
    validation_error = _validate_url(url)
    if validation_error:
        return {"error": validation_error}

    # Check cache
    now = time.monotonic()
    if url in _cache:
        cached_at, cached_result = _cache[url]
        if now - cached_at < _CACHE_TTL:
            return {**cached_result, "cached": True}

    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return {"error": "FIRECRAWL_API_KEY not set. Firecrawl scraping is unavailable."}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_scrape_sync, url, api_key),
            timeout=_SCRAPE_TIMEOUT_MS / 1000.0,
        )
    except TimeoutError:
        logger.warning("firecrawl_scrape wall-clock timeout for %s", url)
        return {"error": f"Firecrawl scrape timed out after {_SCRAPE_TIMEOUT_MS // 1000}s."}

    if "error" not in result:
        _cache[url] = (time.monotonic(), result)

    return result
