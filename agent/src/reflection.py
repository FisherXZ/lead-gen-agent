"""Reflection step for the research loop.

After each search round, evaluates evidence, identifies gaps,
and decides the next search topic. Uses a cheap/fast model
to keep costs low — this runs every iteration.
"""

from __future__ import annotations

import json
import logging
import os
import re

import anthropic

from .evidence import EvidenceStore
from .models import ReflectionResult
from .prompts import REFLECTION_PROMPT

logger = logging.getLogger(__name__)

REFLECTION_MODEL = os.environ.get("REFLECTION_MODEL", "claude-haiku-4-5-20251001")


async def analyze_and_plan(
    project: dict,
    evidence: EvidenceStore,
    minutes_remaining: float,
    api_key: str | None = None,
) -> ReflectionResult:
    """Run the reflection step: evaluate evidence, identify gaps, decide next topic.

    Returns a ReflectionResult. On LLM failure, returns a default "continue" result.
    """
    project_summary = _format_project_summary(project)
    time_warning = (
        "IMPORTANT: Less than 1 minute remains. Set should_continue to false."
        if minutes_remaining < 1.0
        else ""
    )

    prompt = REFLECTION_PROMPT.format(
        project_summary=project_summary,
        evidence=evidence.format_for_prompt(),
        searches="\n".join(f"- {s}" for s in evidence.searches_performed) or "None yet",
        minutes_remaining=f"{minutes_remaining:.1f}",
        time_warning=time_warning,
    )

    try:
        raw = await _call_reflection_llm(prompt, api_key)
        return _parse_reflection(raw)
    except Exception as e:
        logger.warning("Reflection step failed: %s — defaulting to continue", e)
        return ReflectionResult(
            summary=f"Reflection failed ({e}), continuing research.",
            gaps=["Reflection step failed — continue with current approach"],
            should_continue=True,
        )


def _format_project_summary(project: dict) -> str:
    """One-line project summary for the reflection prompt."""
    parts = []
    if project.get("project_name"):
        parts.append(project["project_name"])
    if project.get("developer"):
        parts.append(f"Developer: {project['developer']}")
    if project.get("mw_capacity"):
        parts.append(f"{project['mw_capacity']}MW")
    if project.get("state"):
        parts.append(project["state"])
    return " | ".join(parts) if parts else "Unknown project"


def _parse_reflection(raw: str) -> ReflectionResult:
    """Parse LLM output into ReflectionResult. Handles malformed JSON gracefully."""
    # Try direct parse
    try:
        data = json.loads(raw)
        return ReflectionResult(**data)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Try extracting JSON from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return ReflectionResult(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Try finding any JSON object in the text
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return ReflectionResult(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # All parsing failed — return a safe default
    logger.warning("Could not parse reflection output, defaulting to continue")
    return ReflectionResult(
        summary="Could not parse reflection — continuing research.",
        should_continue=True,
    )


async def _call_reflection_llm(prompt: str, api_key: str | None = None) -> str:
    """Call the cheap reflection model. Separated for testability."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.AsyncAnthropic(api_key=key)

    response = await client.messages.create(
        model=REFLECTION_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text if response.content else ""
