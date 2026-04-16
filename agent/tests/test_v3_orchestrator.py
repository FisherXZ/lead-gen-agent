"""Tests for v3 research orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.evidence import EvidenceStore
from src.models import AgentResult, Finding, ReflectionResult, ResearchError
from src.v3.orchestrator import _emergency_queries, run_research_v3

PROJECT = {
    "id": "proj-001",
    "project_name": "Sunbelt Solar",
    "developer": "AES Corporation",
    "mw_capacity": 250,
    "state": "TX",
    "iso_region": "ERCOT",
}

_GOOD_RESULT = AgentResult(
    epc_contractor="McCarthy Building",
    confidence="likely",
    source_count=1,
    searches_performed=["AES Corporation Sunbelt Solar EPC contractor"],
)

_REFLECTION_STOP = ReflectionResult(
    summary="Found sufficient evidence.",
    gaps=[],
    should_continue=False,
    next_search_topic=None,
)

_REFLECTION_CONTINUE = ReflectionResult(
    summary="Need more evidence.",
    gaps=["Need second source for McCarthy"],
    should_continue=True,
    next_search_topic="McCarthy Building AES Sunbelt Solar TX verification",
)


# ---------------------------------------------------------------------------
# test_happy_path_finds_epc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_finds_epc():
    """Plan returns queries, fan-out runs, reflection says stop, synthesis returns EPC."""
    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            return_value=(["query1", "query2"], 500),
        ),
        patch(
            "src.v3.orchestrator.execute_sub_query",
            new_callable=AsyncMock,
            return_value=3,
        ),
        patch(
            "src.v3.orchestrator.llm_reflect",
            new_callable=AsyncMock,
            return_value=_REFLECTION_STOP,
        ),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            return_value=(_GOOD_RESULT, 1000),
        ),
    ):
        result, log, tokens = await run_research_v3(PROJECT)

    assert result.epc_contractor == "McCarthy Building"
    assert result.confidence == "likely"
    assert tokens > 0  # plan + reflect + synthesize tokens

    phases = [entry["phase"] for entry in log]
    assert "plan" in phases
    assert "initial_fanout" in phases
    assert "reflect" in phases
    assert "synthesize" in phases

    plan_entry = next(e for e in log if e["phase"] == "plan")
    assert plan_entry["queries"] == ["query1", "query2"]

    fanout_entry = next(e for e in log if e["phase"] == "initial_fanout")
    assert fanout_entry["queries"] == 2
    # 2 queries × 3 findings each = 6 total added
    assert fanout_entry["findings_added"] == 6

    synth_entry = next(e for e in log if e["phase"] == "synthesize")
    assert synth_entry["epc"] == "McCarthy Building"
    assert synth_entry["confidence"] == "likely"


# ---------------------------------------------------------------------------
# test_reflect_drives_additional_search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_drives_additional_search():
    """First reflection says continue → refine search runs → second reflection says stop."""
    reflect_calls = 0

    async def mock_reflect(project, evidence, minutes_remaining, api_key=None):
        nonlocal reflect_calls
        reflect_calls += 1
        if reflect_calls == 1:
            return _REFLECTION_CONTINUE
        return _REFLECTION_STOP

    execute_calls = []

    async def mock_execute(query, evidence, compressor, iteration=0):
        execute_calls.append((query, iteration))
        return 2

    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            return_value=(["initial query"], 500),
        ),
        patch("src.v3.orchestrator.execute_sub_query", side_effect=mock_execute),
        patch("src.v3.orchestrator.llm_reflect", side_effect=mock_reflect),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            return_value=(_GOOD_RESULT, 1000),
        ),
    ):
        result, log, tokens = await run_research_v3(PROJECT)

    # Should have: 1 initial fanout call + 1 refine call
    assert len(execute_calls) == 2
    # Initial fanout at iteration=0
    assert execute_calls[0] == ("initial query", 0)
    # Refine call uses the next_search_topic from the reflection
    assert execute_calls[1][0] == _REFLECTION_CONTINUE.next_search_topic
    assert execute_calls[1][1] == 1  # iteration=depth+1=1

    phases = [entry["phase"] for entry in log]
    assert phases.count("reflect") == 2
    assert phases.count("refine") == 1

    refine_entry = next(e for e in log if e["phase"] == "refine")
    assert refine_entry["query"] == _REFLECTION_CONTINUE.next_search_topic
    assert refine_entry["depth"] == 0


# ---------------------------------------------------------------------------
# test_max_depth_exhausted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_depth_exhausted():
    """Reflection always says continue; depth hits max_depth → synthesis still runs."""
    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            return_value=(["query1"], 500),
        ),
        patch(
            "src.v3.orchestrator.execute_sub_query",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch(
            "src.v3.orchestrator.llm_reflect",
            new_callable=AsyncMock,
            return_value=_REFLECTION_CONTINUE,
        ),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            return_value=(_GOOD_RESULT, 1000),
        ) as mock_synth,
    ):
        result, log, tokens = await run_research_v3(PROJECT, max_depth=3)

    # Synthesis must still run
    mock_synth.assert_awaited_once()
    assert result.epc_contractor == "McCarthy Building"

    reflect_entries = [e for e in log if e["phase"] == "reflect"]
    assert len(reflect_entries) == 3  # max_depth=3

    # All depths 0, 1, 2 covered
    assert [e["depth"] for e in reflect_entries] == [0, 1, 2]


# ---------------------------------------------------------------------------
# test_planning_failure_uses_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planning_failure_uses_fallback():
    """llm_plan raises → _emergency_queries used; loop still completes."""
    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unavailable"),
        ),
        patch(
            "src.v3.orchestrator.execute_sub_query",
            new_callable=AsyncMock,
            return_value=2,
        ),
        patch(
            "src.v3.orchestrator.llm_reflect",
            new_callable=AsyncMock,
            return_value=_REFLECTION_STOP,
        ),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            return_value=(_GOOD_RESULT, 1000),
        ),
    ):
        result, log, tokens = await run_research_v3(PROJECT)

    # Should fall back to emergency queries and still complete
    assert result is not None
    assert result.epc_contractor == "McCarthy Building"

    plan_entry = next(e for e in log if e["phase"] == "plan")
    # Emergency query contains developer + project name
    assert len(plan_entry["queries"]) == 1
    assert "AES Corporation" in plan_entry["queries"][0]
    assert "Sunbelt Solar" in plan_entry["queries"][0]


# ---------------------------------------------------------------------------
# test_synthesis_failure_returns_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesis_failure_returns_error():
    """Synthesis raises → AgentResult with error field, no crash."""
    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            return_value=(["query1"], 500),
        ),
        patch(
            "src.v3.orchestrator.execute_sub_query",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch(
            "src.v3.orchestrator.llm_reflect",
            new_callable=AsyncMock,
            return_value=_REFLECTION_STOP,
        ),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Synthesis boom"),
        ),
    ):
        result, log, tokens = await run_research_v3(PROJECT)

    assert result is not None
    assert result.error is not None
    assert result.error.category == "anthropic_error"
    assert "Synthesis boom" in result.error.message
    assert result.epc_contractor is None

    # Synthesize phase still appears in log
    synth_entry = next(e for e in log if e["phase"] == "synthesize")
    assert synth_entry is not None


# ---------------------------------------------------------------------------
# test_shared_findings_seeded_and_propagated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_findings_seeded_and_propagated():
    """Pass shared_findings with 1 finding → seeded into evidence.
    After completion, local findings propagated back to shared store.
    """
    pre_existing = Finding(
        text="Pre-existing finding about McCarthy",
        source_url="https://example.com/prior",
        source_tool="tavily_search",
        reliability="high",
        iteration=0,
    )
    shared = EvidenceStore()
    shared.add(pre_existing)

    execute_calls = []

    async def mock_execute(query, evidence, compressor, iteration=0):
        # Add a new finding so propagation has something to write back
        evidence.add(Finding(
            text=f"New finding for {query}",
            source_url=f"https://example.com/{iteration}",
            source_tool="parallel_search",
            reliability="medium",
            iteration=iteration,
        ))
        execute_calls.append(query)
        return 1

    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            return_value=(["query1"], 500),
        ),
        patch("src.v3.orchestrator.execute_sub_query", side_effect=mock_execute),
        patch(
            "src.v3.orchestrator.llm_reflect",
            new_callable=AsyncMock,
            return_value=_REFLECTION_STOP,
        ),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            return_value=(_GOOD_RESULT, 1000),
        ),
    ):
        result, log, tokens = await run_research_v3(PROJECT, shared_findings=shared)

    # Seed phase should be logged
    seed_entry = next(e for e in log if e["phase"] == "seed")
    assert seed_entry["shared_findings_count"] == 1

    # Shared store should now contain the pre-existing finding + propagated new finding
    shared_urls = {f.source_url for f in shared.findings}
    assert "https://example.com/prior" in shared_urls
    assert "https://example.com/0" in shared_urls


# ---------------------------------------------------------------------------
# test_time_budget_respected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_time_budget_respected():
    """Very short time_budget → loop exits quickly; synthesis still runs."""
    reflect_call_count = 0

    async def mock_reflect_slow(project, evidence, minutes_remaining, api_key=None):
        nonlocal reflect_call_count
        reflect_call_count += 1
        # Always say continue, but time budget should cut us off
        return _REFLECTION_CONTINUE

    with (
        patch("src.v3.orchestrator.EmbeddingProvider", return_value=MagicMock()),
        patch(
            "src.v3.orchestrator.llm_plan",
            new_callable=AsyncMock,
            return_value=(["query1"], 500),
        ),
        patch(
            "src.v3.orchestrator.execute_sub_query",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch("src.v3.orchestrator.llm_reflect", side_effect=mock_reflect_slow),
        patch(
            "src.v3.orchestrator.llm_synthesize",
            new_callable=AsyncMock,
            return_value=(_GOOD_RESULT, 1000),
        ) as mock_synth,
    ):
        # 0.001 minutes = 0.06 seconds — deadline fires almost immediately
        result, log, tokens = await run_research_v3(PROJECT, time_budget=0.001, max_depth=10)

    # Synthesis still runs regardless of time exhaustion
    mock_synth.assert_awaited_once()
    assert result is not None

    # time_exhausted phase should be in log OR zero reflect calls ran
    phases = [e["phase"] for e in log]
    assert "time_exhausted" in phases or reflect_call_count == 0


# ---------------------------------------------------------------------------
# test_emergency_queries unit test
# ---------------------------------------------------------------------------


def test_emergency_queries_with_both_fields():
    project = {"project_name": "Sunbelt Solar", "developer": "AES Corporation"}
    queries = _emergency_queries(project)
    assert len(queries) == 1
    assert "AES Corporation" in queries[0]
    assert "Sunbelt Solar" in queries[0]
    assert "EPC contractor" in queries[0]


def test_emergency_queries_missing_developer():
    project = {"project_name": "Sunbelt Solar"}
    queries = _emergency_queries(project)
    assert len(queries) == 1
    assert "Sunbelt Solar" in queries[0]


def test_emergency_queries_empty_project():
    queries = _emergency_queries({})
    assert len(queries) == 1
    assert "solar project" in queries[0]
