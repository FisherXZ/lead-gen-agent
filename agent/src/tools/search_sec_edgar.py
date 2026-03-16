"""SEC EDGAR company filing search — find EPC contract disclosures.

Uses the official data.sec.gov API (no auth, 10 req/sec).
Flow: company name → CIK lookup → fetch submissions → filter filings.
Only works for publicly-traded companies.
"""

from __future__ import annotations

import difflib
import logging
import re

import httpx
import tenacity

from ._base import cache_get, cache_set

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_MAX_RETRIES = 2
_CACHE_TTL_HOURS = 6  # Submissions change with new filings
_TICKERS_CACHE_TTL_HOURS = 24

# SEC requires a User-Agent with contact info
_HEADERS = {
    "User-Agent": "CivRobotics-EPCResearch/1.0 (research@civrobotics.com)",
    "Accept": "application/json",
}

# Module-level in-memory cache for company tickers
_tickers_cache: dict[str, int] | None = None

DEFINITION = {
    "name": "search_sec_edgar",
    "description": (
        "Search SEC EDGAR filings for a specific company. Looks up the company's "
        "CIK number, then fetches their recent filings filtered by form type. "
        "Use for publicly-traded solar developers/EPCs — 8-K filings often contain "
        "EPC contract announcements. If a result looks relevant, use fetch_sec_filing "
        "to read the full document. Only works for publicly-traded companies. "
        "Rate limited to 10 req/sec."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": (
                    "Company name or CIK number. Examples: 'First Solar', "
                    "'SolarMax Technology', '1274494' (CIK). Fuzzy matching is "
                    "applied — exact names not required."
                ),
            },
            "form_type": {
                "type": "string",
                "description": (
                    "Optional: filter by SEC form type. Common types: '8-K' (material events), "
                    "'10-K' (annual report), '10-Q' (quarterly). Leave empty for all forms."
                ),
            },
            "date_range": {
                "type": "string",
                "description": (
                    "Optional: date range filter as 'YYYY-MM-DD,YYYY-MM-DD'. "
                    "Example: '2023-01-01,2026-03-16'. Defaults to last 3 years."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["company_name"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Search SEC EDGAR filings for a company."""
    company_name = tool_input.get("company_name", "").strip()
    form_type = tool_input.get("form_type", "")
    date_range = tool_input.get("date_range", "")
    max_results = min(tool_input.get("max_results", 5), 10)

    if not company_name:
        return {"error": "Empty company_name. Provide a company name or CIK number."}

    # Check cache
    cache_params = {
        "company_name": company_name,
        "form_type": form_type,
        "date_range": date_range,
        "max_results": max_results,
    }
    cached = cache_get("search_sec_edgar", cache_params)
    if cached is not None:
        return {"results": cached, "cached": True}

    # Step 1: Resolve CIK
    try:
        cik, matched_name = await _resolve_cik(company_name)
    except CompanyNotFoundError as e:
        return {"error": str(e)}
    except Exception as exc:
        return {"error": f"CIK lookup failed: {exc}"}

    # Step 2: Fetch submissions
    try:
        submissions = await _fetch_submissions(cik)
    except httpx.TimeoutException:
        return {"error": f"SEC EDGAR submissions fetch timed out after {_TIMEOUT}s."}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return {"error": "SEC EDGAR rate limit exceeded (10 req/sec). Wait and retry."}
        return {"error": f"SEC EDGAR returned HTTP {e.response.status_code}."}
    except Exception as exc:
        return {"error": f"SEC EDGAR submissions fetch failed: {exc}"}

    # Step 3: Filter filings
    results = _filter_filings(submissions, cik, matched_name, form_type, date_range, max_results)

    # Cache results
    cache_set("search_sec_edgar", cache_params, results, ttl_hours=_CACHE_TTL_HOURS)

    return {"results": results}


class CompanyNotFoundError(Exception):
    pass


async def _resolve_cik(company_name: str) -> tuple[str, str]:
    """Resolve a company name to a CIK number.

    Returns (cik_string, matched_company_name).
    If input is digits, use directly as CIK.
    Otherwise fuzzy-match against company_tickers.json.
    """
    # Direct CIK input
    if company_name.isdigit():
        return company_name, company_name

    tickers = await _load_company_tickers()

    # Normalize for matching: strip common suffixes, uppercase
    normalized_input = _normalize_company_name(company_name)

    # Try exact match first
    for title, cik in tickers.items():
        if _normalize_company_name(title) == normalized_input:
            return str(cik), title

    # Fuzzy match
    all_names = list(tickers.keys())
    normalized_names = [_normalize_company_name(n) for n in all_names]
    matches = difflib.get_close_matches(normalized_input, normalized_names, n=1, cutoff=0.6)

    if matches:
        idx = normalized_names.index(matches[0])
        matched_title = all_names[idx]
        return str(tickers[matched_title]), matched_title

    raise CompanyNotFoundError(
        f"Company '{company_name}' not found in SEC EDGAR. "
        f"This tool only works for publicly-traded companies. "
        f"Try a different spelling or use the CIK number directly."
    )


def _normalize_company_name(name: str) -> str:
    """Strip common suffixes and normalize for fuzzy matching."""
    upper = name.upper().strip()
    # Remove common corporate suffixes
    for suffix in [", INC", ", INC.", " INC", " INC.", ", LLC", " LLC",
                   ", CORP", " CORP", ", CO", " CO", ", LTD", " LTD",
                   ", LP", " LP", ", L.P.", " L.P."]:
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)]
            break
    return upper.strip()


async def _load_company_tickers() -> dict[str, int]:
    """Load company_tickers.json from SEC, with in-memory + DB caching.

    Returns dict mapping company title (uppercase) -> CIK number.
    """
    global _tickers_cache
    if _tickers_cache is not None:
        return _tickers_cache

    # Try DB cache
    cached = cache_get("sec_company_tickers", {"version": "v1"})
    if cached is not None:
        _tickers_cache = cached
        return _tickers_cache

    # Fetch from SEC
    data = await _fetch_tickers_with_retry()

    # Build lookup: title -> cik
    tickers: dict[str, int] = {}
    for entry in data.values():
        title = entry.get("title", "")
        cik = entry.get("cik_str")
        if title and cik:
            tickers[title] = int(cik) if not isinstance(cik, int) else cik

    _tickers_cache = tickers
    cache_set("sec_company_tickers", {"version": "v1"}, tickers, ttl_hours=_TICKERS_CACHE_TTL_HOURS)
    return tickers


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
        "sec_edgar retry #%d: %s", rs.attempt_number, rs.outcome.exception(),
    ),
)
async def _fetch_tickers_with_retry() -> dict:
    async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
        response = await client.get("https://www.sec.gov/files/company_tickers.json")
        response.raise_for_status()
        return response.json()


@tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable),
    stop=tenacity.stop_after_attempt(_MAX_RETRIES + 1),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
    before_sleep=lambda rs: logger.info(
        "sec_edgar retry #%d: %s", rs.attempt_number, rs.outcome.exception(),
    ),
)
async def _fetch_submissions(cik: str) -> dict:
    """Fetch submissions for a CIK from data.sec.gov."""
    padded_cik = cik.zfill(10)

    # Check DB cache for submissions
    sub_cache_key = {"cik": padded_cik}
    cached = cache_get("sec_submissions", sub_cache_key)
    if cached is not None:
        return cached

    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    cache_set("sec_submissions", sub_cache_key, data, ttl_hours=_CACHE_TTL_HOURS)
    return data


def _filter_filings(
    submissions: dict,
    cik: str,
    company_name: str,
    form_type: str,
    date_range: str,
    max_results: int,
) -> list[dict]:
    """Filter and format filings from submissions response."""
    recent = submissions.get("filings", {}).get("recent", {})
    entity_name = submissions.get("name", company_name)

    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    forms = recent.get("form", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    # Parse date range
    start_date, end_date = "", ""
    if date_range and "," in date_range:
        parts = date_range.split(",")
        start_date = parts[0].strip()
        end_date = parts[1].strip()

    padded_cik = cik.zfill(10)
    results = []

    for i in range(len(accession_numbers)):
        if len(results) >= max_results:
            break

        filing_form = forms[i] if i < len(forms) else ""
        filing_date = filing_dates[i] if i < len(filing_dates) else ""
        accession = accession_numbers[i] if i < len(accession_numbers) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        description = descriptions[i] if i < len(descriptions) else ""

        # Filter by form type
        if form_type and filing_form != form_type:
            continue

        # Filter by date range
        if start_date and filing_date < start_date:
            continue
        if end_date and filing_date > end_date:
            continue

        # Build Archives URL
        accession_no_dashes = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{padded_cik}/{accession_no_dashes}/{primary_doc}"

        results.append({
            "company_name": entity_name,
            "cik": padded_cik,
            "form_type": filing_form,
            "filing_date": filing_date,
            "accession_number": accession,
            "primary_document": primary_doc,
            "description": description,
            "url": url,
            "source_type": "sec_edgar",
        })

    return results


def _clear_tickers_cache() -> None:
    """Clear the in-memory tickers cache (for testing)."""
    global _tickers_cache
    _tickers_cache = None
