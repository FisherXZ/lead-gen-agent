"""Research planner — generates initial search queries from project context.

Single Haiku call. Returns list of search query strings.
"""

from __future__ import annotations

import json
import logging
import os
import re

import anthropic

logger = logging.getLogger(__name__)

PLAN_MODEL = os.environ.get("PLAN_MODEL", "claude-haiku-4-5-20251001")


PLAN_PROMPT = """\
You are a solar EPC research planner. Given a solar project, generate {n_queries} \
specific Google search queries that would help identify the EPC (Engineering, \
Procurement & Construction) contractor.

## Project
{project_summary}

## Knowledge Base Context
{knowledge_context}

## Rules
- Each query should target a different search angle (developer press release, \
EPC portfolio page, regulatory filing, trade publication, OSHA records, etc.)
- Include the project name, developer name, state, and MW capacity where relevant
- Include terms like "EPC", "construction contractor", "selected to build", \
"awarded contract" to find announcements
- If the KB shows a known developer→EPC relationship, include a verification query
- If the project is early-stage or the developer is a shell company, note this \
and adjust queries accordingly

Respond with a JSON array of search query strings. No markdown fencing:
["query 1", "query 2", "query 3"]
"""


async def llm_plan(
    project: dict,
    knowledge_context: str | None = None,
    api_key: str | None = None,
    n_queries: int = 3,
) -> tuple[list[str], int]:
    """Generate initial search queries for a project. Single cheap LLM call.

    Returns: (queries, tokens_used)
    """
    summary = _format_project_summary(project)
    prompt = PLAN_PROMPT.format(
        n_queries=n_queries,
        project_summary=summary,
        knowledge_context=knowledge_context or "No prior research.",
    )

    try:
        raw, tokens = await _call_llm(prompt, api_key)
        queries = _parse_query_list(raw)
        if queries:
            return queries, tokens
    except Exception as e:
        logger.warning("Planning failed: %s — using fallback queries", e)

    # Fallback: generate basic queries from project fields
    return _fallback_queries(project), 0


def _format_project_summary(project: dict) -> str:
    parts = []
    if project.get("project_name"):
        parts.append(f"Project: {project['project_name']}")
    if project.get("developer"):
        parts.append(f"Developer: {project['developer']}")
    if project.get("mw_capacity"):
        parts.append(f"Capacity: {project['mw_capacity']}MW")
    if project.get("state"):
        parts.append(f"State: {project['state']}")
    if project.get("iso_region"):
        parts.append(f"ISO: {project['iso_region']}")
    return "\n".join(parts) if parts else "Unknown project"


def _parse_query_list(raw: str) -> list[str]:
    """Parse LLM response as JSON array. Handles markdown code blocks."""
    # Try direct parse
    try:
        result = json.loads(raw)
        if isinstance(result, list) and all(isinstance(q, str) for q in result):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting from code block
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    # Try finding any JSON array
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    return []


def _fallback_queries(project: dict) -> list[str]:
    """Generate basic search queries from project fields when LLM fails."""
    name = project.get("project_name", "")
    dev = project.get("developer", "")
    state = project.get("state", "")
    mw = project.get("mw_capacity", "")

    queries = []
    if name and dev:
        queries.append(f"{dev} {name} EPC contractor solar")
    if dev and state:
        queries.append(f"{dev} solar EPC {state}")
    if name and mw:
        queries.append(f"{name} {mw}MW solar construction contractor")

    return queries or [f"{name or dev or 'solar project'} EPC contractor"]


async def _call_llm(prompt: str, api_key: str | None = None) -> tuple[str, int]:
    """Call the cheap planning model. Returns (text, token_count)."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.AsyncAnthropic(api_key=key)
    response = await client.messages.create(
        model=PLAN_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text if response.content else ""
    tokens = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0
    return text, tokens
