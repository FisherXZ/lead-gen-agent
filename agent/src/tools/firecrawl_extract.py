"""Firecrawl structured extraction tool.

Replaces snippet-blindness: sends a URL to Firecrawl and gets back typed
JSON data extracted from the full page content (JS-rendered). Handles
portfolio pages, press releases, PDFs, and JS-heavy sites that fetch_page
can't read.

Uses Firecrawl's /scrape endpoint with formats=[{type:"json", schema:...}]
rather than the separate /extract endpoint — simpler fit for single-URL
usage inside our research loop.
"""

from __future__ import annotations

import logging
import os

from ..models import EpcPageExtraction

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "firecrawl_extract",
    "description": (
        "Extract structured data from a URL using Firecrawl. Sends the page to "
        "Firecrawl's AI extraction service and gets back typed JSON with fields: "
        "epc_contractor, project_name, mw_capacity, developer, announcement_date, "
        "source_confidence, key_quote. Use this INSTEAD of fetch_page when: "
        "(a) the URL is a press release, EPC portfolio page, or regulatory filing, "
        "(b) the page is JS-heavy (React/Vue/Angular) and fetch_page returned empty, "
        "(c) you want structured data rather than raw text. Returns error if "
        "FIRECRAWL_API_KEY is not set — fall back to fetch_page in that case."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "The full URL to extract from. Must start with http:// or https://. "
                    "Examples: press release URL, EPC portfolio page, SEC filing page."
                ),
            },
        },
        "required": ["url"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Extract structured data from a URL via Firecrawl."""
    url = tool_input.get("url", "").strip()
    if not url:
        return {"error": "Empty URL."}
    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}

    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return {
            "error": (
                "FIRECRAWL_API_KEY not set. Firecrawl extract is unavailable — "
                "use fetch_page instead."
            )
        }

    # Lazy import so the package is only required when the tool is actually used
    try:
        from firecrawl import AsyncFirecrawl
    except ImportError:
        return {
            "error": (
                "firecrawl-py package not installed. Run `pip install firecrawl-py` "
                "or use fetch_page instead."
            )
        }

    try:
        client = AsyncFirecrawl(api_key=api_key)
        schema = EpcPageExtraction.model_json_schema()
        result = await client.scrape(
            url,
            formats=[{"type": "json", "schema": schema}],
            only_main_content=True,
            timeout=120000,
        )
    except Exception as exc:
        logger.warning("Firecrawl extraction failed for %s: %s", url, exc)
        return {"error": f"Firecrawl extraction failed: {exc}"}

    # Response shape: result.data.json (or result["data"]["json"] depending on SDK version)
    data = _extract_data_field(result)
    if not data:
        return {
            "error": "Firecrawl returned no structured data (page may not contain EPC info).",
            "url": url,
        }

    return {
        "url": url,
        "extracted": data,
        "source_tool": "firecrawl_extract",
    }


def _extract_data_field(result) -> dict | None:
    """Normalize Firecrawl response to a dict matching EpcPageExtraction.

    SDK versions vary: sometimes result is an object with .data, sometimes a dict.
    JSON extraction lives under data.json (object) or data["json"] (dict).
    """
    if result is None:
        return None

    # Object-like response
    data = getattr(result, "data", None)
    if data is None and isinstance(result, dict):
        data = result.get("data")

    if data is None:
        return None

    # Nested "json" field under data
    json_data = getattr(data, "json", None)
    if json_data is None and isinstance(data, dict):
        json_data = data.get("json")

    if isinstance(json_data, dict):
        return json_data
    return None
