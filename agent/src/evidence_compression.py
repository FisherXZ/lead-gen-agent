"""Evidence compression layer.

Uses Haiku to extract only EPC-relevant content from raw page fetches,
reducing context bloat by 3-5x. Applied as post-processing on fetch_page
and firecrawl_scrape tool outputs.

Opt-in via EVIDENCE_COMPRESSION=1 environment variable.
"""

from __future__ import annotations

import logging
import os

import anthropic

logger = logging.getLogger(__name__)

COMPRESSION_MODEL = os.environ.get(
    "COMPRESSION_MODEL", "claude-haiku-4-5-20251001"
)
# Skip compression for content shorter than this
MIN_CONTENT_LENGTH = 500
# Max input to send to Haiku
MAX_INPUT_CHARS = 10000
# Fallback truncation length when Haiku fails
FALLBACK_TRUNCATE = 2000


def is_compression_enabled() -> bool:
    """Check if evidence compression is enabled via environment variable."""
    return os.environ.get("EVIDENCE_COMPRESSION", "").strip() == "1"


async def compress_evidence(raw_content: str, query_context: str) -> str:
    """Extract only EPC-relevant paragraphs from raw content using Haiku.

    Returns compressed content (typically 200-500 tokens vs 2000-5000 raw).
    Falls back to truncation if Haiku call fails.

    Args:
        raw_content: Raw page text to compress.
        query_context: Research context (project name, developer, etc.)
            to help Haiku identify relevant paragraphs.

    Returns:
        Compressed text with only EPC-relevant paragraphs, or truncated
        fallback on error.
    """
    if len(raw_content) < MIN_CONTENT_LENGTH:
        return raw_content

    try:
        client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        response = await client.messages.create(
            model=COMPRESSION_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract only paragraphs that mention any of:\n"
                        "- EPC contractors, construction companies, or engineering firms\n"
                        "- Project construction milestones, groundbreaking, or completion\n"
                        "- Contract awards, procurement decisions, or contractor selection\n"
                        "- Company names associated with building or constructing "
                        "solar/energy projects\n\n"
                        f"Context: {query_context[:500]}\n\n"
                        f"Content to extract from:\n{raw_content[:MAX_INPUT_CHARS]}\n\n"
                        "Return ONLY the relevant paragraphs verbatim. "
                        "If nothing is relevant, return "
                        '"No EPC-relevant content found." '
                        "Do not summarize or rephrase."
                    ),
                }
            ],
        )
        result = response.content[0].text
        if result and len(result) > 20:
            return result
        return raw_content[:FALLBACK_TRUNCATE]  # Fallback: truncate
    except Exception as e:
        logger.warning(
            "Evidence compression failed: %s — falling back to truncation", e
        )
        return raw_content[:FALLBACK_TRUNCATE]
