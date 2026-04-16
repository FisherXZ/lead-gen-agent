"""Reflector — evaluates evidence and identifies gaps between research rounds.

Single Haiku call per round. Returns ReflectionResult.
"""

from __future__ import annotations

import json
import logging
import os
import re

import anthropic

from ..evidence import EvidenceStore
from ..models import ReflectionResult

logger = logging.getLogger(__name__)

REFLECT_MODEL = os.environ.get("REFLECT_MODEL", "claude-haiku-4-5-20251001")


REFLECT_PROMPT = """\
You are evaluating EPC research evidence for a solar project.

## Project
{project_summary}

## Evidence ({n_findings} findings)
{evidence}

## Searches Performed ({n_searches})
{searches}

## Time Remaining: {minutes_remaining} minutes
{time_warning}

Analyze and respond with JSON (no markdown fencing):
{{"summary": "1-2 sentence assessment", "gaps": ["specific gap 1", "specific gap 2"], \
"should_continue": true/false, "next_search_topic": "concrete search query"}}

Rules:
- should_continue=false if: evidence sufficient, all angles exhausted, or <1 min remains
- gaps must be specific ("No second source confirming McCarthy" not "need more evidence")
- next_search_topic must be a concrete Google search query, not a vague direction
- If candidate EPC found: most valuable gap = verification (scale check, second source)
- If nothing found after 4+ searches: consider project is too early for EPC selection
"""


async def llm_reflect(
    project: dict,
    evidence: EvidenceStore,
    minutes_remaining: float,
    api_key: str | None = None,
) -> ReflectionResult:
    """Evaluate evidence and decide next research step."""
    # Reuse planner's format function
    from .planner import _format_project_summary

    time_warning = (
        "IMPORTANT: Less than 1 minute remains. Set should_continue to false."
        if minutes_remaining < 1.0
        else ""
    )

    prompt = REFLECT_PROMPT.format(
        project_summary=_format_project_summary(project),
        n_findings=len(evidence.findings),
        evidence=evidence.format_for_prompt(),
        n_searches=len(evidence.searches_performed),
        searches="\n".join(f"- {s}" for s in evidence.searches_performed) or "None yet",
        minutes_remaining=f"{minutes_remaining:.1f}",
        time_warning=time_warning,
    )

    try:
        raw, tokens = await _call_llm(prompt, api_key)
        result = _parse_reflection(raw)
        result._tokens_used = tokens  # stash for orchestrator to collect
        return result
    except Exception as e:
        logger.warning("Reflection failed: %s", e)
        r = ReflectionResult(
            summary=f"Reflection failed ({e}), continuing.",
            should_continue=True,
        )
        r._tokens_used = 0
        return r


def _parse_reflection(raw: str) -> ReflectionResult:
    """Parse reflection JSON with 3-level fallback."""
    for attempt in [
        lambda: json.loads(raw),
        lambda: json.loads(
            re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL).group(1)
        ),
        lambda: json.loads(re.search(r"\{[^{}]*\}", raw, re.DOTALL).group(0)),
    ]:
        try:
            data = attempt()
            return ReflectionResult(**data)
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            continue

    return ReflectionResult(summary="Could not parse reflection.", should_continue=True)


async def _call_llm(prompt: str, api_key: str | None = None) -> tuple[str, int]:
    """Returns (text, token_count)."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.AsyncAnthropic(api_key=key)
    response = await client.messages.create(
        model=REFLECT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text if response.content else ""
    tokens = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0
    return text, tokens
