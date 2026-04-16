"""End-to-end smoke test for the wired v3 research pipeline.

Verifies the full path: run_research() → run_research_v3() → plan →
fan-out → reflect → synthesize → AgentResult.

The deep orchestrator scenarios (max_depth, time_budget, shared_findings,
synthesis failure, etc.) live in test_v3_orchestrator.py. This file only
exercises the public run_research() entry point to confirm the wiring is
correct.
"""

from unittest.mock import AsyncMock, patch

from src.models import AgentResult, ReflectionResult
from src.research import run_research


def _sample_project():
    return {
        "id": "e2e-v3-1",
        "project_name": "Desert Sun Solar",
        "queue_id": "Q-E2E-V3-1",
        "developer": "AES Corporation",
        "mw_capacity": 300,
        "state": "CA",
        "iso_region": "CAISO",
    }


class TestE2EV3:
    @patch("src.v3.orchestrator.llm_synthesize", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_reflect", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.llm_plan", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.execute_sub_query", new_callable=AsyncMock)
    @patch("src.v3.orchestrator.EmbeddingProvider")
    async def test_full_v3_pipeline_finds_epc(
        self, MockEmbed, mock_sub_query, mock_plan, mock_reflect, mock_synth
    ):
        """Full flow via run_research(): plan → fan-out → reflect-stop → synthesize."""
        project = _sample_project()

        mock_plan.return_value = (["AES Desert Sun Solar EPC contractor"], 500)
        mock_sub_query.return_value = 3
        mock_reflect.return_value = ReflectionResult(
            summary="Mortenson confirmed from press release",
            gaps=[],
            should_continue=False,
        )
        mock_synth.return_value = (AgentResult(
            epc_contractor="Mortenson",
            confidence="likely",
            sources=[{
                "channel": "press_release",
                "excerpt": "Mortenson selected as EPC for 300MW Desert Sun",
                "reliability": "high",
            }],
            reasoning="Mortenson identified as EPC from press release",
            searches_performed=["AES Desert Sun Solar EPC contractor"],
        ), 1000)

        result, log, tokens = await run_research(
            project=project,
            knowledge_context="No prior research on this project.",
        )

        assert isinstance(result, AgentResult)
        assert result.epc_contractor == "Mortenson"
        assert result.confidence == "likely"
        assert tokens > 0  # v3 now tracks tokens

        # Verify plan + fan-out + reflect + synthesize phases all logged
        phases = [e["phase"] for e in log]
        assert "plan" in phases
        assert "initial_fanout" in phases
        assert "reflect" in phases
        assert "synthesize" in phases

        # Verify the LLM seams were called exactly once each
        mock_plan.assert_awaited_once()
        mock_reflect.assert_awaited_once()
        mock_synth.assert_awaited_once()
