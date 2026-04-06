"""Export data as a downloadable CSV — agent tool.

The agent calls this when the user asks to export results (discoveries,
project lists, etc.) as a CSV file. Returns structured data that the
frontend renders as an inline table with a download button.
"""

from __future__ import annotations

from src.skills.csv.processor import export_csv

DEFINITION = {
    "name": "export_csv",
    "description": (
        "Export structured data as a CSV file for the user to download. "
        "Use this when the user asks to export, download, or save results "
        "as a CSV or spreadsheet. Provide headers (column names) and rows "
        "(list of lists). The frontend will display the data as an inline "
        "table with a download button. Always include a descriptive filename."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "headers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Column headers for the CSV.",
            },
            "rows": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "description": (
                    "Data rows. Each row is a list of string values matching the headers."
                ),
            },
            "filename": {
                "type": "string",
                "description": "Filename for the download (e.g. 'epc_discoveries.csv').",
                "default": "export.csv",
            },
        },
        "required": ["headers", "rows"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Generate CSV from headers + rows."""
    headers = tool_input.get("headers", [])
    rows = tool_input.get("rows", [])
    filename = tool_input.get("filename", "export.csv")

    if not headers:
        return {"error": "No headers provided."}
    if not rows:
        return {"error": "No data rows provided."}

    result = export_csv(headers, rows, filename)
    # Mark as CSV content type so frontend renders the CsvCard
    result["content_type"] = "csv"
    return result
