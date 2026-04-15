"""Triage layer v1: classify projects before research.

Addresses two failure buckets from the EPC research queue audit:
- Bucket #1: Utility listed as developer (SCE, PG&E, Entergy, etc.)
- Bucket #2: POI/substation path used as project name ("Reynolds - Olive 345 kV")

Runs BEFORE the iteration loop. Deterministic rules + optional LLM resolution.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta

import anthropic

from .db import get_client
from .models import TriageResult

logger = logging.getLogger(__name__)

# Triage cache TTL: reuse cached result if < 30 days old
CACHE_TTL_DAYS = 30

# ──────────────────────────────────────────────────────────────
# Rule 1: Utility allow-list
# ──────────────────────────────────────────────────────────────

UTILITY_ALLOWLIST = {
    "SCE",
    "SOUTHERN CALIFORNIA EDISON",
    "PGAE",
    "PG&E",
    "PACIFIC GAS & ELECTRIC",
    "PACIFIC GAS AND ELECTRIC",
    "SDGE",
    "SAN DIEGO GAS & ELECTRIC",
    "DCRT",
    "ENTERGY ARKANSAS",
    "ENTERGY LOUISIANA",
    "ENTERGY MISSISSIPPI",
    "ENTERGY TEXAS",
    "ENTERGY NEW ORLEANS",
    "AMEREN ILLINOIS",
    "AMEREN MISSOURI",
    "AMEREN TRANSMISSION COMPANY OF ILLINOIS",
    "AEP",
    "AMERICAN ELECTRIC POWER",
    "AEP INDIANA MICHIGAN",
    "I&M",
    "JCPL",
    "JERSEY CENTRAL POWER & LIGHT",
    "HOOSIER ENERGY",
    "CENTERPOINT ENERGY INDIANA SOUTH",
    "SOUTHERN COMPANY",
    "ALABAMA POWER",
    "GEORGIA POWER",
    "MISSISSIPPI POWER",
    "DOMINION",
    "DOMINION ENERGY",
    "APS",
    "ARIZONA PUBLIC SERVICE",
}


def _is_utility(developer: str | None) -> bool:
    """Check if developer is actually an interconnecting utility."""
    if not developer:
        return False
    normalized = developer.strip().upper()
    return normalized in UTILITY_ALLOWLIST


# ──────────────────────────────────────────────────────────────
# Rule 2: POI regex patterns
# ──────────────────────────────────────────────────────────────

POI_PATTERNS = [
    # "Reynolds - Olive 345 kV"
    re.compile(r"^[\w\s\./&-]+ ?- ?[\w\s\./&-]+ ?\d+(\.\d+)? ?kV$", re.IGNORECASE),
    # "7COFFEEN - 7PANA 345.0kV"
    re.compile(r"^\d+[A-Z]+ ?- ?\d+[A-Z]+ ?\d+(\.\d+)? ?kV$", re.IGNORECASE),
    # "Wheatley 500 kV Switching Station"
    re.compile(r"\d+(\.\d+)? ?kV (Switching Station|Substation|SS)$", re.IGNORECASE),
    # "Taping 'Newport AB / ...' to 'Cash / ...'"
    re.compile(r"^Taping .+ to .+ \d+kV", re.IGNORECASE),
    # "EL DORADO EHV - SAREPTA 345/115 SS 345.0kV"
    re.compile(r"^[\w\s]+ - [\w\s]+ \d+/\d+ SS \d+(\.\d+)? ?kV$", re.IGNORECASE),
]


def _is_poi_name(name: str | None) -> bool:
    """Check if project name is a POI/substation path, not a marketing name."""
    if not name:
        return False
    return any(p.search(name) for p in POI_PATTERNS)


# ──────────────────────────────────────────────────────────────
# Rule 3: Optional LLM name resolution
# ──────────────────────────────────────────────────────────────

_RESOLVE_SYSTEM_PROMPT = """You are a project-name resolver. Your job is to map
an interconnection queue entry (which may use substation names or utility names
as identifiers) to the public marketing name of the underlying solar project
and its real developer.

Rules:
- The "utility" in US interconnection queues (SCE, PG&E, Entergy, Ameren, AEP,
  etc.) is almost never the developer. It's the grid owner at the point of
  interconnection.
- Transmission-line names (e.g., "Reynolds - Olive 345 kV") describe WHERE the
  project connects, not what it's called.
- You have budget for 3 web_search or fetch_page calls total. Use them wisely.
- If you can't find a confident match, return project_name=null and explain.
- Do NOT attempt to find the EPC contractor — that's a separate step."""

_RESOLVE_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for project information.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "resolve_result",
        "description": "Report the resolution result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The public marketing name, or null if unknown",
                },
                "developer": {
                    "type": "string",
                    "description": "The real generation owner, or null",
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "explanation": {"type": "string"},
            },
            "required": ["confidence", "explanation"],
        },
    },
]


async def _resolve_project_name(
    project: dict,
    api_key: str | None = None,
) -> dict:
    """Use a small LLM call to resolve a POI/utility project to its real name.

    Budget: 3 tool calls, 2 iterations, ~2k tokens.
    Returns: {project_name, developer, confidence, sources}
    """
    from .tools import execute_tool

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.AsyncAnthropic(api_key=key)

    name = project.get("project_name", "Unknown")
    state = project.get("state", "Unknown")
    mw = project.get("mw_capacity", "Unknown")
    dev = project.get("developer", "Unknown")

    user_msg = (
        f"Resolve this interconnection queue entry:\n"
        f"- Queue name: {name}\n"
        f"- State: {state}\n"
        f"- MW capacity: {mw}\n"
        f"- Listed developer: {dev}\n\n"
        f"Find the real project marketing name and developer."
    )

    messages = [{"role": "user", "content": user_msg}]
    sources: list[str] = []
    tool_calls_used = 0
    result: dict = {"project_name": None, "developer": None, "confidence": "low", "sources": []}

    for _ in range(2):  # max 2 iterations
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=_RESOLVE_SYSTEM_PROMPT,
                tools=_RESOLVE_TOOLS,
                messages=messages,
            )
        except Exception as e:
            logger.warning("Triage resolve_project_name failed: %s", e)
            return result

        if response.stop_reason == "end_turn":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "resolve_result":
                result = {
                    "project_name": block.input.get("project_name"),
                    "developer": block.input.get("developer"),
                    "confidence": block.input.get("confidence", "low"),
                    "sources": sources,
                }
                return result

            if block.name == "web_search" and tool_calls_used < 3:
                tool_calls_used += 1
                try:
                    search_result = await execute_tool("web_search", block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(search_result)
                            if isinstance(search_result, dict)
                            else str(search_result),
                        }
                    )
                    # Track URLs from results as sources
                    if isinstance(search_result, dict):
                        for r in search_result.get("results", []):
                            if r.get("url"):
                                sources.append(r["url"])
                except Exception as e:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        }
                    )
            else:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Budget exhausted. Call resolve_result now.",
                    }
                )

        if tool_results:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    return result


# ──────────────────────────────────────────────────────────────
# Main triage function
# ──────────────────────────────────────────────────────────────


async def triage_project(
    project: dict,
    api_key: str | None = None,
) -> TriageResult:
    """Classify a project before research.

    Rule evaluation order:
    1. Check cache (reuse if < 30 days)
    2. Utility allow-list match -> mark developer unknown
    3. POI regex match -> mark name_type = poi
    4. If either rule fired -> resolve_project_name (LLM call)
    5. Return action=research (with corrected project) or action=skip
    """
    project_id = project.get("id")
    triage_log: list[dict] = []
    tokens_used = 0

    # Check cache
    if project_id:
        try:
            client = get_client()
            resp = client.table("projects").select("triage_result").eq("id", project_id).execute()
            if resp.data and resp.data[0].get("triage_result"):
                cached = resp.data[0]["triage_result"]
                triaged_at = cached.get("triaged_at")
                if triaged_at:
                    age = datetime.now(UTC) - datetime.fromisoformat(triaged_at)
                    if age < timedelta(days=CACHE_TTL_DAYS):
                        triage_log.append({"rule": "cache_hit", "age_days": age.days})
                        # Defensive: tolerate legacy cache rows with unknown action values
                        cached_action = cached.get("action", "research")
                        if cached_action not in ("research", "skip"):
                            cached_action = "research"
                        return TriageResult(
                            action=cached_action,
                            corrected_project=cached.get("corrected_project"),
                            skip_reason=cached.get("skip_reason"),
                            triage_log=triage_log,
                            tokens_used=0,
                        )
        except Exception as e:
            logger.warning("Triage cache check failed: %s", e)

    # Rule 1: Utility allow-list
    developer = project.get("developer")
    is_utility = _is_utility(developer)
    if is_utility:
        triage_log.append({"rule": "utility_allowlist", "developer": developer})

    # Rule 2: POI regex
    name = project.get("project_name")
    is_poi = _is_poi_name(name)
    if is_poi:
        triage_log.append({"rule": "poi_regex", "name": name})

    # If neither rule fired, pass through
    if not is_utility and not is_poi:
        triage_log.append({"rule": "pass_through"})
        result = TriageResult(action="research", triage_log=triage_log)
        _persist_triage(project_id, result)
        return result

    # Rule 3: Resolve project name
    triage_log.append(
        {"rule": "resolve_project_name", "triggered_by": "utility" if is_utility else "poi"}
    )

    resolution = await _resolve_project_name(project, api_key)
    triage_log.append({"resolution": resolution})

    confidence = resolution.get("confidence", "low")
    resolved_name = resolution.get("project_name")
    resolved_dev = resolution.get("developer")

    if confidence in ("high", "medium") and resolved_name:
        # Build corrected project
        corrected = dict(project)
        corrected["project_name"] = resolved_name
        if resolved_dev:
            corrected["developer"] = resolved_dev
        elif is_utility:
            corrected["developer"] = None

        triage_log.append({"rule": "resolved", "name": resolved_name, "developer": resolved_dev})
        result = TriageResult(
            action="research",
            corrected_project=corrected,
            triage_log=triage_log,
            tokens_used=tokens_used,
        )
    else:
        # Resolution failed
        if is_utility:
            skip_reason = "utility_as_developer_unresolved"
        elif is_poi:
            skip_reason = "poi_name_unresolved"
        else:
            skip_reason = "needs_name_resolution"

        triage_log.append({"rule": "skip", "reason": skip_reason})
        result = TriageResult(
            action="skip",
            skip_reason=skip_reason,
            triage_log=triage_log,
            tokens_used=tokens_used,
        )

    _persist_triage(project_id, result)
    return result


def _persist_triage(project_id: str | None, result: TriageResult) -> None:
    """Cache triage result on the projects table."""
    if not project_id:
        return
    try:
        client = get_client()
        payload = {
            "action": result.action,
            "skip_reason": result.skip_reason,
            "corrected_project": result.corrected_project,
            "triaged_at": datetime.now(UTC).isoformat(),
        }
        client.table("projects").update({"triage_result": payload}).eq("id", project_id).execute()
    except Exception as e:
        logger.warning("Failed to persist triage result: %s", e)
