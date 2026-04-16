"""Research agent configuration — autonomous EPC research."""

from __future__ import annotations

from ..config import RUNTIME_MAX_ITERATIONS, RUNTIME_MIN_STAGNATION_ITERATIONS
from ..hooks import CompletenessHook, DiscoveryHook, ToolHealthHook
from ..prompts import RESEARCH_SYSTEM_PROMPT
from ..runtime import AgentRuntime, EscalationPolicy
from ..runtime.compactor import HeuristicCompactor
from ..tools import get_tools

# Canonical research tool set for AgentRuntime-based research.
# The completeness hook handles checkpoint and hard-stop logic that was
# previously inline in the research.py loop.
RESEARCH_TOOL_NAMES = [
    "web_search",
    "web_search_broad",
    "fetch_page",
    "query_knowledge_base",
    "notify_progress",
    "research_scratchpad",
    "report_findings",
    # Structured data source tools
    "search_sec_edgar",
    "fetch_sec_filing",
    "search_osha",
    "search_enr",
    "search_wiki_solar",
    "search_spw",
]


def build_research_runtime(
    project: dict | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[AgentRuntime, CompletenessHook]:
    """Build an AgentRuntime configured for autonomous EPC research.

    Returns (runtime, completeness_hook) so callers can access the hook's
    agent_log and recent_tool_outputs after the run completes (needed for
    salvage extraction on timeout).
    """
    completeness_hook = CompletenessHook()
    runtime = AgentRuntime(
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        tools=get_tools(RESEARCH_TOOL_NAMES),
        hooks=[DiscoveryHook(), ToolHealthHook(), completeness_hook],
        compactor=HeuristicCompactor(max_tokens=60_000, preserve_recent=4),
        escalation=EscalationPolicy(
            max_iterations=RUNTIME_MAX_ITERATIONS,
            escalation_mode="autonomous",
            min_iterations_before_stagnation=RUNTIME_MIN_STAGNATION_ITERATIONS,
        ),
        api_key=api_key,
        model=model,
    )
    return runtime, completeness_hook
