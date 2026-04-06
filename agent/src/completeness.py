"""Completeness evaluation for EPC research (Harvey AI pattern).

At checkpoint iterations (6, 12, 18), evaluates what the agent has done
so far and produces a message to inject into the conversation. Uses
deterministic heuristics on tool call patterns — no extra LLM call needed.

Three escalation levels:
- Iteration 6:  Gentle — "have you completed Phase 2?"
- Iteration 12: Firm   — "diminishing returns, you SHOULD wrap up"
- Iteration 18: Mandatory — "you MUST call report_findings now"
"""

from __future__ import annotations

import re

# Top 10 EPC domains for portfolio check detection
_EPC_DOMAINS = {
    "mccarthybuilding.com",
    "mortenson.com",
    "blattnerenergy.com",
    "signalenergy.com",
    "rosendin.com",
    "solvenergyus.com",
    "stratacleane.com",
    "sundtconstruction.com",
    "primoris.com",
    "maborenewables.com",
}

# Checkpoint iterations and their escalation level
CHECKPOINTS: dict[int, str] = {
    6: "gentle",
    12: "firm",
    18: "mandatory",
}


def evaluate_completeness(
    iteration: int,
    agent_log: list[dict],
    recent_tool_outputs: list[dict],
) -> dict:
    """Evaluate research completeness at a checkpoint iteration.

    Args:
        iteration: Current loop iteration (0-indexed).
        agent_log: Full agent log (tool calls + API responses).
        recent_tool_outputs: Parsed tool result dicts from the run so far.

    Returns:
        {
            "iteration": int,
            "level": "gentle" | "firm" | "mandatory",
            "search_count": int,
            "fetch_count": int,
            "portfolio_checks": int,
            "kb_consulted": bool,
            "new_signals_in_last_n": bool,
            "error_rate": float,
            "recommendation": "continue" | "switch_strategy" | "wrap_up",
            "message": str | None,
        }
    """
    level = CHECKPOINTS.get(iteration, "gentle")

    # --- Gather metrics from agent_log ---
    search_count = 0
    fetch_count = 0
    portfolio_checks = 0
    kb_consulted = False
    all_queries: list[str] = []

    for entry in agent_log:
        tool = entry.get("tool")
        tool_input = entry.get("input", {})

        if tool in ("web_search", "web_search_broad"):
            search_count += 1
            query = tool_input.get("query", "")
            all_queries.append(query)
            # Check for EPC portfolio site: queries
            if _is_portfolio_check(query):
                portfolio_checks += 1

        elif tool == "fetch_page":
            fetch_count += 1
            url = tool_input.get("url", "")
            if _is_epc_domain(url):
                portfolio_checks += 1

        elif tool == "query_knowledge_base":
            kb_consulted = True

    # --- Check for new signals in recent outputs ---
    # Look at last 4 tool outputs for anything that isn't an error or empty
    lookback = min(4, len(recent_tool_outputs))
    recent = recent_tool_outputs[-lookback:] if lookback > 0 else []
    new_signals = _has_new_signals(recent)

    # --- Error rate ---
    error_count = sum(1 for r in recent_tool_outputs if isinstance(r, dict) and "error" in r)
    error_rate = error_count / max(len(recent_tool_outputs), 1)

    # --- Determine recommendation ---
    recommendation, message = _build_recommendation(
        level=level,
        iteration=iteration,
        search_count=search_count,
        fetch_count=fetch_count,
        portfolio_checks=portfolio_checks,
        kb_consulted=kb_consulted,
        new_signals=new_signals,
        error_rate=error_rate,
        all_queries=all_queries,
    )

    return {
        "iteration": iteration,
        "level": level,
        "search_count": search_count,
        "fetch_count": fetch_count,
        "portfolio_checks": portfolio_checks,
        "kb_consulted": kb_consulted,
        "new_signals_in_last_n": new_signals,
        "error_rate": round(error_rate, 2),
        "recommendation": recommendation,
        "message": message,
    }


def _build_recommendation(
    *,
    level: str,
    iteration: int,
    search_count: int,
    fetch_count: int,
    portfolio_checks: int,
    kb_consulted: bool,
    new_signals: bool,
    error_rate: float,
    all_queries: list[str],
) -> tuple[str, str | None]:
    """Build the recommendation and checkpoint message.

    Returns (recommendation, message). message is None if no injection needed.
    """

    # --- Iteration 6: Gentle ---
    if level == "gentle":
        gaps = []
        if portfolio_checks < 2:
            gaps.append(
                f"You have checked {portfolio_checks} EPC portfolio sites. "
                "Phase 2 requires at least 3 (e.g., site:mccarthybuilding.com, "
                "site:mortenson.com, site:blattnerenergy.com)."
            )
        if not kb_consulted:
            gaps.append(
                "You have not consulted the knowledge base yet. "
                "Use query_knowledge_base to check for known developer→EPC relationships."
            )

        if not gaps and new_signals:
            # Research is on track — no message needed
            return "continue", None

        if not gaps and not new_signals:
            return "switch_strategy", (
                f"\n\nRESEARCH CHECKPOINT (iteration {iteration + 1} of {25}):\n"
                f"Searches: {search_count} | Pages read: {fetch_count} | "
                f"Portfolio checks: {portfolio_checks} | KB consulted: {kb_consulted}\n"
                "Your recent searches haven't surfaced new EPC-specific information. "
                "Consider switching to a different strategy — try Phase 2 (EPC portfolio sweep) "
                "or Phase 3 (trade publications, Brave search) before reporting unknown."
            )

        # Has gaps
        return "switch_strategy", (
            f"\n\nRESEARCH CHECKPOINT (iteration {iteration + 1} of {25}):\n"
            f"Searches: {search_count} | Pages read: {fetch_count} | "
            f"Portfolio checks: {portfolio_checks} | KB consulted: {kb_consulted}\n"
            "Gaps detected:\n- " + "\n- ".join(gaps) + "\n"
            "Please address these gaps before reporting findings."
        )

    # --- Iteration 12: Firm ---
    if level == "firm":
        if new_signals:
            # Still finding new info — let it continue but note the checkpoint
            return "continue", (
                f"\n\nRESEARCH CHECKPOINT (iteration {iteration + 1} of {25}):\n"
                f"Searches: {search_count} | Pages read: {fetch_count} | "
                f"Portfolio checks: {portfolio_checks} | KB consulted: {kb_consulted}\n"
                "You are still finding new information. You may continue, but "
                "you SHOULD call report_findings soon with your best assessment. "
                "You have used {:.0f}% of your iteration budget.".format((iteration + 1) / 25 * 100)
            )

        # No new signals — firm wrap-up
        return "wrap_up", (
            f"\n\nRESEARCH CHECKPOINT (iteration {iteration + 1} of {25}):\n"
            f"Searches: {search_count} | Pages read: {fetch_count} | "
            f"Portfolio checks: {portfolio_checks} | KB consulted: {kb_consulted}\n"
            "Diminishing returns detected — your recent searches have not surfaced "
            "new EPC-specific information. You SHOULD call report_findings now "
            "with your best assessment. An honest 'unknown' after a thorough search "
            "is the correct outcome. Do not continue searching without a new strategy."
        )

    # --- Iteration 18: Mandatory ---
    if level == "mandatory":
        return "wrap_up", (
            f"\n\nRESEARCH CHECKPOINT — MANDATORY WRAP-UP (iteration {iteration + 1} of {25}):\n"
            f"Searches: {search_count} | Pages read: {fetch_count} | "
            f"Portfolio checks: {portfolio_checks} | KB consulted: {kb_consulted}\n"
            "You have used 76% of your iteration budget. You MUST call report_findings "
            "on your next response. Report what you have found so far — confirmed, likely, "
            "possible, or unknown. Continuing to search is not an option. "
            "Include all searches performed and any negative evidence in your report."
        )

    return "continue", None


def _is_portfolio_check(query: str) -> bool:
    """Detect if a search query is an EPC portfolio site: check."""
    query_lower = query.lower()
    if "site:" not in query_lower:
        return False
    for domain in _EPC_DOMAINS:
        if domain in query_lower:
            return True
    return False


def _is_epc_domain(url: str) -> bool:
    """Check if a URL belongs to a known EPC company domain."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _EPC_DOMAINS)


def _has_new_signals(recent_outputs: list[dict]) -> bool:
    """Check if recent tool outputs contain new EPC-relevant information.

    Looks for:
    - Non-empty, non-error results
    - Mentions of EPC-related terms in result content
    """
    epc_pattern = re.compile(
        r"(epc|contractor|construction|built|building|awarded|selected|"
        r"engineering.procurement|general\s*contractor)",
        re.IGNORECASE,
    )

    signal_count = 0
    for output in recent_outputs:
        if not isinstance(output, dict):
            continue
        if "error" in output:
            continue

        # Check if result has meaningful content
        content = str(output)
        if len(content) < 50:
            continue

        # Look for EPC-relevant terms
        if epc_pattern.search(content):
            signal_count += 1

    # At least 1 out of last 4 results should have new signals
    return signal_count >= 1
