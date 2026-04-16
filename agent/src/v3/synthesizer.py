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
) -> AgentResult:
    """Synthesize final AgentResult from evidence. ONE Sonnet structured-output call."""
    from .planner import _format_project_summary

    prompt = SYNTHESIS_PROMPT.format(
        project_summary=_format_project_summary(project),
        n_findings=len(evidence.findings),
        n_searches=len(evidence.searches_performed),
        evidence=evidence.format_for_prompt(),
        searches="\n".join(f"- {s}" for s in evidence.searches_performed) or "None",
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
        )

    # Post-hoc confidence upgrade (same logic as parse_report_findings)
    upgraded_conf, src_count, warning = compute_confidence_upgrade(
        result.sources, result.confidence, result.epc_contractor,
    )
    result.agent_confidence = result.confidence  # capture pre-upgrade
    result.confidence = upgraded_conf
    result.source_count = src_count
    result.confidence_warning = warning

    return result
