"""Tests for research.py — standalone EPC research runner.

After the v3 swap, run_research() delegates to run_research_v3().
All mocks target src.v3.orchestrator.* rather than src.research_loop.*.

Deleted tests (covered by test_v3_orchestrator.py):
- TestMaxDepth.test_max_depth_returns_error → test_max_depth_exhausted
- TestSearchErrors.test_search_error_feeds_back_error → error handling in orchestrator
- TestTokenCounting.test_tokens_accumulated_across_turns → tokens are 0 in v3 (not yet instrumented)
- TestTenacityRetry.* → retry lives in v2 _call_api, not used by v3; v3 error handling
  is in test_synthesis_failure_returns_error + test_planning_failure_uses_fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.models import AgentResult, ReflectionResult
from src.research import run_research


# ---------------------------------------------------------------------------
# Immediate report_findings (plan → synthesize in one pass)
# ---------------------------------------------------------------------------


class TestReportFindings:
    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_single_turn_report(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth, sample_project
    ):
        """v3 pipeline: plan → fan-out → reflect-stop → synthesize returns EPC."""
        mock_plan.return_value = (["query1"], 500)
        mock_sub_query.return_value = 3
        mock_reflect.return_value = ReflectionResult(
            summary="done", gaps=[], should_continue=False
        )
        mock_synth.return_value = (AgentResult(
            epc_contractor="Blattner Energy",
            confidence="confirmed",
            sources=[
                {
                    "channel": "trade_publication",
                    "publication": "SPW",
                    "excerpt": "Blattner awarded",
                    "reliability": "high",
                }
            ],
            reasoning="Two sources confirm.",
            searches_performed=["query1"],
        ), 1000)

        result, log, tokens = await run_research(sample_project)

        assert isinstance(result, AgentResult)
        assert result.epc_contractor == "Blattner Energy"
        assert result.confidence == "confirmed"
        assert result.reasoning == "Two sources confirm."
        # v3 now tracks tokens from plan + reflect + synthesize calls
        assert tokens > 0

    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_report_with_null_epc(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth, sample_project
    ):
        """v3 synthesizer can return unknown confidence with null epc_contractor."""
        mock_plan.return_value = (["dead end query"], 500)
        mock_sub_query.return_value = 0
        mock_reflect.return_value = ReflectionResult(
            summary="No evidence found.", gaps=[], should_continue=False
        )
        mock_synth.return_value = (AgentResult(
            epc_contractor=None,
            confidence="unknown",
            reasoning="No evidence found.",
            searches_performed=["dead end query"],
        ), 1000)

        result, log, tokens = await run_research(sample_project)

        assert result.epc_contractor is None
        assert result.confidence == "unknown"
        assert result.sources == []


# ---------------------------------------------------------------------------
# Multi-turn: reflect→refine→synthesize
# ---------------------------------------------------------------------------


class TestMultiTurn:
    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_search_then_report(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth, sample_project
    ):
        """Reflect says continue on first pass, then stops — two rounds of sub-queries."""
        mock_plan.return_value = (["SunDev Sunrise Solar EPC contractor"], 500)
        mock_sub_query.return_value = 2

        reflect_calls = 0

        async def reflect_side_effect(project, evidence, minutes_remaining, api_key=None):
            nonlocal reflect_calls
            reflect_calls += 1
            if reflect_calls == 1:
                return ReflectionResult(
                    summary="Found partial evidence",
                    gaps=["Need verification"],
                    should_continue=True,
                    next_search_topic="Blattner Energy SunDev verification",
                )
            return ReflectionResult(
                summary="Sufficient evidence", gaps=[], should_continue=False
            )

        mock_reflect.side_effect = reflect_side_effect
        mock_synth.return_value = (AgentResult(
            epc_contractor="Blattner Energy",
            confidence="likely",
            sources=[{"channel": "news_article", "excerpt": "Blattner"}],
            reasoning="Found news article.",
            searches_performed=["SunDev Sunrise Solar EPC contractor"],
        ), 1000)

        result, log, tokens = await run_research(sample_project)

        assert result.epc_contractor == "Blattner Energy"
        assert result.confidence == "likely"
        # sub_query called for initial fan-out (1) + 1 refine = 2 total
        assert mock_sub_query.call_count == 2
        # Both reflect calls happened
        assert mock_reflect.call_count == 2


# ---------------------------------------------------------------------------
# Shared findings forwarded correctly
# ---------------------------------------------------------------------------


class TestSharedFindingsForwarding:
    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_shared_findings_parameter_forwarded(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth, sample_project
    ):
        """shared_findings kwarg is forwarded through run_research → run_research_v3."""
        from src.evidence import EvidenceStore, Finding

        mock_plan.return_value = (["query1"], 500)
        mock_sub_query.return_value = 1
        mock_reflect.return_value = ReflectionResult(
            summary="done", gaps=[], should_continue=False
        )
        mock_synth.return_value = (AgentResult(
            epc_contractor="McCarthy",
            confidence="likely",
            searches_performed=["query1"],
        ), 1000)

        shared = EvidenceStore()
        shared.add(Finding(
            text="Pre-seeded finding",
            source_url="https://example.com/pre",
            source_tool="tavily_search",
            iteration=0,
        ))

        result, log, tokens = await run_research(sample_project, shared_findings=shared)

        assert result.epc_contractor == "McCarthy"
        # Seed phase logged
        seed_entry = next((e for e in log if e.get("phase") == "seed"), None)
        assert seed_entry is not None
        assert seed_entry["shared_findings_count"] == 1
