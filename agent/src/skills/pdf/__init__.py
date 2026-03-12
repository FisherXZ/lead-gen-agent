"""PDF skill — extract text and tables from PDF documents."""

from __future__ import annotations

from .extractor import extract_text, extract_text_from_url

SKILL_META = {
    "name": "pdf",
    "description": "Extract text and tables from PDF documents",
    "version": "0.1.0",
}

__all__ = ["SKILL_META", "extract_text", "extract_text_from_url"]
