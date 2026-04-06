"""Research agent configuration — autonomous EPC research."""

from __future__ import annotations

from ..hooks import DiscoveryHook, ToolHealthHook
from ..prompts import RESEARCH_SYSTEM_PROMPT
from ..runtime import AgentRuntime, Compactor, EscalationPolicy
from ..tools import get_tools

RESEARCH_TOOL_NAMES = [
    "web_search",
    "web_search_broad",
    "fetch_page",
    "search_sec_edgar",
    "fetch_sec_filing",
    "search_osha",
    "search_enr",
    "search_wiki_solar",
    "search_spw",
    "query_knowledge_base",
    "remember",
    "recall",
    "manage_todo",
    "think",
    "notify_progress",
    "research_scratchpad",
    "report_findings",
]


def build_research_runtime(
    project: dict,
    api_key: str | None = None,
    model: str | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        tools=get_tools(RESEARCH_TOOL_NAMES),
        hooks=[DiscoveryHook(), ToolHealthHook()],
        compactor=Compactor(max_tokens=60_000, preserve_recent=4, api_key=api_key),
        escalation=EscalationPolicy(
            max_iterations=30, escalation_mode="autonomous", min_iterations_before_stagnation=6
        ),
        api_key=api_key,
        model=model,
    )
