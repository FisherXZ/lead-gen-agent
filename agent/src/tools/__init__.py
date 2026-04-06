"""Tool registry — discovers, selects, and dispatches tools.

Usage:
    from .tools import get_all_tools, get_tools, execute_tool

    # All tools (for chat agent)
    tools = get_all_tools()

    # Specific tools (for research runner)
    tools = get_tools(["web_search", "fetch_page", "report_findings"])

    # Execute
    result = await execute_tool("web_search", {"query": "..."})
"""

from __future__ import annotations

from typing import Any

import httpx

from . import (
    approve_discovery,
    batch_research_epc,
    brave_search,
    classify_contact,
    enrich_contact_email,
    enrich_contact_phone,
    export_csv,
    fetch_page,
    fetch_sec_filing,
    find_contacts,
    get_discoveries,
    lookup_hubspot_contacts,
    manage_todo,
    push_to_hubspot,
    notify_progress,
    query_kb,
    recall,
    remember,
    report_findings,
    request_discovery_review,
    request_guidance,
    research_scratchpad,
    search_enr,
    search_exa_people,
    search_linkedin,
    search_osha,
    search_projects,
    search_projects_with_epc,
    search_sec_edgar,
    search_spw,
    search_wiki_solar,
    think,
    web_search,
)

# Registry: name -> module
_REGISTRY: dict[str, Any] = {}


def _register(module: Any) -> None:
    name = module.DEFINITION["name"]
    _REGISTRY[name] = module


# Register all built-in tools
_register(approve_discovery)
_register(batch_research_epc)
_register(web_search)
_register(brave_search)
_register(export_csv)
_register(fetch_page)
_register(fetch_sec_filing)
_register(find_contacts)
_register(push_to_hubspot)
_register(search_projects)
_register(search_projects_with_epc)
_register(get_discoveries)
_register(query_kb)
_register(recall)
_register(remember)
_register(notify_progress)
_register(report_findings)
_register(request_discovery_review)
_register(request_guidance)
_register(research_scratchpad)
# Structured data source tools (Phase 1)
_register(search_sec_edgar)
_register(search_osha)
_register(search_enr)
_register(search_wiki_solar)
_register(search_spw)
# Contact discovery tools
_register(search_exa_people)
_register(search_linkedin)
_register(lookup_hubspot_contacts)
# Contact enrichment tools
_register(enrich_contact_email)
_register(enrich_contact_phone)
# Contact scoring
_register(classify_contact)
# Agent self-management tools
_register(manage_todo)
_register(think)


def get_all_tools() -> list[dict]:
    """Return all tool definitions for the Claude API."""
    return [mod.DEFINITION for mod in _REGISTRY.values()]


def get_tools(names: list[str]) -> list[dict]:
    """Return specific tool definitions by name.

    Raises KeyError if a name is not found.
    """
    return [_REGISTRY[n].DEFINITION for n in names]


def get_tool_names() -> list[str]:
    """Return all registered tool names."""
    return list(_REGISTRY.keys())


async def execute_tool(name: str, tool_input: dict) -> dict:
    """Dispatch to the named tool's execute function.

    Catches common error types and returns structured error dicts.
    Unknown/unexpected exceptions are re-raised.

    If the tool module defines an `Input` Pydantic model, `tool_input` is
    validated against it before dispatch.  On failure a structured
    ``validation_error`` dict is returned.  On success, ``model_dump()`` is
    forwarded so that field defaults are always applied.
    """
    if name not in _REGISTRY:
        raise KeyError(f"Unknown tool: {name}. Available: {list(_REGISTRY.keys())}")

    mod = _REGISTRY[name]

    # Pydantic validation for tools that declare an Input model
    if hasattr(mod, "Input"):
        try:
            from pydantic import ValidationError
            validated = mod.Input(**tool_input)
            tool_input = validated.model_dump()
        except ValidationError as exc:
            return {
                "error": f"Invalid input for {name}: {exc.errors()}",
                "error_category": "validation_error",
            }

    try:
        return await mod.execute(tool_input)
    except KeyError as exc:
        return {
            "error": f"API key not configured for {name}",
            "error_category": "api_key_missing",
            "detail": str(exc),
        }
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"Search service returned {exc.response.status_code}",
            "error_category": "search_tool_error",
            "detail": str(exc),
        }
    except httpx.TimeoutException:
        return {
            "error": f"{name} timed out",
            "error_category": "search_tool_error",
        }
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Unexpected error in tool %s", name)
        return {
            "error": f"Unexpected error in {name}: {type(exc).__name__}",
            "error_category": "tool_error",
            "detail": str(exc),
        }


def check_tool_health(tool_results: list[dict]) -> tuple[bool, str]:
    """Check if last 3+ consecutive tool results all had errors.

    Args:
        tool_results: List of tool result dicts (parsed JSON from content).

    Returns:
        (all_healthy, message) — all_healthy is False if 3+ consecutive errors found.
    """
    consecutive_errors = 0
    last_error = ""
    for result in reversed(tool_results):
        if isinstance(result, dict) and "error" in result:
            consecutive_errors += 1
            if not last_error:
                last_error = result.get("error", "Unknown error")
        else:
            break

    if consecutive_errors >= 3:
        return False, f"{consecutive_errors} consecutive tool errors. Last: {last_error}"
    return True, ""
