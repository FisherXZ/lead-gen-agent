"""PDF text extraction using pymupdf."""

from __future__ import annotations

import logging

import httpx
import pymupdf

logger = logging.getLogger(__name__)

_MAX_PDF_BYTES = 10_000_000  # 10 MB
_MAX_PAGES = 30


def extract_text(pdf_bytes: bytes, max_pages: int = _MAX_PAGES) -> dict:
    """Extract text from PDF bytes.

    Returns:
        {
            "text": str,
            "page_count": int,
            "pages_extracted": int,
        }
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count

    pages_text = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        page_text = page.get_text()
        if page_text.strip():
            pages_text.append(page_text.strip())

    doc.close()

    return {
        "text": "\n\n".join(pages_text),
        "page_count": total_pages,
        "pages_extracted": len(pages_text),
    }


async def extract_text_from_url(
    url: str,
    timeout: float = 20.0,
    max_bytes: int = _MAX_PDF_BYTES,
) -> dict:
    """Download a PDF from a URL and extract its text.

    Returns:
        {
            "text": str,
            "page_count": int,
            "pages_extracted": int,
            "url": str,
            "size_bytes": int,
        }
        or {"error": str} on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EPCResearchBot/1.0)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            if len(response.content) > max_bytes:
                return {
                    "error": f"PDF too large ({len(response.content):,} bytes, limit {max_bytes:,})"
                }

            result = extract_text(response.content)
            result["url"] = url
            result["size_bytes"] = len(response.content)
            return result

    except httpx.TimeoutException:
        return {"error": f"PDF download timed out after {timeout}s"}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} downloading PDF"}
    except Exception as e:
        return {"error": f"PDF extraction failed: {e}"}
