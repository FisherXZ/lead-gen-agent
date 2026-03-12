"""Search projects with joined EPC discovery data."""

from __future__ import annotations

from .. import db

DEFINITION = {
    "name": "search_projects_with_epc",
    "description": (
        "Search solar projects joined with their latest EPC discovery results. "
        "Two modes: (1) project-first — find projects by state/developer/capacity "
        "and see any pending or accepted EPC discoveries attached; (2) EPC-first — "
        "find all projects linked to a specific EPC contractor name. Unlike "
        "search_projects (which only shows accepted EPCs in epc_company), this tool "
        "includes pending discoveries so you can see the full research pipeline. "
        "Use this when users ask about EPC coverage, pending reviews, or want to "
        "see projects grouped by contractor."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": "Two-letter state abbreviation (e.g. 'TX', 'CA').",
            },
            "cod_year": {
                "type": "integer",
                "description": "Filter to projects with expected COD in this year.",
            },
            "epc_name": {
                "type": "string",
                "description": (
                    "EPC contractor name to search for (partial match, case-insensitive). "
                    "When provided, switches to EPC-first mode."
                ),
            },
            "developer": {
                "type": "string",
                "description": "Developer name (partial match, case-insensitive).",
            },
            "mw_min": {
                "type": "number",
                "description": "Minimum MW capacity.",
            },
            "confidence_min": {
                "type": "string",
                "enum": ["confirmed", "likely", "possible", "unknown"],
                "description": (
                    "Minimum confidence level to include. 'confirmed' = only confirmed; "
                    "'likely' = confirmed + likely; 'possible' = confirmed + likely + possible; "
                    "'unknown' = all (default)."
                ),
            },
            "include_pending": {
                "type": "boolean",
                "description": "Include pending (unreviewed) discoveries. Default true.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 30, max 100).",
            },
        },
    },
}


async def execute(tool_input: dict) -> dict:
    """Search projects with EPC discovery data."""
    limit = min(tool_input.get("limit", 30), 100)
    results = db.search_projects_with_epc(
        state=tool_input.get("state"),
        cod_year=tool_input.get("cod_year"),
        epc_name=tool_input.get("epc_name"),
        developer=tool_input.get("developer"),
        mw_min=tool_input.get("mw_min"),
        confidence_min=tool_input.get("confidence_min"),
        include_pending=tool_input.get("include_pending", True),
        limit=limit,
    )
    query_mode = "epc_search" if tool_input.get("epc_name") else "project_search"
    return {"results": results, "count": len(results), "query_mode": query_mode}
