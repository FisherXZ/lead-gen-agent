"""Gap-driven research loop v2.

Replaces the linear tool loop with a structured while-loop that
alternates between search rounds and reflection steps. Inspired by
Open Deep Research (gap-as-next-topic mutation) and GPT-Researcher
(recursive depth for verification).

Pipeline per iteration:
  1. Agent makes tool calls (search, fetch, etc.)
  2. Extract findings from tool results into EvidenceStore
  3. Reflection: analyze_and_plan() identifies gaps, decides next topic
  4. If should_continue: inject next_search_topic and loop
  5. If !should_continue: force report_findings and exit
"""

from __future__ import annotations

import json
import logging
import os
import time
from uuid import uuid4

import anthropic
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .evidence import EvidenceStore, extract_findings_from_tool_result
from .models import AgentResult, ResearchError
from .parsing import parse_report_findings
from .prompts import RESEARCH_SYSTEM_PROMPT, build_user_message
from .reflection import analyze_and_plan
from .tools import execute_tool, get_tools

logger = logging.getLogger(__name__)

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-4-6")
MAX_DEPTH = int(os.environ.get("RESEARCH_MAX_DEPTH", "7"))
TIME_BUDGET_MINUTES = float(os.environ.get("RESEARCH_TIME_BUDGET", "4.5"))
MAX_FAILED_ATTEMPTS = 3
MAX_CALLS_PER_ROUND = 6

RESEARCH_TOOLS = [
    "web_search",
    "web_search_broad",
    "fetch_page",
    "query_knowledge_base",
    "notify_progress",
    "research_scratchpad",
    "report_findings",
    "search_sec_edgar",
    "fetch_sec_filing",
    "search_osha",
    "search_enr",
    "search_wiki_solar",
    "search_spw",
]


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
    """Call Anthropic API with retry on transient errors."""
    return await client.messages.create(**kwargs)


async def run_research_loop(
    project: dict,
    knowledge_context: str | None = None,
    approved_plan: str | None = None,
    api_key: str | None = None,
    max_depth: int | None = None,
    time_budget: float | None = None,
    shared_findings: EvidenceStore | None = None,
) -> tuple[AgentResult, list[dict], int]:
    """Run gap-driven EPC research for a single project.

    The loop alternates between:
    1. A search round (agent calls tools, we extract findings)
    2. A reflection step (cheap model evaluates gaps, decides next topic)

    Stops when: reflection says stop, max_depth reached, time expired,
    or report_findings is called.

    Args:
        shared_findings: Optional cross-project evidence store for batch mode.
            When provided, this project's local store is seeded from it at start,
            and local findings are propagated back at end. Enables concurrent
            batch research tasks to share discoveries (e.g., "developer X uses
            EPC Y" found by project A benefits project B).

    Returns:
        (result, agent_log, total_tokens) — same contract as run_research().
    """
    from .db import get_anthropic_client

    client = get_anthropic_client(api_key)
    effective_max_depth = max_depth if max_depth is not None else MAX_DEPTH
    effective_time_budget = time_budget if time_budget is not None else TIME_BUDGET_MINUTES
    start_time = time.time()
    deadline = start_time + (effective_time_budget * 60)

    session_id = f"research-{project.get('id', 'unknown')}-{uuid4().hex[:8]}"
    evidence = EvidenceStore()

    # Seed local evidence from shared store (batch mode: benefits from sibling discoveries)
    if shared_findings is not None:
        for finding in shared_findings.findings:
            evidence.add(finding)

    agent_log: list[dict] = []
    total_tokens = 0
    failed_attempts = 0

    async def _propagate_findings() -> None:
        """Push this project's findings back to the shared store (batch mode)."""
        if shared_findings is None:
            return
        for finding in evidence.findings:
            await shared_findings.add_async(finding)

    user_msg = build_user_message(project, knowledge_context)
    user_msg += f"\n- **Session ID:** {session_id}"
    if approved_plan:
        user_msg += f"\n\n## Approved Research Plan\n{approved_plan}\n\nExecute this plan now."

    messages: list[dict] = [{"role": "user", "content": user_msg}]

    tools = get_tools(RESEARCH_TOOLS)
    cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]

    for depth in range(effective_max_depth):
        minutes_remaining = (deadline - time.time()) / 60
        if minutes_remaining < 0.5:
            logger.info("Time budget exhausted at depth %d", depth)
            break

        # ── Search round ──
        report_result, round_tokens, round_failed = await _run_search_round(
            client=client,
            messages=messages,
            cached_tools=cached_tools,
            evidence=evidence,
            agent_log=agent_log,
            max_calls=MAX_CALLS_PER_ROUND,
            depth=depth,
        )
        total_tokens += round_tokens
        failed_attempts += round_failed

        if report_result is not None:
            await _propagate_findings()
            return report_result, agent_log, total_tokens

        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            logger.warning("Too many failed attempts (%d), forcing wrap-up", failed_attempts)
            break

        # ── Reflection ──
        minutes_remaining = (deadline - time.time()) / 60
        reflection = await analyze_and_plan(
            project=project,
            evidence=evidence,
            minutes_remaining=minutes_remaining,
            api_key=api_key,
        )

        agent_log.append({
            "type": "reflection",
            "depth": depth,
            "summary": reflection.summary,
            "gaps": reflection.gaps,
            "should_continue": reflection.should_continue,
            "next_search_topic": reflection.next_search_topic,
            "findings_count": len(evidence.findings),
            "minutes_remaining": round(minutes_remaining, 1),
        })

        if not reflection.should_continue or not reflection.gaps:
            logger.info("Reflection says stop at depth %d: %s", depth, reflection.summary)
            # Force report_findings
            report_result, round_tokens, _ = await _force_report(
                client=client,
                messages=messages,
                cached_tools=cached_tools,
                evidence=evidence,
                agent_log=agent_log,
                reflection_summary=reflection.summary,
            )
            total_tokens += round_tokens
            if report_result is not None:
                await _propagate_findings()
                return report_result, agent_log, total_tokens
            break

        # Gap-as-next-topic mutation (from Open Deep Research)
        next_topic = reflection.next_search_topic or reflection.gaps[0]
        messages.append({
            "role": "user",
            "content": (
                f"[Research guidance: {reflection.summary}\n"
                f"Gaps remaining: {', '.join(reflection.gaps)}\n"
                f"Next search focus: {next_topic}\n"
                f"Time remaining: {minutes_remaining:.1f} minutes.\n"
                f"Evidence so far:\n{evidence.format_for_prompt()}]"
            ),
        })

    # Exhausted depth/time without report_findings
    await _propagate_findings()
    return (
        AgentResult(
            reasoning=f"Research exhausted iteration budget ({effective_max_depth} rounds). "
            f"Collected {len(evidence.findings)} findings across "
            f"{len(evidence.searches_performed)} searches.",
            searches_performed=evidence.searches_performed,
            error=ResearchError(
                category="max_iterations",
                message="Research exhausted iteration budget without completing report.",
            ),
        ),
        agent_log,
        total_tokens,
    )


async def _run_search_round(
    client,
    messages: list[dict],
    cached_tools: list[dict],
    evidence: EvidenceStore,
    agent_log: list[dict],
    max_calls: int = 6,
    depth: int = 0,
) -> tuple[AgentResult | None, int, int]:
    """Run one search round: agent makes tool calls until end_turn or limit.

    Returns (AgentResult if report_findings called, round_tokens, failed_count).
    """
    round_tokens = 0
    failed_count = 0

    for _ in range(max_calls):
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
            return (
                AgentResult(
                    reasoning="Authentication failed.",
                    error=ResearchError(
                        category="api_key_missing",
                        message="Anthropic API key is invalid or missing.",
                        detail=str(exc),
                    ),
                ),
                round_tokens,
                failed_count,
            )
        except anthropic.RateLimitError as exc:
            logger.warning("Rate limit exceeded after retries: %s", exc)
            return (
                AgentResult(
                    reasoning="Anthropic API rate limit exceeded after retries.",
                    error=ResearchError(
                        category="anthropic_error",
                        message="Rate limit exceeded after retries.",
                        detail=str(exc),
                    ),
                ),
                round_tokens,
                failed_count,
            )
        except anthropic.APIError as exc:
            return (
                AgentResult(
                    reasoning=f"Anthropic API error: {exc}",
                    error=ResearchError(
                        category="anthropic_error",
                        message=f"API error: {type(exc).__name__}",
                        detail=str(exc),
                    ),
                ),
                round_tokens,
                failed_count,
            )

        round_tokens += response.usage.input_tokens + response.usage.output_tokens
        agent_log.append({
            "type": "api_call",
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        })

        # End turn — round is done
        if response.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": response.content})
            return None, round_tokens, failed_count

        # Extract tool calls
        tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            messages.append({"role": "assistant", "content": response.content})
            return None, round_tokens, failed_count

        # Process tool calls
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        report_result = None

        for block in tool_uses:
            agent_log.append({"type": "tool_call", "tool": block.name, "input": block.input})

            if block.name == "report_findings":
                report_result = parse_report_findings(block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Findings recorded.",
                })
            else:
                try:
                    result = await execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
                    extract_findings_from_tool_result(
                        block.name, block.input, result, evidence, iteration=depth,
                    )
                except Exception as e:
                    failed_count += 1
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True,
                    })

        if report_result is not None:
            return report_result, round_tokens, failed_count

        messages.append({"role": "user", "content": tool_results})

    return None, round_tokens, failed_count


async def _force_report(
    client,
    messages: list[dict],
    cached_tools: list[dict],
    evidence: EvidenceStore,
    agent_log: list[dict],
    reflection_summary: str,
) -> tuple[AgentResult | None, int, int]:
    """Inject guidance and give the agent one round to call report_findings."""
    messages.append({
        "role": "user",
        "content": (
            f"[Research guidance: {reflection_summary} "
            "Call report_findings now with your best assessment. "
            f"Evidence summary:\n{evidence.format_for_prompt()}]"
        ),
    })
    report_tools = [t for t in cached_tools if t["name"] == "report_findings"]
    return await _run_search_round(
        client=client,
        messages=messages,
        cached_tools=report_tools,
        evidence=evidence,
        agent_log=agent_log,
        max_calls=2,
    )
