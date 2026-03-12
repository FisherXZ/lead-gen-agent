"""CSV processing — parse, summarize, and export."""

from __future__ import annotations

import csv
import io
import logging

logger = logging.getLogger(__name__)

_MAX_ROWS_PREVIEW = 50  # max rows to show in inline preview
_MAX_ROWS_PARSE = 10_000  # max rows to parse


def parse_csv(text: str, max_rows: int = _MAX_ROWS_PARSE) -> dict:
    """Parse CSV text into structured data.

    Returns:
        {
            "headers": ["col1", "col2", ...],
            "rows": [["val1", "val2", ...], ...],
            "row_count": int,
            "column_count": int,
            "truncated": bool,
        }
    """
    reader = csv.reader(io.StringIO(text))
    rows = []
    headers = []

    for i, row in enumerate(reader):
        if i == 0:
            headers = row
            continue
        if i > max_rows:
            break
        rows.append(row)

    return {
        "headers": headers,
        "rows": rows,
        "row_count": len(rows),
        "column_count": len(headers),
        "truncated": len(rows) >= max_rows,
    }


def summarize_csv(text: str) -> dict:
    """Parse CSV and return a summary suitable for the agent.

    Returns headers, row count, and a preview of first rows.
    """
    parsed = parse_csv(text)
    preview_rows = parsed["rows"][:_MAX_ROWS_PREVIEW]

    return {
        "headers": parsed["headers"],
        "row_count": parsed["row_count"],
        "column_count": parsed["column_count"],
        "preview": preview_rows,
        "truncated": parsed["row_count"] > _MAX_ROWS_PREVIEW,
    }


def export_csv(headers: list[str], rows: list[list[str]], filename: str = "export.csv") -> dict:
    """Generate CSV text from headers and rows.

    Returns:
        {
            "csv_text": str,
            "filename": str,
            "row_count": int,
            "headers": list[str],
            "rows": list[list[str]],
        }
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)

    return {
        "csv_text": output.getvalue(),
        "filename": filename,
        "row_count": len(rows),
        "headers": headers,
        "rows": rows,
    }
