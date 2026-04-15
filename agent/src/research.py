"""Standalone EPC research runner.

Used by:
- POST /api/discover (ResearchButton in frontend)
- batch.py (concurrent batch research)

This is NOT a separate agent — it uses the same shared tools as the chat
agent, but with a focused research-only system prompt and no conversation
context. Think of it as "chat agent in research mode, headless."
"""

from __future__ import annotations

import json
import logging
import os
from uuid import uuid4

import anthropic
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .completeness import CHECKPOINTS, evaluate_completeness
from .models import AgentResult, ResearchError
from .parsing import parse_report_findings
from .prompts import PLANNING_SYSTEM_PROMPT, RESEARCH_SYSTEM_PROMPT, build_user_message
from .salvage import synthesize_timeout_salvage
from .tools import check_tool_health, execute_tool, get_tools
from .triage import triage_project

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 25
# At this iteration, strip all tools except report_findings to force conclusion
HARD_STOP_ITERATION = 22

# Tools available during standalone research
RESEARCH_TOOLS = [
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
) -> tuple[AgentResult, list[dict], int]:
    """Run EPC research for a single project.

    Args:
        project: Project dict from DB.
        knowledge_context: Optional KB briefing to include in the prompt.
        approved_plan: Optional approved research plan text to inject.
        api_key: Optional user-provided Anthropic API key.

    Returns:
        (result, agent_log, total_tokens)
    """
    from .db import get_anthropic_client

    client = get_anthropic_client(api_key)

    session_id = f"research-{project.get('id', 'unknown')}-{uuid4().hex[:8]}"
    user_msg = build_user_message(project, knowledge_context)
    user_msg += f"\n- **Session ID:** {session_id}"
    if approved_plan:
        user_msg += f"\n\n## Approved Research Plan\n{approved_plan}\n\nExecute this plan now."
    messages = [{"role": "user", "content": user_msg}]
    agent_log: list[dict] = []
    total_tokens = 0

    tools = get_tools(RESEARCH_TOOLS)
    # Cache system + last tool for prompt caching (~90% input token savings)
    cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]

    # Triage: classify project before research
    triage = await triage_project(project, api_key)
    if triage.action == "skip":
        return (
            AgentResult(
                reasoning=f"Skipped by triage: {triage.skip_reason}",
                error=ResearchError(
                    category="triaged_skip",
                    message=f"Triage skipped: {triage.skip_reason}",
                ),
            ),
            triage.triage_log,
            triage.tokens_used,
        )
    if triage.corrected_project:
        project = triage.corrected_project

    # Track parsed tool results for health checking
    recent_tool_outputs: list[dict] = []
    # Effective iteration counter — notify_progress-only turns don't count
    effective_iteration = 0
    consecutive_status_only = 0

    for iteration in range(MAX_ITERATIONS):
        # Completeness checkpoint (Harvey AI pattern): at iterations 6, 12, 18
        # evaluate what the agent has done and inject guidance into the last
        # tool result.  Gentle → Firm → Mandatory escalation.
        if effective_iteration in CHECKPOINTS and len(messages) > 1:
            check = evaluate_completeness(effective_iteration, agent_log, recent_tool_outputs)
            agent_log.append({"completeness_check": check})
            logger.info(
                "Completeness check at effective iteration %d (raw %d): %s (%s)",
                effective_iteration,
                iteration,
                check["recommendation"],
                check["level"],
            )
            if check["message"]:
                # Inject into last tool_result message (append-only — preserves KV cache)
                last_msg = messages[-1]
                if isinstance(last_msg.get("content"), list) and last_msg["content"]:
                    last_msg["content"][-1]["content"] += check["message"]

        # Hard stop: at iteration 22+, strip all tools except report_findings
        # to force the agent to conclude. The mandatory checkpoint at 18 is a
        # text nudge the agent can ignore; this is structural — it literally
        # cannot call anything else.
        if effective_iteration >= HARD_STOP_ITERATION or iteration >= MAX_ITERATIONS - 3:
            active_tools = [t for t in cached_tools if t["name"] == "report_findings"]
            hard_stop_msg = (
                "\n\nSYSTEM: You have exhausted your research budget. "
                "The ONLY tool available to you now is report_findings. "
                "Call it immediately with your best assessment."
            )
            # Inject into the last tool result
            if len(messages) > 1:
                last_msg = messages[-1]
                if isinstance(last_msg.get("content"), list) and last_msg["content"]:
                    last_msg["content"][-1]["content"] += hard_stop_msg
        else:
            active_tools = cached_tools

        try:
            response = await _call_api(
                client,
                model=MODEL,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": RESEARCH_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=active_tools,
                messages=messages,
            )
        except anthropic.AuthenticationError as exc:
            return (
                AgentResult(
                    reasoning="Authentication failed.",
                    error=ResearchError(
                        category="api_key_missing",
                        message="Anthropic API key is invalid or missing.",
                        detail=str(exc),
                    ),
                ),
                agent_log,
                total_tokens,
            )
        except anthropic.RateLimitError as exc:
            logger.warning("Rate limit exceeded after 3 retries: %s", exc)
            return (
                AgentResult(
                    reasoning="Anthropic API rate limit exceeded after retries.",
                    error=ResearchError(
                        category="anthropic_error",
                        message="Rate limit exceeded after 3 retries.",
                        detail=str(exc),
                    ),
                ),
                agent_log,
                total_tokens,
            )
        except anthropic.APIError as exc:
            return (
                AgentResult(
                    reasoning=f"Anthropic API error: {exc}",
                    error=ResearchError(
                        category="anthropic_error",
                        message=f"Anthropic API error: {type(exc).__name__}",
                        detail=str(exc),
                    ),
                ),
                agent_log,
                total_tokens,
            )

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        agent_log.append(
            {
                "iteration": iteration,
                "stop_reason": response.stop_reason,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        )

        # 3d: Model stopped without tool use — end_turn without report_findings
        if response.stop_reason == "end_turn":
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return (
                AgentResult(
                    reasoning=text or "Agent stopped without reporting findings.",
                    error=ResearchError(
                        category="no_report",
                        message="Agent ended without calling report_findings.",
                    ),
                ),
                agent_log,
                total_tokens,
            )

        # Process tool use blocks
        tool_results = []
        report_result: AgentResult | None = None

        for block in response.content:
            if block.type != "tool_use":
                continue

            agent_log.append({"tool": block.name, "input": block.input})

            if block.name == "report_findings":
                # Parse structured findings into AgentResult
                report_result = parse_report_findings(block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Findings recorded. Thank you.",
                    }
                )
            else:
                # Dispatch to shared tool handler
                try:
                    result = await execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
                    recent_tool_outputs.append(result)
                except Exception as e:
                    error_result = {"error": str(e)}
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(error_result),
                            "is_error": True,
                        }
                    )
                    recent_tool_outputs.append(error_result)

        # If report_findings was called, we're done
        if report_result is not None:
            return report_result, agent_log, total_tokens

        # Count this turn toward the effective budget only if the agent did
        # real work (search, fetch, KB query, etc.). Turns that only call
        # notify_progress or research_scratchpad are "status-only" and don't
        # count — they waste the iteration budget otherwise.
        tool_names_this_turn = {
            block.name for block in response.content if block.type == "tool_use"
        }
        substantive_tools = tool_names_this_turn - {"notify_progress", "research_scratchpad"}
        if substantive_tools:
            consecutive_status_only = 0
            effective_iteration += 1
        else:
            consecutive_status_only += 1
            if consecutive_status_only >= 3:
                effective_iteration += 1
                consecutive_status_only = 0

        # 3b: Check for consecutive tool errors — if 3+, tell agent to wrap up
        healthy, health_msg = check_tool_health(recent_tool_outputs)
        all_failing = not healthy
        if all_failing and tool_results:
            # Append bail-out instruction to last real tool result
            tool_results[-1]["content"] += (
                f"\n\nSYSTEM WARNING: {health_msg}. Tools are failing repeatedly. "
                "Please call report_findings now with confidence 'unknown' "
                "and document what went wrong in reasoning."
            )

        # Feed tool results back and continue
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # Context compaction is handled by the AgentRuntime in src/agents/research.py.

    # 3c: Max iterations reached — synthesize structured negative evidence
    salvage = synthesize_timeout_salvage(agent_log, project, recent_tool_outputs)
    return (
        AgentResult(
            reasoning={
                "summary": salvage["summary"],
                "supporting_evidence": salvage["supporting_evidence"],
                "gaps": salvage["gaps"],
            },
            confidence="unknown",
            epc_contractor=None,
            sources=salvage["sources"],
            searches_performed=salvage["queries_tried"],
            negative_evidence=salvage["negative_evidence"],
            error=ResearchError(
                category="max_iterations_salvaged",
                message="Hit iteration cap; salvaged structured negative evidence.",
            ),
        ),
        agent_log,
        total_tokens,
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
