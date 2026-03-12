"""CSV skill — parse, analyze, and export CSV data."""

from __future__ import annotations

from .processor import parse_csv, export_csv, summarize_csv

SKILL_META = {
    "name": "csv",
    "description": "Parse, analyze, and export CSV data",
    "version": "0.1.0",
}

__all__ = ["SKILL_META", "parse_csv", "export_csv", "summarize_csv"]
