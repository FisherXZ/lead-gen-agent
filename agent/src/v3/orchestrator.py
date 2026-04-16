"""v3 Research Orchestrator — procedural deep research loop.

Architecture: Plan → Parallel fan-out → Reflect-refine loop → Synthesize.
LLM calls: ~5 total (1 plan + 3 reflections + 1 synthesis).
Search/scrape/filter: procedural Python, NO LLM calls.

Drop-in compatible with run_research() signature:
  (project, knowledge_context, approved_plan, api_key, shared_findings)
  → (AgentResult, list[dict], int)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from ..context_compressor import ContextCompressor
from ..embeddings import EmbeddingProvider
from ..evidence import EvidenceStore
from ..models import AgentResult, ResearchError
from ..search_dispatch import execute_sub_query
from .planner import llm_plan
from .reflector import llm_reflect
from .synthesizer import llm_synthesize

logger = logging.getLogger(__name__)

MAX_DEPTH = int(os.environ.get("RESEARCH_V3_MAX_DEPTH", "5"))
TIME_BUDGET_MINUTES = float(os.environ.get("RESEARCH_V3_TIME_BUDGET", "4.0"))


async def run_research_v3(
    project: dict,
    knowledge_context: str | None = None,
    approved_plan: str | None = None,
    api_key: str | None = None,
    shared_findings: EvidenceStore | None = None,
    max_depth: int | None = None,
    time_budget: float | None = None,
) -> tuple[AgentResult, list[dict], int]:
    """Run procedural deep research for a single project.

    Returns: (AgentResult, agent_log, total_tokens)
    """
    effective_max_depth = max_depth if max_depth is not None else MAX_DEPTH
    effective_time_budget = time_budget if time_budget is not None else TIME_BUDGET_MINUTES
    start_time = time.time()
    deadline = start_time + (effective_time_budget * 60)

    # Initialize components
    embedding_key = os.environ.get("OPENAI_API_KEY")
    compressor = ContextCompressor(EmbeddingProvider(api_key=embedding_key))
    evidence = EvidenceStore()
    agent_log: list[dict] = []

    # Seed from shared findings (batch mode)
    if shared_findings is not None:
        for finding in shared_findings.findings:
            evidence.add(finding)
        agent_log.append({
            "phase": "seed",
            "shared_findings_count": len(shared_findings.findings),
        })

    total_tokens = 0

    # ── PLAN ──
    try:
        sub_queries, plan_tokens = await llm_plan(
            project, knowledge_context, api_key=api_key,
        )
        total_tokens += plan_tokens
    except Exception as e:
        logger.warning("Planning failed: %s", e)
        sub_queries = _emergency_queries(project)
        plan_tokens = 0

    agent_log.append({"phase": "plan", "queries": sub_queries, "tokens": plan_tokens})

    # ── INITIAL FAN-OUT (parallel, no LLM) ──
    fanout_results = await asyncio.gather(*[
        execute_sub_query(sq, evidence, compressor, iteration=0)
        for sq in sub_queries
    ], return_exceptions=True)

    total_added = sum(r for r in fanout_results if isinstance(r, int))
    agent_log.append({
        "phase": "initial_fanout",
        "queries": len(sub_queries),
        "findings_added": total_added,
        "total_findings": len(evidence.findings),
    })

    # ── REFLECT-REFINE LOOP ──
    for depth in range(effective_max_depth):
        minutes_remaining = (deadline - time.time()) / 60
        if minutes_remaining < 0.5:
            logger.info("Time budget exhausted at depth %d", depth)
            agent_log.append({"phase": "time_exhausted", "depth": depth})
            break

        try:
            reflection = await llm_reflect(
                project, evidence, minutes_remaining, api_key=api_key,
            )
            reflect_tokens = getattr(reflection, "_tokens_used", 0)
            total_tokens += reflect_tokens
        except Exception as e:
            logger.warning("Reflection failed at depth %d: %s", depth, e)
            break

        agent_log.append({
            "phase": "reflect",
            "depth": depth,
            "summary": reflection.summary,
            "gaps": reflection.gaps,
            "should_continue": reflection.should_continue,
            "next_search_topic": reflection.next_search_topic,
            "findings_count": len(evidence.findings),
            "minutes_remaining": round(minutes_remaining, 1),
            "tokens": reflect_tokens,
        })

        if not reflection.should_continue or not reflection.gaps:
            logger.info("Reflection says stop at depth %d", depth)
            break

        # Refine: search the next gap (procedural, no LLM)
        next_query = reflection.next_search_topic or reflection.gaps[0]
        added = await execute_sub_query(
            next_query, evidence, compressor, iteration=depth + 1,
        )
        agent_log.append({
            "phase": "refine",
            "depth": depth,
            "query": next_query,
            "findings_added": added,
        })

    # ── SYNTHESIZE (1 Sonnet structured-output call) ──
    # Pass reflection trail so synthesizer can generate negative_evidence
    reflection_trail = [e for e in agent_log if e.get("phase") == "reflect"]
    try:
        result, synth_tokens = await llm_synthesize(
            project, evidence, api_key=api_key, reflection_trail=reflection_trail,
        )
        total_tokens += synth_tokens
    except Exception as e:
        logger.error("Synthesis failed: %s", e)
        result = AgentResult(
            reasoning=f"Synthesis failed: {e}",
            searches_performed=evidence.searches_performed,
            error=ResearchError(category="anthropic_error", message=str(e)),
        )
        synth_tokens = 0

    # Ensure searches_performed is populated from evidence
    if not result.searches_performed and evidence.searches_performed:
        result.searches_performed = evidence.searches_performed

    agent_log.append({
        "phase": "synthesize",
        "epc": result.epc_contractor,
        "confidence": result.confidence,
        "source_count": result.source_count,
        "total_findings": len(evidence.findings),
        "tokens": synth_tokens,
        "total_tokens": total_tokens,
    })

    # ── PROPAGATE TO SHARED (batch mode) ──
    if shared_findings is not None:
        for finding in evidence.findings:
            await shared_findings.add_async(finding)

    return result, agent_log, total_tokens


def _emergency_queries(project: dict) -> list[str]:
    """Last-resort queries when planner completely fails."""
    name = project.get("project_name", "solar project")
    dev = project.get("developer", "")
    return [f"{dev} {name} EPC contractor".strip()]
