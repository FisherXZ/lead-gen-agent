"""Synthesizer — produces final AgentResult from evidence.

Single Sonnet call using Anthropic structured output (messages.parse).
Guaranteed schema compliance via constrained decoding.
"""

from __future__ import annotations

import logging
import os

import anthropic
from pydantic import BaseModel

from ..confidence import compute_confidence_upgrade
from ..evidence import EvidenceStore
from ..models import AgentResult, EpcSource, NegativeEvidence

logger = logging.getLogger(__name__)

SYNTHESIS_MODEL = os.environ.get("SYNTHESIS_MODEL", "claude-sonnet-4-6")


SYNTHESIS_PROMPT = """\
You are synthesizing EPC research findings for a solar project into a structured report.

## Project
{project_summary}

## Evidence Collected ({n_findings} findings from {n_searches} searches)
{evidence}

## Searches Performed
{searches}

## Research Reflection Trail
{reflection_trail}

## Instructions
Based on the evidence above, produce a structured assessment of the EPC contractor \
for this project. Be honest: if evidence is insufficient, report confidence="unknown" \
rather than guessing.

For the reasoning field, use this structure:
- summary: 1-2 sentences stating your conclusion. Cite sources as [1], [2] etc.
- supporting_evidence: Key evidence points, strongest first
- gaps: What's missing or uncertain

For sources, only include sources that DIRECTLY support your EPC determination. \
Each source must have a real URL from the evidence, a channel classification, \
and a reliability rating.

For negative_evidence: Document searches that found nothing or contradictory info. \
Use the reflection trail above to identify dead-end searches. For each, record:
- search_query: the query that was tried
- expected_to_find: what you hoped to find
- what_was_found: "nothing", "contradictory", "different_epc", or "different_project"
This helps reviewers understand what was tried and why the confidence level was set.

For confidence:
- confirmed: 2+ independent sources, at least one first-party
- likely: 1 reliable source specifically naming EPC for THIS project
- possible: Indirect evidence only
- unknown: No project-specific EPC evidence after thorough search

An honest "unknown" after thorough research is better than an unverified guess.
"""


class _SynthesisResult(BaseModel):
    """Internal model for structured output — uses str-only fields for constrained decoding.

    AgentResult.reasoning is typed str | dict which can confuse constrained decoding.
    We parse into this clean model and convert to AgentResult afterwards.
    """

    epc_contractor: str | None = None
    confidence: str = "unknown"
    sources: list[EpcSource] = []
    reasoning: str = ""
    searches_performed: list[str] = []
    negative_evidence: list[NegativeEvidence] = []


async def llm_synthesize(
    project: dict,
    evidence: EvidenceStore,
    api_key: str | None = None,
    reflection_trail: list[dict] | None = None,
) -> tuple[AgentResult, int]:
    """Synthesize final AgentResult from evidence. ONE Sonnet structured-output call.

    Args:
        reflection_trail: List of reflection log entries from the orchestrator.
            Passed to the synthesis prompt so the LLM can generate negative_evidence
            from the gaps and dead ends documented during research.

    Returns: (AgentResult, tokens_used)
    """
    from .planner import _format_project_summary

    # Format reflection trail for the prompt
    trail_text = "No reflections recorded."
    if reflection_trail:
        lines = []
        for r in reflection_trail:
            lines.append(f"Round {r.get('depth', '?')}: {r.get('summary', '?')}")
            for gap in r.get("gaps", []):
                lines.append(f"  Gap: {gap}")
            if r.get("next_search_topic"):
                lines.append(f"  → Searched: {r['next_search_topic']}")
        trail_text = "\n".join(lines)

    prompt = SYNTHESIS_PROMPT.format(
        project_summary=_format_project_summary(project),
        n_findings=len(evidence.findings),
        n_searches=len(evidence.searches_performed),
        evidence=evidence.format_for_prompt(),
        searches="\n".join(f"- {s}" for s in evidence.searches_performed) or "None",
        reflection_trail=trail_text,
    )

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.AsyncAnthropic(api_key=key)

    try:
        response = await client.messages.parse(
            model=SYNTHESIS_MODEL,
            max_tokens=4096,
            output_format=_SynthesisResult,
            messages=[{"role": "user", "content": prompt}],
        )
        # Anthropic SDK v0.84.0: ParsedMessage exposes structured result via `parsed_output`
        parsed = response.parsed_output
        synth_tokens = (
            (response.usage.input_tokens + response.usage.output_tokens)
            if response.usage else 0
        )

        # Convert _SynthesisResult -> AgentResult
        result = AgentResult(
            epc_contractor=parsed.epc_contractor,
            confidence=parsed.confidence,
            sources=parsed.sources,
            reasoning=parsed.reasoning,
            searches_performed=parsed.searches_performed or evidence.searches_performed,
            negative_evidence=parsed.negative_evidence,
        )
    except Exception as e:
        logger.error("Structured synthesis failed: %s", e)
        from ..models import ResearchError

        return AgentResult(
            reasoning=f"Synthesis failed: {e}",
            searches_performed=evidence.searches_performed,
            error=ResearchError(category="anthropic_error", message=str(e)),
        ), 0

    # Post-hoc confidence upgrade (same logic as parse_report_findings)
    upgraded_conf, src_count, warning = compute_confidence_upgrade(
        result.sources, result.confidence, result.epc_contractor,
    )
    result.agent_confidence = result.confidence  # capture pre-upgrade
    result.confidence = upgraded_conf
    result.source_count = src_count
    result.confidence_warning = warning

    return result, synth_tokens
