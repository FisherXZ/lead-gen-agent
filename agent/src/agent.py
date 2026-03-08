"""Claude agentic loop with tool use for EPC discovery."""

from __future__ import annotations

import asyncio
import json
import os

import anthropic

from .models import AgentResult, EpcSource
from .prompts import SYSTEM_PROMPT, build_user_message
from .tavily_search import search as tavily_search

MAX_ITERATIONS = 10

# Tool definitions for Claude
TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for information about solar project EPC contractors. "
            "Use targeted queries like '[developer] [project name] EPC' or "
            "'site:solarpowerworldonline.com [developer] [state]'. "
            "Returns a list of search results with title, URL, and content snippet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default 5, max 10).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "report_findings",
        "description": (
            "Report your findings after researching the EPC contractor. "
            "Call this EXACTLY ONCE when you are done researching. "
            "You MUST call this even if you found nothing (set confidence to 'unknown')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "epc_contractor": {
                    "type": ["string", "null"],
                    "description": "Name of the EPC contractor, or null if not found.",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["confirmed", "likely", "possible", "unknown"],
                    "description": "Confidence level of the finding.",
                },
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string"},
                            "publication": {"type": ["string", "null"]},
                            "date": {"type": ["string", "null"]},
                            "url": {"type": ["string", "null"]},
                            "excerpt": {"type": "string"},
                            "reliability": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                        },
                        "required": ["channel", "excerpt"],
                    },
                    "description": "Sources found during research.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of how you arrived at this conclusion.",
                },
                "searches_performed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of all searches executed, including dead ends.",
                },
                "related_findings": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Other developer→EPC relationships discovered during research.",
                },
            },
            "required": ["confidence", "reasoning", "searches_performed"],
        },
    },
]


async def run_agent_async(
    project: dict,
    knowledge_context: str | None = None,
) -> tuple[AgentResult, list[dict], int]:
    """Run the EPC discovery agent for a single project (async).

    Args:
        project: Project dict from DB.
        knowledge_context: Optional KB briefing to include in the prompt.

    Returns (result, agent_log, total_tokens).
    """
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    messages = [{"role": "user", "content": build_user_message(project, knowledge_context)}]
    agent_log: list[dict] = []
    total_tokens = 0

    # Mark last tool with cache_control so system + tools are cached
    cached_tools = [*TOOLS[:-1], {**TOOLS[-1], "cache_control": {"type": "ephemeral"}}]

    for iteration in range(MAX_ITERATIONS):
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=cached_tools,
            messages=messages,
        )

        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        agent_log.append({
            "iteration": iteration,
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        })

        # If the model stopped without tool use, we're done (shouldn't happen normally)
        if response.stop_reason == "end_turn":
            # Model finished without calling report_findings — extract text
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return AgentResult(reasoning=text), agent_log, total_tokens

        # Process tool use blocks
        tool_results = []
        report_result: AgentResult | None = None

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "web_search":
                query = block.input.get("query", "")
                max_results = min(block.input.get("max_results", 5), 10)
                agent_log.append({"tool": "web_search", "query": query})

                try:
                    results = tavily_search(query, max_results=max_results)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(results),
                    })
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True,
                    })

            elif block.name == "report_findings":
                inp = block.input
                sources = [
                    EpcSource(
                        channel=s.get("channel", "web_search"),
                        publication=s.get("publication"),
                        date=s.get("date"),
                        url=s.get("url"),
                        excerpt=s.get("excerpt", ""),
                        reliability=s.get("reliability", "medium"),
                    )
                    for s in inp.get("sources", [])
                ]
                report_result = AgentResult(
                    epc_contractor=inp.get("epc_contractor"),
                    confidence=inp.get("confidence", "unknown"),
                    sources=sources,
                    reasoning=inp.get("reasoning", ""),
                    related_leads=inp.get("related_findings", []),
                    searches_performed=inp.get("searches_performed", []),
                )
                # Acknowledge the tool call so the conversation is well-formed
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Findings recorded. Thank you.",
                })

        # If report_findings was called, we're done
        if report_result is not None:
            return report_result, agent_log, total_tokens

        # Feed tool results back and continue the loop
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached — return whatever we have
    return AgentResult(reasoning="Max iterations reached without findings."), agent_log, total_tokens


def run_agent(project: dict) -> tuple[AgentResult, list[dict], int]:
    """Sync wrapper for backward compatibility."""
    return asyncio.run(run_agent_async(project))
