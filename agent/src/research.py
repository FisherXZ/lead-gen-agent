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
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .compaction import compact_messages, estimate_context_size
from .completeness import CHECKPOINTS, evaluate_completeness
from .models import AgentResult, ResearchError
from .parsing import parse_report_findings
from .prompts import PLANNING_SYSTEM_PROMPT, RESEARCH_SYSTEM_PROMPT, build_user_message
from .tools import check_tool_health, execute_tool, get_tools

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 25

# Tools available during standalone research
RESEARCH_TOOLS = [
    "web_search", "web_search_broad", "fetch_page", "query_knowledge_base",
    "notify_progress", "research_scratchpad", "report_findings",
]

# Planning phase: KB + quick web search + notify, no scratchpad or broad search
PLANNING_TOOLS = [
    "web_search", "fetch_page", "query_knowledge_base",
    "notify_progress", "report_findings",
]
MAX_PLANNING_ITERATIONS = 5

logger = logging.getLogger(__name__)


@retry(
    retry=retry_if_exception_type(anthropic.RateLimitError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    reraise=True,
)
async def _call_api(client, **kwargs):
    """Call Anthropic API with automatic retry on rate limits."""
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

    # Track parsed tool results for health checking
    recent_tool_outputs: list[dict] = []

    for iteration in range(MAX_ITERATIONS):
        # Completeness checkpoint (Harvey AI pattern): at iterations 6, 12, 18
        # evaluate what the agent has done and inject guidance into the last
        # tool result.  Gentle → Firm → Mandatory escalation.
        if iteration in CHECKPOINTS and len(messages) > 1:
            check = evaluate_completeness(iteration, agent_log, recent_tool_outputs)
            agent_log.append({"completeness_check": check})
            logger.info(
                "Completeness check at iteration %d: %s (%s)",
                iteration, check["recommendation"], check["level"],
            )
            if check["message"]:
                # Inject into last tool_result message (append-only — preserves KV cache)
                last_msg = messages[-1]
                if (
                    isinstance(last_msg.get("content"), list)
                    and last_msg["content"]
                ):
                    last_msg["content"][-1]["content"] += check["message"]

        try:
            response = await _call_api(
                client,
                model=MODEL,
                max_tokens=4096,
                system=[{
                    "type": "text",
                    "text": RESEARCH_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=cached_tools,
                messages=messages,
            )
        except anthropic.AuthenticationError as exc:
            return AgentResult(
                reasoning="Authentication failed.",
                error=ResearchError(
                    category="api_key_missing",
                    message="Anthropic API key is invalid or missing.",
                    detail=str(exc),
                ),
            ), agent_log, total_tokens
        except anthropic.RateLimitError as exc:
            logger.warning("Rate limit exceeded after 3 retries: %s", exc)
            return AgentResult(
                reasoning="Anthropic API rate limit exceeded after retries.",
                error=ResearchError(
                    category="anthropic_error",
                    message="Rate limit exceeded after 3 retries.",
                    detail=str(exc),
                ),
            ), agent_log, total_tokens
        except anthropic.APIError as exc:
            return AgentResult(
                reasoning=f"Anthropic API error: {exc}",
                error=ResearchError(
                    category="anthropic_error",
                    message=f"Anthropic API error: {type(exc).__name__}",
                    detail=str(exc),
                ),
            ), agent_log, total_tokens

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        agent_log.append({
            "iteration": iteration,
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        })

        # 3d: Model stopped without tool use — end_turn without report_findings
        if response.stop_reason == "end_turn":
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return AgentResult(
                reasoning=text or "Agent stopped without reporting findings.",
                error=ResearchError(
                    category="no_report",
                    message="Agent ended without calling report_findings.",
                ),
            ), agent_log, total_tokens

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
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Findings recorded. Thank you.",
                })
            else:
                # Dispatch to shared tool handler
                try:
                    result = await execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
                    recent_tool_outputs.append(result)
                except Exception as e:
                    error_result = {"error": str(e)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(error_result),
                        "is_error": True,
                    })
                    recent_tool_outputs.append(error_result)

        # If report_findings was called, we're done
        if report_result is not None:
            return report_result, agent_log, total_tokens

        # 3b: Check for consecutive tool errors — if 3+, tell agent to wrap up
        healthy, health_msg = check_tool_health(recent_tool_outputs)
        all_failing = not healthy
        if all_failing and tool_results:
            # Append bail-out instruction to last real tool result
            tool_results[-1]["content"] += (
                f"\n\nSYSTEM WARNING: {health_msg}. Tools are failing repeatedly. "
                "Please call report_findings now with confidence 'unknown' and document what went wrong in reasoning."
            )

        # Feed tool results back and continue
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # Only compact when actually approaching context limits — not every
        # iteration.  Compacting rewrites old messages which breaks KV-cache
        # prefix matching, so each unnecessary compaction costs ~10x more on
        # the conversation portion.  300K chars ≈ 75K tokens, well within
        # Opus's 200K-token window while leaving room for response + next tool.
        if estimate_context_size(messages) > 300_000:
            messages = compact_messages(
                messages,
                max_context_chars=300_000,
                keep_recent_turns=4,
            )

    # 3c: Max iterations reached
    return AgentResult(
        reasoning="Research timed out after maximum iterations.",
        error=ResearchError(
            category="max_iterations",
            message="Research timed out after maximum iterations without completing.",
        ),
    ), agent_log, total_tokens


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
                system=[{
                    "type": "text",
                    "text": PLANNING_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=cached_tools,
                messages=messages,
            )
        except anthropic.APIError as exc:
            return f"Planning failed: {exc}", agent_log, total_tokens

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        agent_log.append({
            "iteration": iteration,
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        })

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
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Plan recorded. Awaiting approval.",
                })
            else:
                try:
                    result = await execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True,
                    })

        if plan_text is not None:
            return plan_text, agent_log, total_tokens

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "Planning timed out — could not produce a plan within iteration limit.", agent_log, total_tokens


