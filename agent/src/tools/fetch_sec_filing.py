"""Fetch and extract text from a specific SEC EDGAR filing.

Use after search_sec_edgar finds a promising filing. Takes a CIK + accession
number or direct URL, downloads the filing, and extracts text with EPC keyword
filtering. Uses the official data.sec.gov Archives URLs.
"""

from __future__ import annotations

import logging
import re

import httpx
import tenacity

from ._base import cache_get, cache_set

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_MAX_RETRIES = 2
_MAX_CHARS = 6000  # Larger than fetch_page since SEC filings are dense
_CACHE_TTL_HOURS = 168  # 7 days — filings don't change

_HEADERS = {
    "User-Agent": "CivRobotics-EPCResearch/1.0 (research@civrobotics.com)",
    "Accept": "text/html, application/xhtml+xml, application/pdf, */*",
}

# Accession number pattern: XXXXXXXXXX-XX-XXXXXX
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")

# Keywords for relevance filtering
_EPC_KEYWORDS = {
    "epc", "contractor", "construction", "engineering", "procurement",
    "solar", "megawatt", "mw", "awarded", "selected",
    "built by", "constructed by", "utility-scale", "commissioning",
    "blattner", "mccarthy", "mortenson", "primoris", "rosendin",
    "solv energy", "signal energy", "strata", "moss",
}


DEFINITION = {
    "name": "fetch_sec_filing",
    "description": (
        "Fetch and read a specific SEC EDGAR filing. Use after search_sec_edgar "
        "finds a relevant filing — especially 8-K filings that may contain EPC "
        "contract details. Provide cik + accession_number (from search_sec_edgar "
        "results) or a direct URL. Extracts text and filters for EPC-relevant "
        "paragraphs. Returns up to ~6000 characters. Works with HTML and PDF filings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cik": {
                "type": "string",
                "description": (
                    "Company CIK number (from search_sec_edgar results). "
                    "Required when using accession_number."
                ),
            },
            "accession_number": {
                "type": "string",
                "description": (
                    "SEC accession number (e.g., '0001564590-24-012345'). "
                    "Get this from search_sec_edgar results."
                ),
            },
            "primary_document": {
                "type": "string",
                "description": (
                    "Primary document filename (e.g., 'smxt-20250805.htm'). "
                    "Get this from search_sec_edgar results. If omitted, the "
                    "filing index page is fetched to find the main document."
                ),
            },
            "url": {
                "type": "string",
                "description": (
                    "Direct URL to a filing document. Use if you have a specific "
                    "URL from search_sec_edgar or another source."
                ),
            },
        },
    },
}


async def execute(tool_input: dict) -> dict:
    """Fetch a SEC filing and extract EPC-relevant text."""
    accession = tool_input.get("accession_number", "").strip()
    cik = tool_input.get("cik", "").strip()
    primary_doc = tool_input.get("primary_document", "").strip()
    url = tool_input.get("url", "").strip()

    if not accession and not url:
        return {"error": "Provide either accession_number (with cik) or url."}

    # Resolve URL from accession number + CIK
    if accession and not url:
        if not cik:
            return {
                "error": "cik is required when using accession_number. "
                "Get it from search_sec_edgar results (the 'cik' field)."
            }
        if not _ACCESSION_RE.match(accession):
            return {"error": f"Invalid accession number format: {accession}. Expected: XXXXXXXXXX-XX-XXXXXX"}
        url = _build_archives_url(cik, accession, primary_doc)

    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}

    # Check cache
    cache_params = {"url": url}
    cached = cache_get("fetch_sec_filing", cache_params)
    if cached is not None:
        return {**cached, "cached": True}

    # If no primary_document, resolve from filing index
    if accession and not primary_doc:
        try:
            url = await _resolve_filing_document(url)
        except Exception as exc:
            return {"error": f"Failed to resolve filing document: {exc}"}
        if not url:
            return {"error": "Could not find a readable document in this filing."}

    # Fetch and extract the actual document
    try:
        response = await _fetch_with_retry(url)
    except httpx.TimeoutException:
        return {"error": f"Filing fetch timed out after {_TIMEOUT}s."}
    except httpx.HTTPStatusError as e:
        return {"error": f"SEC returned HTTP {e.response.status_code} for {url}."}
    except Exception as exc:
        return {"error": f"Filing fetch failed: {exc}"}

    content_type = response.headers.get("content-type", "").lower()

    # PDF path
    if "application/pdf" in content_type:
        result = _extract_from_pdf(url, response.content)
    else:
        result = _extract_from_html(url, response.text)

    if "error" not in result:
        cache_set("fetch_sec_filing", cache_params, result, ttl_hours=_CACHE_TTL_HOURS)

    return result


def _build_archives_url(cik: str, accession: str, primary_doc: str = "") -> str:
    """Build a data.sec.gov Archives URL from CIK + accession + optional primary doc."""
    padded_cik = cik.zfill(10)
    accession_no_dashes = accession.replace("-", "")

    if primary_doc:
        return f"https://www.sec.gov/Archives/edgar/data/{padded_cik}/{accession_no_dashes}/{primary_doc}"

    # Without primary_doc, point to the index page
    return f"https://www.sec.gov/Archives/edgar/data/{padded_cik}/{accession_no_dashes}/"


async def _resolve_filing_document(index_url: str) -> str | None:
    """Given a filing index URL, find the main document (HTM/PDF).

    Falls back to the index URL itself if it's already a document.
    """
    # If URL already points to a document, use it directly
    if index_url.endswith((".htm", ".html", ".txt", ".pdf")):
        return index_url

    # Try to fetch the filing index and find document links
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            resp = await client.get(index_url, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text

            # Look for the primary document link in the index
            htm_links = re.findall(r'href="([^"]+\.htm)"', html)
            if htm_links:
                link = htm_links[0]
                if link.startswith("/"):
                    return f"https://www.sec.gov{link}"
                if not link.startswith("http"):
                    return f"{index_url.rstrip('/')}/{link}"
                return link

            # Try .txt filing links
            txt_links = re.findall(r'href="([^"]+\.txt)"', html)
            if txt_links:
                link = txt_links[0]
                if link.startswith("/"):
                    return f"https://www.sec.gov{link}"
                if not link.startswith("http"):
                    return f"{index_url.rstrip('/')}/{link}"
                return link

    except Exception:
        pass

    # Fallback: return the index URL and let the HTML extractor handle it
    return index_url


def _extract_from_html(url: str, html: str) -> dict:
    """Extract EPC-relevant text from an HTML filing."""
    import trafilatura

    if not html:
        return {"error": "Empty response from SEC."}

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if not text:
        return {"error": "Could not extract text from this SEC filing."}

    filtered = _extract_relevant_sections(text)

    return {
        "url": url,
        "text": filtered,
        "length": len(filtered),
        "content_type": "html",
        "source_type": "sec_filing",
    }


def _extract_from_pdf(url: str, pdf_bytes: bytes) -> dict:
    """Extract EPC-relevant text from a PDF filing."""
    if len(pdf_bytes) > 15_000_000:
        return {"error": f"PDF too large ({len(pdf_bytes):,} bytes, limit 15MB)"}

    try:
        from src.skills.pdf.extractor import extract_text
        result = extract_text(pdf_bytes)
    except Exception as e:
        return {"error": f"PDF extraction failed: {e}"}

    text = result.get("text", "")
    if not text:
        return {"error": "Could not extract text from PDF filing."}

    filtered = _extract_relevant_sections(text)

    return {
        "url": url,
        "text": filtered,
        "length": len(filtered),
        "content_type": "pdf",
        "source_type": "sec_filing",
        "page_count": result.get("page_count", 0),
    }


def _extract_relevant_sections(text: str) -> str:
    """Score paragraphs by EPC keyword hits, return relevant ones."""
    if not text:
        return ""

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text[:_MAX_CHARS]

    relevant = []
    for para in paragraphs:
        para_lower = para.lower()
        if any(kw in para_lower for kw in _EPC_KEYWORDS):
            relevant.append(para)

    if not relevant:
        if len(text) > _MAX_CHARS:
            return text[:_MAX_CHARS] + "\n\n[... truncated — no EPC keywords found]"
        return text

    result = f"[Extracted {len(relevant)}/{len(paragraphs)} paragraphs matching EPC keywords]\n\n"
    result += "\n\n".join(relevant)

    if len(result) > _MAX_CHARS:
        result = result[:_MAX_CHARS] + "\n\n[... truncated]"

    return result


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
        "fetch_sec_filing retry #%d: %s", rs.attempt_number, rs.outcome.exception(),
    ),
)
async def _fetch_with_retry(url: str) -> httpx.Response:
    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response
