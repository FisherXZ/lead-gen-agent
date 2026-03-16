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
    export_csv,
    fetch_page,
    fetch_sec_filing,
    get_discoveries,
    notify_progress,
    query_kb,
    recall,
    remember,
    report_findings,
    request_discovery_review,
    request_guidance,
    research_scratchpad,
    search_enr,
    search_osha,
    search_projects,
    search_projects_with_epc,
    search_sec_edgar,
    search_spw,
    search_wiki_solar,
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
    """
    if name not in _REGISTRY:
        raise KeyError(f"Unknown tool: {name}. Available: {list(_REGISTRY.keys())}")
    try:
        return await _REGISTRY[name].execute(tool_input)
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
