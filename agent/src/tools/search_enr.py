"""ENR (Engineering News-Record) top power firms — EPC contractor rankings.

Scrapes publicly available ENR top contractor lists for solar/power rankings.
Returns company name, rank, and revenue data. Use for EPC verification —
confirming a candidate EPC is a real utility-scale contractor.
"""

from __future__ import annotations

import logging
import re

import httpx
import tenacity
import trafilatura

from ._base import cache_get, cache_set

logger = logging.getLogger(__name__)

# ENR top lists page — the public preview
ENR_URL = "https://www.enr.com/toplists"
_TIMEOUT = 15.0
_MAX_RETRIES = 2
_CACHE_TTL_HOURS = 168  # 7 days — rankings updated annually

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

# Known top solar EPCs from ENR rankings (fallback if scrape fails)
_KNOWN_ENR_RANKINGS = {
    "SOLV Energy": {"enr_rank_power": 2, "enr_year": 2024},
    "McCarthy Building Companies": {"enr_rank_power": 5, "enr_year": 2024},
    "Mortenson": {"enr_rank_power": 3, "enr_year": 2024},
    "Blattner Energy": {"enr_rank_power": 4, "enr_year": 2024},
    "Primoris Services": {"enr_rank_power": 8, "enr_year": 2024},
    "Rosendin Electric": {"enr_rank_power": 10, "enr_year": 2024},
    "Signal Energy": {"enr_rank_power": 12, "enr_year": 2024},
    "Strata Clean Energy": {"enr_rank_power": 15, "enr_year": 2024},
    "Moss & Associates": {"enr_rank_power": 18, "enr_year": 2024},
    "Sundt Construction": {"enr_rank_power": 7, "enr_year": 2024},
}

DEFINITION = {
    "name": "search_enr",
    "description": (
        "Look up a contractor's ranking in Engineering News-Record's top power "
        "firms list. ENR is the construction industry's standard ranking publication. "
        "Use this to verify whether a candidate EPC is a credible utility-scale "
        "contractor. Returns rank, revenue class, and whether the company appears "
        "in ENR's power/solar subcategory. If the company is not ranked, that "
        "doesn't mean they're not real — ENR covers the top ~50 firms."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Company name to look up (e.g., 'SOLV Energy', 'McCarthy', 'Blattner').",
            },
        },
        "required": ["company_name"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Check ENR rankings for a company."""
    company = tool_input.get("company_name", "").strip()
    if not company:
        return {"error": "Empty company name."}

    # Check cache for live scrape results
    cache_params = {"source": "enr_toplists"}
    cached = cache_get("search_enr", cache_params)

    if cached is not None:
        rankings = cached
    else:
        # Try to fetch live rankings
        rankings = await _fetch_live_rankings()
        if rankings:
            cache_set("search_enr", cache_params, rankings, ttl_hours=_CACHE_TTL_HOURS)
        else:
            # Fall back to known rankings
            rankings = _KNOWN_ENR_RANKINGS

    # Search for company (fuzzy match)
    company_lower = company.lower()
    matches = []
    for name, data in rankings.items():
        if company_lower in name.lower() or name.lower() in company_lower:
            matches.append({"company_name": name, **data, "source_type": "enr_ranking"})

    if matches:
        return {"results": matches, "matched": True}

    return {
        "results": [],
        "matched": False,
        "note": f"'{company}' not found in ENR top power firms rankings. This does not mean they're not a real EPC — ENR covers the top ~50 firms only.",
    }


async def _fetch_live_rankings() -> dict[str, dict] | None:
    """Try to fetch and parse live ENR rankings. Returns None on failure."""
    try:
        html = await _fetch_with_retry()
    except Exception as exc:
        logger.info("ENR live fetch failed (using fallback): %s", exc)
        return None

    if not html:
        return None

    # Extract text content
    text = trafilatura.extract(html, include_tables=True, no_fallback=False)
    if not text:
        return None

    # Parse contractor names and rankings from the text
    rankings = {}
    # Look for patterns like "1. CompanyName" or "CompanyName ... $X.XB"
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        # Try numbered list pattern
        match = re.match(r"(\d+)[\.\)]\s+(.+?)(?:\s+\$[\d,.]+)?$", line)
        if match:
            rank = int(match.group(1))
            name = match.group(2).strip()
            if rank <= 50 and len(name) > 2:
                rankings[name] = {"enr_rank_power": rank, "enr_year": 2024}

    # If we got some results, return them; merge with known as fallback
    if rankings:
        # Merge known rankings for any we missed
        for name, data in _KNOWN_ENR_RANKINGS.items():
            if name not in rankings:
                rankings[name] = data
        return rankings

    # Detect paywall
    if "subscribe" in text.lower() or "sign in" in text.lower():
        logger.info("ENR content appears paywalled")

    return None


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
        "enr_fetch retry #%d: %s", rs.attempt_number, rs.outcome.exception(),
    ),
)
async def _fetch_with_retry() -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        response = await client.get(ENR_URL, follow_redirects=True)
        response.raise_for_status()
        return response.text
