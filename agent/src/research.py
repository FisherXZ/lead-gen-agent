"""Standalone EPC research runner.

Used by:
- POST /api/discover (ResearchButton in frontend)
- batch.py (concurrent batch research)

This is NOT a separate agent — it uses the same shared tools as the chat
agent, but with a focused research-only system prompt and no conversation
context. Think of it as "chat agent in research mode, headless."

The research loop itself lives in v3/orchestrator.py (procedural v3 loop).
This module exposes the public run_research() API plus the planning-only
run_research_plan() variant.
"""

from __future__ import annotations

import json
import logging
import os

import anthropic
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .models import AgentResult
from .prompts import PLANNING_SYSTEM_PROMPT, build_user_message
from .research_loop import RESEARCH_TOOLS  # keep for backward compat export
from .tools import execute_tool, get_tools
from .v3.orchestrator import run_research_v3

# Re-export RESEARCH_TOOLS so consumers importing from src.research continue to work
__all__ = ["run_research", "run_research_plan", "RESEARCH_TOOLS", "PLANNING_TOOLS", "MODEL"]

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-4-6")

# Planning phase: KB + quick web/structured search + notify, no scratchpad or broad search
PLANNING_TOOLS = [
    "web_search",
    "fetch_page",
    "query_knowledge_base",
    "search_sec_edgar",
    "search_wiki_solar",
    "search_spw",
    "notify_progress",
    "report_findings",
]
MAX_PLANNING_ITERATIONS = 5

logger = logging.getLogger(__name__)


@retry(
    retry=retry_if_exception(
        lambda e: (
            isinstance(e, (anthropic.RateLimitError, anthropic.APIStatusError))
            and not isinstance(e, anthropic.AuthenticationError)
        )
    ),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
    before_sleep=lambda rs: logging.getLogger(__name__).warning(
        "API retry #%d: %s", rs.attempt_number, rs.outcome.exception()
    ),
)
async def _call_api(client, **kwargs):
    """Call Anthropic API with automatic retry on transient errors."""
    return await client.messages.create(**kwargs)


async def run_research(
    project: dict,
    knowledge_context: str | None = None,
    approved_plan: str | None = None,
    api_key: str | None = None,
    shared_findings=None,
) -> tuple[AgentResult, list[dict], int]:
    """Run EPC research for a single project.

    Delegates to the v3 procedural research loop. See v3/orchestrator.py
    for the loop implementation.

    Args:
        project: Project dict from DB.
        knowledge_context: Optional KB briefing to include in the prompt.
        approved_plan: Optional approved research plan text to inject.
        api_key: Optional user-provided Anthropic API key.
        shared_findings: Optional EvidenceStore shared across sibling batch
            research tasks. When provided, findings from other projects in
            the same batch seed this project, and its findings are propagated
            back on completion.

    Returns:
        (result, agent_log, total_tokens)
    """
    return await run_research_v3(
        project=project,
        knowledge_context=knowledge_context,
        approved_plan=approved_plan,
        api_key=api_key,
        shared_findings=shared_findings,
    )


async def run_research_plan(
    project: dict,
    knowledge_context: str | None = None,
    api_key: str | None = None,
) -> tuple[str, list[dict], int]:
    """Generate a research plan for a project WITHOUT executing full research.

    The agent can do 1-2 quick web searches to inform the plan, but its primary
    job is to propose a strategy, not find the EPC.

    Args:
        project: Project dict from DB.
        knowledge_context: Optional KB briefing to include in the prompt.
        api_key: Optional user-provided Anthropic API key.

    Returns:
        (plan_text, agent_log, total_tokens)
    """
    from .db import get_anthropic_client

    client = get_anthropic_client(api_key)

    user_msg = build_user_message(project, knowledge_context)
    messages = [{"role": "user", "content": user_msg}]
    agent_log: list[dict] = []
    total_tokens = 0

    tools = get_tools(PLANNING_TOOLS)
    cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]

    for iteration in range(MAX_PLANNING_ITERATIONS):
        try:
            response = await _call_api(
                client,
                model=MODEL,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": PLANNING_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=cached_tools,
                messages=messages,
            )
        except anthropic.APIError as exc:
            return f"Planning failed: {exc}", agent_log, total_tokens

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        agent_log.append(
            {
                "iteration": iteration,
                "stop_reason": response.stop_reason,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        )

        if response.stop_reason == "end_turn":
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return text or "Agent stopped without producing a plan.", agent_log, total_tokens

        # Process tool use
        tool_results = []
        plan_text: str | None = None

        for block in response.content:
            if block.type != "tool_use":
                continue
            agent_log.append({"tool": block.name, "input": block.input})

            if block.name == "report_findings":
                # The plan is in the reasoning field
                raw_reasoning = block.input.get("reasoning", "")
                if isinstance(raw_reasoning, dict):
                    plan_text = raw_reasoning.get("summary", "")
                    evidence = raw_reasoning.get("supporting_evidence", [])
                    if evidence:
                        plan_text += "\n\n" + "\n".join(f"- {e}" for e in evidence)
                else:
                    plan_text = raw_reasoning
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Plan recorded. Awaiting approval.",
                    }
                )
            else:
                try:
                    result = await execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
                except Exception as e:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        }
                    )

        if plan_text is not None:
            return plan_text, agent_log, total_tokens

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return (
        "Planning timed out — could not produce a plan within iteration limit.",
        agent_log,
        total_tokens,
    )
