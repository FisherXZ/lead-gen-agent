"""Search the solar project database."""

from __future__ import annotations

from .. import db

DEFINITION = {
    "name": "search_projects",
    "description": (
        "Search the solar project database. Returns projects matching the given "
        "filters. Use this when users ask to find, show, or list projects. Each "
        "result includes project_id, name, developer, MW capacity, state, ISO "
        "region, fuel type, queue status, lead_score (0-100), and whether an EPC "
        "has been identified. Default COD window is 2025-2028. "
        "States are stored as two-letter abbreviations (TX, CA, IL). "
        "lead_score ranks lead quality: higher = larger capacity, nearer COD, "
        "solar+storage preferred. Use min_lead_score to filter and sort_by='lead_score' "
        "to rank by score. "
        "NOTE: The epc_company field only reflects ACCEPTED discoveries. For the "
        "full picture including pending discoveries, use search_projects_with_epc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": (
                    "Two-letter state abbreviation (e.g. 'TX', 'CA', 'IL'). "
                    "Use abbreviations, not full names."
                ),
            },
            "iso_region": {
                "type": "string",
                "enum": ["ERCOT", "CAISO", "MISO"],
                "description": "ISO region filter.",
            },
            "mw_min": {
                "type": "number",
                "description": "Minimum MW capacity.",
            },
            "mw_max": {
                "type": "number",
                "description": "Maximum MW capacity.",
            },
            "developer": {
                "type": "string",
                "description": "Developer name (partial match, case-insensitive).",
            },
            "fuel_type": {
                "type": "string",
                "description": "Fuel type: 'Solar', 'Wind', 'Battery', or 'Hybrid'.",
            },
            "needs_research": {
                "type": "boolean",
                "description": (
                    "If true, only return projects that don't have an "
                    "EPC contractor identified yet."
                ),
            },
            "has_epc": {
                "type": "boolean",
                "description": "If true, only return projects that already have a known EPC.",
            },
            "search": {
                "type": "string",
                "description": ("Free text search across project name, developer, and queue ID."),
            },
            "cod_min": {
                "type": "string",
                "description": (
                    "Earliest expected COD (YYYY-MM-DD). Default '2025-01-01'. "
                    "Set to null to remove lower bound."
                ),
            },
            "cod_max": {
                "type": "string",
                "description": (
                    "Latest expected COD (YYYY-MM-DD). Default '2028-12-31'. "
                    "Set to null to remove upper bound."
                ),
            },
            "min_lead_score": {
                "type": "integer",
                "description": (
                    "Minimum lead score (0-100). Higher scores = larger, "
                    "nearer-term, solar+storage projects. Use 70+ for "
                    "strong leads, 90+ for top-tier."
                ),
            },
            "sort_by": {
                "type": "string",
                "enum": ["capacity", "lead_score"],
                "description": (
                    "Sort results by 'capacity' (default) or 'lead_score' (highest score first)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 20, max 100).",
            },
        },
    },
}


async def execute(tool_input: dict) -> dict:
    """Search projects in the database."""
    projects = db.search_projects(
        state=tool_input.get("state"),
        iso_region=tool_input.get("iso_region"),
        mw_min=tool_input.get("mw_min"),
        mw_max=tool_input.get("mw_max"),
        developer=tool_input.get("developer"),
        fuel_type=tool_input.get("fuel_type"),
        needs_research=tool_input.get("needs_research"),
        has_epc=tool_input.get("has_epc"),
        search=tool_input.get("search"),
        cod_min=tool_input.get("cod_min", "2025-01-01"),
        cod_max=tool_input.get("cod_max", "2028-12-31"),
        min_lead_score=tool_input.get("min_lead_score"),
        sort_by=tool_input.get("sort_by", "capacity"),
        limit=tool_input.get("limit", 20),
    )
    return {"projects": projects, "count": len(projects)}
