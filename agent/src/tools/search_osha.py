"""OSHA establishment search — find EPC contractors at construction sites.

Queries osha.gov/ords/imis/establishment.html for employer inspection records.
OSHA names the employer (= EPC contractor) at construction sites with physical
addresses. Cross-reference addresses with known solar project locations.

Best for reverse lookup: search by known EPC name to find their active sites.
"""

from __future__ import annotations

import logging
import re

import httpx
import tenacity

from ._base import cache_get, cache_set

logger = logging.getLogger(__name__)

OSHA_SEARCH_URL = "https://www.osha.gov/ords/imis/establishment.search"
_TIMEOUT = 20.0  # Gov sites can be slow
_MAX_RETRIES = 2
_CACHE_TTL_HOURS = 24

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EPCResearchBot/1.0)",
    "Accept": "text/html",
}

# NAICS codes relevant to solar construction
SOLAR_NAICS = {
    "237130": "Power and Communication Line Construction",
    "238210": "Electrical Contractors",
    "237110": "Water and Sewer Line Construction",
    "236220": "Commercial Building Construction",
}

DEFINITION = {
    "name": "search_osha",
    "description": (
        "Search OSHA inspection records for a construction company's work sites. "
        "OSHA records name the employer (the EPC contractor) at each inspected "
        "construction site, with physical addresses. Use this for: (1) Reverse "
        "lookup — search by EPC name to find their active solar construction sites, "
        "then match addresses to known projects. (2) Verification — confirm an EPC "
        "is active in a specific state. Returns: employer name, site address, SIC/NAICS "
        "code, inspection date, and violation count. Note: OSHA only inspects a fraction "
        "of sites — absence of records does NOT mean the EPC isn't active there."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "employer_name": {
                "type": "string",
                "description": (
                    "Company name to search for (e.g., 'SOLV Energy', "
                    "'Blattner Energy', 'McCarthy Building')."
                ),
            },
            "state": {
                "type": "string",
                "description": (
                    "Optional: two-letter state abbreviation to filter results (e.g., 'TX', 'CA')."
                ),
            },
            "naics": {
                "type": "string",
                "description": (
                    "Optional: NAICS code to filter by industry. "
                    "'237130' = power line construction, "
                    "'238210' = electrical contractors."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 10, max 20).",
                "default": 10,
            },
        },
        "required": ["employer_name"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Search OSHA establishment records with caching."""
    employer = tool_input.get("employer_name", "").strip()
    state = tool_input.get("state", "").strip().upper()
    naics = tool_input.get("naics", "").strip()
    max_results = min(tool_input.get("max_results", 10), 20)

    if not employer:
        return {"error": "Empty employer name."}

    # Check cache
    cache_params = {"employer": employer, "state": state, "naics": naics}
    cached = cache_get("search_osha", cache_params)
    if cached is not None:
        return {"results": cached, "cached": True}

    # Build form data for OSHA search
    form_data = {
        "p_logger": "1",
        "p_log_id": "",
        "State": state if state else "all",
        "establishment": employer,
        "Site_City": "",
        "Site_State": state if state else "all",
        "p_case": "",
        "InspNr": "",
    }
    if naics:
        form_data["naession"] = naics

    try:
        html = await _search_with_retry(form_data)
    except httpx.TimeoutException:
        return {
            "error": f"OSHA search timed out after {_TIMEOUT}s. Gov sites can be slow — try again."
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"OSHA returned HTTP {e.response.status_code}."}
    except Exception as exc:
        return {"error": f"OSHA search failed: {exc}"}

    results = _parse_osha_html(html, max_results)

    # Validate parsed results — detect if HTML structure changed
    if results is None:
        return {
            "error": "OSHA HTML structure may have changed — could not parse results. Check logs."
        }

    cache_set("search_osha", cache_params, results, ttl_hours=_CACHE_TTL_HOURS)

    return {"results": results, "total_found": len(results)}


def _parse_osha_html(html: str, max_results: int) -> list[dict] | None:
    """Parse OSHA search results HTML into structured dicts.

    Returns None if the HTML structure doesn't match expectations (signals
    the site may have been redesigned).
    Returns empty list if the search simply had no results.
    """
    if not html:
        return None

    # Check for "no records found" message
    if "No matching records found" in html or "0 records" in html.lower():
        return []

    # OSHA returns results in a table. Look for the results table.
    # The table has columns: Est Name, Insp Nr, SIC, NAICS, City, State, Zip, Open Date
    results = []

    # Extract table rows using regex — more robust than full HTML parsing
    # for a gov site that doesn't change often
    row_pattern = re.compile(
        r"<tr[^>]*>\s*"
        r'<td[^>]*><a[^>]*href="([^"]*)"[^>]*>([^<]+)</a></td>\s*'  # Est Name (link + text)
        r"<td[^>]*>(\d+)</td>\s*"  # Inspection Number
        r"<td[^>]*>([^<]*)</td>\s*"  # SIC
        r"<td[^>]*>([^<]*)</td>\s*"  # NAICS
        r"<td[^>]*>([^<]*)</td>\s*"  # City
        r"<td[^>]*>([^<]*)</td>\s*"  # State
        r"<td[^>]*>([^<]*)</td>\s*"  # Zip
        r"<td[^>]*>([^<]*)</td>",  # Open Date
        re.IGNORECASE | re.DOTALL,
    )

    for match in row_pattern.finditer(html):
        detail_url, name, insp_nr, sic, naics_code, city, state, zipcode, open_date = match.groups()

        # Build full address
        address_parts = [p.strip() for p in [city, state, zipcode] if p.strip()]
        address = ", ".join(address_parts) if address_parts else ""

        results.append(
            {
                "employer_name": name.strip(),
                "inspection_number": insp_nr.strip(),
                "sic_code": sic.strip(),
                "naics_code": naics_code.strip(),
                "address": address,
                "city": city.strip(),
                "state": state.strip(),
                "zip": zipcode.strip(),
                "inspection_date": open_date.strip(),
                "detail_url": f"https://www.osha.gov{detail_url}"
                if detail_url.startswith("/")
                else detail_url,
                "source_type": "osha_inspection",
            }
        )

        if len(results) >= max_results:
            break

    # If we found no rows but the HTML looks like a results page, try a simpler parse
    if not results and ("establishment" in html.lower() and "<table" in html.lower()):
        # Try to extract at least employer names from links
        simple_pattern = re.compile(
            r"establishment\.inspection_detail\?id=(\d+)[^>]*>([^<]+)</a>",
            re.IGNORECASE,
        )
        for match in simple_pattern.finditer(html):
            insp_id, name = match.groups()
            results.append(
                {
                    "employer_name": name.strip(),
                    "inspection_number": insp_id.strip(),
                    "detail_url": f"https://www.osha.gov/ords/imis/establishment.inspection_detail?id={insp_id}",
                    "source_type": "osha_inspection",
                }
            )
            if len(results) >= max_results:
                break

    # Validation: if HTML has <table> but we got zero results, structure may have changed
    if not results and "<table" in html and len(html) > 5000:
        logger.warning(
            "OSHA HTML has tables but parser found no results — structure may have changed"
        )
        return None

    return results


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


@tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable),
    stop=tenacity.stop_after_attempt(_MAX_RETRIES + 1),
    wait=tenacity.wait_exponential(multiplier=2, min=3, max=15),
    reraise=True,
    before_sleep=lambda rs: logger.info(
        "osha_search retry #%d: %s",
        rs.attempt_number,
        rs.outcome.exception(),
    ),
)
async def _search_with_retry(form_data: dict) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        response = await client.post(OSHA_SEARCH_URL, data=form_data, follow_redirects=True)
        response.raise_for_status()
        return response.text
