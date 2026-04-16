"""Fetch and extract clean text from a web page."""

from __future__ import annotations

import logging

import httpx
import tenacity
import trafilatura

from ..evidence_compression import compress_evidence, is_compression_enabled

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0  # seconds (raised from 10 for slow gov sites)
_MAX_RETRIES = 2  # up to 3 total attempts
_MAX_CHARS = 4000  # keyword extraction limit
_HARD_TRUNCATE = 8000  # absolute max returned to agent
_BLOCKED_CONTENT_TYPES = {"image/", "video/", "audio/", "application/zip"}
_PDF_CONTENT_TYPE = "application/pdf"

_EPC_KEYWORDS: set[str] = {
    # Generic EPC / solar construction terms
    "epc",
    "contractor",
    "construction",
    "engineering",
    "procurement",
    "solar",
    "megawatt",
    "mw",
    "awarded",
    "selected",
    "built by",
    "constructed by",
    "utility-scale",
    "utility scale",
    "commissioning",
    "commercial operation",
    # Known large solar EPC company names
    "blattner",
    "mccarthy",
    "mortenson",
    "primoris",
    "rosendin",
    "swinerton",
    "mas energy",
    "signal energy",
    "strata solar",
    "sunpin solar",
}


def _extract_relevant_sections(text: str) -> str:
    """Score paragraphs by EPC keyword hits, return only relevant ones.

    Falls back to head truncation if no paragraphs match any keywords.
    """
    if not text:
        return ""

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text

    relevant = []
    for para in paragraphs:
        para_lower = para.lower()
        if any(kw in para_lower for kw in _EPC_KEYWORDS):
            relevant.append(para)

    if not relevant:
        # No keyword hits — fall back to head truncation
        if len(text) > _MAX_CHARS:
            return text[:_MAX_CHARS] + "\n\n[... truncated]"
        return text

    result = "\n\n".join(relevant)
    header = f"[Extracted {len(relevant)}/{len(paragraphs)} paragraphs matching EPC keywords]\n\n"
    result = header + result

    if len(result) > _MAX_CHARS:
        result = result[:_MAX_CHARS] + "\n\n[... truncated]"

    return result


DEFINITION = {
    "name": "fetch_page",
    "description": (
        "Fetch a web page or PDF and extract its text. Use this when a "
        "web_search result snippet looks promising but you need the full article "
        "to confirm EPC details — for example, a press release where the snippet "
        "cuts off before naming the contractor. Returns cleaned text truncated to "
        "~4000 characters. Works on press releases, trade articles, EPC portfolio "
        "pages, news sites, AND PDF documents (regulatory filings, permits, etc.). "
        "Will NOT work on pages that require JavaScript rendering."
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


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    return False


async def execute(tool_input: dict) -> dict:
    """Fetch a page and extract clean text."""
    url = tool_input.get("url", "")

    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}

    try:
        response = await _fetch_with_retry(url)
    except httpx.TimeoutException:
        return {"error": f"Request timed out after {_TIMEOUT}s (retried {_MAX_RETRIES}x)."}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"}
    except _UnsupportedContentType as e:
        return {"error": f"Unsupported content type: {e}"}
    except httpx.HTTPError as e:
        return {"error": f"Request failed: {e}"}

    # --- PDF path ---
    content_type = response.headers.get("content-type", "").lower()
    if _PDF_CONTENT_TYPE in content_type:
        pdf_result = _handle_pdf(url, response.content)
        # Evidence compression for PDFs (opt-in)
        if (
            is_compression_enabled()
            and "error" not in pdf_result
            and len(pdf_result.get("text", "")) > _MAX_CHARS
        ):
            pdf_result["text"] = await compress_evidence(
                pdf_result["text"], query_context=url
            )
            pdf_result["length"] = len(pdf_result["text"])
        return pdf_result

    # --- HTML path ---
    html = response.text
    if not html:
        return {"error": "Empty response from server."}

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    if not text:
        return {"error": "Could not extract article text from this page."}

    if len(text) > _MAX_CHARS:
        text = _extract_relevant_sections(text)

    # Evidence compression — use Haiku to extract EPC-relevant content (opt-in)
    if is_compression_enabled() and len(text) > _MAX_CHARS:
        text = await compress_evidence(text, query_context=url)

    # Hard truncation — even after keyword extraction, cap at 8000 chars
    if len(text) > _HARD_TRUNCATE:
        text = text[:_HARD_TRUNCATE] + "\n\n[... truncated to 8000 chars]"

    return {"url": url, "text": text, "length": len(text)}


def _handle_pdf(url: str, pdf_bytes: bytes) -> dict:
    """Extract text from PDF bytes, apply keyword filter."""
    from src.skills.pdf.extractor import extract_text

    if len(pdf_bytes) > 10_000_000:
        return {"error": f"PDF too large ({len(pdf_bytes):,} bytes, limit 10MB)"}

    try:
        result = extract_text(pdf_bytes)
    except Exception as e:
        return {"error": f"PDF extraction failed: {e}"}

    text = result.get("text", "")
    if not text:
        return {"error": "Could not extract text from PDF."}

    if len(text) > _MAX_CHARS:
        text = _extract_relevant_sections(text)

    # Hard truncation — cap at 8000 chars
    if len(text) > _HARD_TRUNCATE:
        text = text[:_HARD_TRUNCATE] + "\n\n[... truncated to 8000 chars]"

    return {
        "url": url,
        "text": text,
        "length": len(text),
        "content_type": "pdf",
        "page_count": result.get("page_count", 0),
        "pages_extracted": result.get("pages_extracted", 0),
    }


@tenacity.retry(
    retry=tenacity.retry_if_exception(_is_retryable),
    stop=tenacity.stop_after_attempt(_MAX_RETRIES + 1),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
    before_sleep=lambda rs: logger.info(
        "fetch_page retry #%d for %s: %s",
        rs.attempt_number,
        rs.args[0] if rs.args else "?",
        rs.outcome.exception(),
    ),
)
async def _fetch_with_retry(url: str) -> httpx.Response:
    """Fetch URL with retry on transient failures."""
    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; EPCResearchBot/1.0)"},
    ) as client:
        # HEAD first to check content type
        try:
            head = await client.head(url)
            content_type = head.headers.get("content-type", "").lower()
            # PDFs are allowed — handled in execute()
            if _PDF_CONTENT_TYPE not in content_type and any(
                blocked in content_type for blocked in _BLOCKED_CONTENT_TYPES
            ):
                raise _UnsupportedContentType(content_type)
        except httpx.HTTPError:
            pass  # HEAD failed — try GET anyway

        response = await client.get(url)
        response.raise_for_status()
        return response


class _UnsupportedContentType(Exception):
    """Raised for blocked content types — not retried."""

    pass
