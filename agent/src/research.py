"""Research planning — lightweight plan generation for EPC discovery.

The main research loop has been migrated to AgentRuntime
(see agents/research.py + build_research_runtime). This module retains
only ``run_research_plan`` which is still used by the ``/api/discover/plan``
endpoint in main.py.
"""

from __future__ import annotations

import json
import logging

import anthropic
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import (
    MAX_PLANNING_ITERATIONS,
    RESEARCH_MODEL as MODEL,
)
from .prompts import PLANNING_SYSTEM_PROMPT
from .tools import execute_tool, get_tools

logger = logging.getLogger(__name__)

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
    from .prompts import build_user_message

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
