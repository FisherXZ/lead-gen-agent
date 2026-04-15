"""End-to-end smoke test for the wired v2 research pipeline.

Verifies the full path: run_research() → run_research_loop() → reflection →
evidence → report_findings → AgentResult with upgraded confidence.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_claude_response, make_tool_use_block

from src.models import AgentResult, ReflectionResult
from src.research import run_research


def _sample_project():
    return {
        "id": "e2e-v2-1",
        "project_name": "Desert Sun Solar",
        "queue_id": "Q-E2E-V2-1",
        "developer": "AES Corporation",
        "mw_capacity": 300,
        "state": "CA",
        "iso_region": "CAISO",
    }


class TestE2EV2:
    @patch("src.research_loop.analyze_and_plan", new_callable=AsyncMock)
    @patch("src.research_loop.execute_tool", new_callable=AsyncMock)
    @patch("src.research.anthropic.AsyncAnthropic")
    async def test_full_v2_pipeline_finds_epc(
        self, MockClient, mock_exec_tool, mock_reflect, _sample_project=_sample_project
    ):
        """Full flow: search → reflect → verify → report through run_research()."""
        project = _sample_project()

        # Round 1: agent searches
        round1_search = make_claude_response(
            stop_reason="tool_use",
            content=[make_tool_use_block(
                name="web_search",
                input_data={"query": "AES Desert Sun Solar EPC contractor"},
                block_id="t1",
            )],
            input_tokens=100,
            output_tokens=50,
        )

        # Round 1 continues: agent ends turn after getting search results
        round1_end = make_claude_response(
            stop_reason="end_turn",
            content=[],
            input_tokens=150,
            output_tokens=40,
        )

        # After reflection says stop, forced report round
        round_report = make_claude_response(
            stop_reason="tool_use",
            content=[make_tool_use_block(
                name="report_findings",
                block_id="t3",
                input_data={
                    "epc_contractor": "Mortenson",
                    "confidence": "likely",
                    "sources": [{
                        "channel": "press_release",
                        "excerpt": "Mortenson selected as EPC for 300MW Desert Sun",
                        "url": "https://example.com/pr",
                        "reliability": "high",
                        "source_method": "tavily_search",
                        "date": "2025-06-01",
                    }],
                    "reasoning": {
                        "summary": "Mortenson identified as EPC from press release [1]",
                        "supporting_evidence": ["Press release names Mortenson"],
                        "gaps": [],
                    },
                    "searches_performed": ["AES Desert Sun Solar EPC contractor"],
                    "negative_evidence": [],
                },
            )],
            input_tokens=300,
            output_tokens=150,
        )

        responses = [round1_search, round1_end, round_report]
        call_idx = 0

        async def side_effect(**kwargs):
            nonlocal call_idx
            resp = responses[min(call_idx, len(responses) - 1)]
            call_idx += 1
            return resp

        mock_client = MagicMock()
        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=side_effect)
        MockClient.return_value = mock_client

        # Reflection after round 1: says stop (sufficient evidence)
        mock_reflect.return_value = ReflectionResult(
            summary="Mortenson confirmed from press release",
            gaps=[],
            should_continue=False,
        )

        # Tool execution returns realistic search results
        mock_exec_tool.return_value = {
            "results": [{
                "title": "Mortenson EPC Award",
                "url": "https://example.com/pr",
                "content": "Mortenson selected as EPC for AES's 300MW Desert Sun Solar project in California",
                "score": 0.95,
            }],
        }

        result, log, tokens = await run_research(
            project=project,
            knowledge_context="No prior research on this project.",
        )

        assert isinstance(result, AgentResult)
        assert result.epc_contractor == "Mortenson"
        assert result.confidence == "likely"
        assert tokens > 0
        # Verify reflection was called
        assert mock_reflect.call_count >= 1
        # Verify evidence was extracted (tool was called at least once)
        assert mock_exec_tool.call_count >= 1
