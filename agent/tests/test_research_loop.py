"""Tests for the v2 gap-driven research loop.

Tests the loop logic: gap-driven iteration, evidence accumulation,
time budgeting, reflection-based stopping, and report_findings handling.
All Anthropic API calls and tool executions are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_claude_response

from src.models import ReflectionResult
from src.research_loop import run_research_loop


def _tool_use_block(name, input_dict, block_id="tool-1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_dict
    block.id = block_id
    return block


def _text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _sample_project():
    return {
        "id": "loop-test-1",
        "project_name": "Lone Star Solar",
        "queue_id": "Q-LOOP-1",
        "developer": "NextEra Energy",
        "mw_capacity": 200,
        "state": "TX",
        "iso_region": "ERCOT",
    }


# ── Helpers to build common response sequences ──

def _search_response():
    """Agent calls web_search."""
    return make_claude_response(
        stop_reason="tool_use",
        content=[_tool_use_block("web_search", {"query": "NextEra Lone Star Solar EPC"})],
    )


def _end_turn_response(text="Done searching"):
    """Agent ends turn with text."""
    return make_claude_response(
        stop_reason="end_turn",
        content=[_text_block(text)],
    )


def _report_response(epc="McCarthy", confidence="likely"):
    """Agent calls report_findings."""
    return make_claude_response(
        stop_reason="tool_use",
        content=[_tool_use_block("report_findings", {
            "epc_contractor": epc,
            "confidence": confidence,
            "sources": [{
                "channel": "press_release",
                "excerpt": f"{epc} selected as EPC",
                "url": "https://example.com/pr",
                "reliability": "high",
                "source_method": "tavily_search",
                "date": "2025-06-01",
            }],
            "reasoning": {
                "summary": f"{epc} identified as EPC [1]",
                "supporting_evidence": ["Press release"],
                "gaps": [],
            },
            "searches_performed": ["NextEra Lone Star Solar EPC"],
            "negative_evidence": [],
        }, "rf-1")],
    )


# ── Tests ──

class TestReportFindingsDirect:
    """Agent calls report_findings in the first search round."""

    async def test_single_round_report(self):
        """Agent immediately finds and reports — loop exits after 1 round."""
        call_idx = 0

        async def mock_api(client, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return _search_response()
            return _report_response()

        with (
            patch("src.research_loop._call_api", side_effect=mock_api),
            patch("src.research_loop.execute_tool", new_callable=AsyncMock, return_value={
                "results": [{"title": "PR", "url": "https://example.com/pr",
                             "content": "McCarthy selected as EPC for 200MW project in Texas", "score": 0.9}],
            }),
            patch("src.db.get_anthropic_client", return_value=MagicMock()),
        ):
            result, log, tokens = await run_research_loop(
                project=_sample_project(),
                knowledge_context=None,
            )

        assert result.epc_contractor == "McCarthy"
        assert result.confidence == "likely"
        assert tokens > 0


class TestReflectionDrivenStop:
    """Reflection says should_continue=False, agent wraps up."""

    async def test_reflection_stops_loop(self):
        call_idx = 0

        async def mock_api(client, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx <= 2:
                # Round 1: search then end_turn
                if call_idx == 1:
                    return _search_response()
                return _end_turn_response()
            # Forced report round
            return _report_response()

        reflection = ReflectionResult(
            summary="Evidence sufficient — McCarthy confirmed",
            gaps=[],
            should_continue=False,
        )

        with (
            patch("src.research_loop._call_api", side_effect=mock_api),
            patch("src.research_loop.analyze_and_plan", new_callable=AsyncMock, return_value=reflection),
            patch("src.research_loop.execute_tool", new_callable=AsyncMock, return_value={
                "results": [{"title": "T", "url": "https://x.com", "content": "A" * 60, "score": 0.8}],
            }),
            patch("src.db.get_anthropic_client", return_value=MagicMock()),
        ):
            result, log, tokens = await run_research_loop(
                project=_sample_project(),
                knowledge_context=None,
            )

        assert result.epc_contractor == "McCarthy"
        # Verify reflection was logged
        reflection_entries = [e for e in log if e.get("type") == "reflection"]
        assert len(reflection_entries) == 1
        assert reflection_entries[0]["should_continue"] is False


class TestMaxDepthRespected:
    """Loop stops when max_depth is exhausted."""

    async def test_max_depth_produces_error_result(self):
        async def mock_api(client, **kwargs):
            return _search_response()

        reflection = ReflectionResult(
            summary="Still searching",
            gaps=["Need more info"],
            should_continue=True,
            next_search_topic="next query",
        )

        with (
            patch("src.research_loop._call_api", side_effect=mock_api),
            patch("src.research_loop.analyze_and_plan", new_callable=AsyncMock, return_value=reflection),
            patch("src.research_loop.execute_tool", new_callable=AsyncMock, return_value={"results": []}),
            patch("src.db.get_anthropic_client", return_value=MagicMock()),
        ):
            result, log, tokens = await run_research_loop(
                project=_sample_project(),
                knowledge_context=None,
                max_depth=2,
            )

        assert result.error is not None
        assert result.error.category == "max_iterations"
        assert result.confidence == "unknown"


class TestGapDrivenIteration:
    """Reflection provides gaps that drive subsequent search rounds."""

    async def test_gap_injected_as_guidance(self):
        call_idx = 0
        captured_messages = []

        async def mock_api(client, **kwargs):
            nonlocal call_idx
            call_idx += 1
            captured_messages.append(kwargs.get("messages", []))
            if call_idx <= 2:
                if call_idx == 1:
                    return _search_response()
                return _end_turn_response()
            if call_idx <= 4:
                if call_idx == 3:
                    return _search_response()
                return _end_turn_response()
            return _report_response()

        reflections = [
            ReflectionResult(
                summary="Found candidate, need verification",
                gaps=["Verify McCarthy scale capability"],
                should_continue=True,
                next_search_topic="McCarthy Building solar portfolio MW",
            ),
            ReflectionResult(
                summary="Verified — sufficient evidence",
                gaps=[],
                should_continue=False,
            ),
        ]
        reflection_idx = 0

        async def mock_reflect(**kwargs):
            nonlocal reflection_idx
            r = reflections[min(reflection_idx, len(reflections) - 1)]
            reflection_idx += 1
            return r

        with (
            patch("src.research_loop._call_api", side_effect=mock_api),
            patch("src.research_loop.analyze_and_plan", side_effect=mock_reflect),
            patch("src.research_loop.execute_tool", new_callable=AsyncMock, return_value={
                "results": [{"title": "T", "url": "https://x.com", "content": "A" * 60, "score": 0.8}],
            }),
            patch("src.db.get_anthropic_client", return_value=MagicMock()),
        ):
            result, log, tokens = await run_research_loop(
                project=_sample_project(),
                knowledge_context=None,
            )

        assert result.epc_contractor == "McCarthy"

        # Verify gap was injected into messages
        # The 3rd API call should see "[Research guidance:" in the messages
        if len(captured_messages) >= 3:
            third_call_msgs = captured_messages[2]
            guidance_msgs = [m for m in third_call_msgs
                           if isinstance(m.get("content"), str)
                           and "[Research guidance:" in m["content"]]
            assert len(guidance_msgs) >= 1
            assert "Verify McCarthy scale capability" in guidance_msgs[0]["content"]


class TestEvidenceAccumulation:
    """Evidence store is populated from tool results."""

    async def test_search_results_extracted(self):
        call_idx = 0

        async def mock_api(client, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return _search_response()
            return _report_response()

        with (
            patch("src.research_loop._call_api", side_effect=mock_api),
            patch("src.research_loop.execute_tool", new_callable=AsyncMock, return_value={
                "results": [{
                    "title": "McCarthy EPC Award",
                    "url": "https://reuters.com/mccarthy",
                    "content": "McCarthy Building Companies awarded 200MW solar EPC contract in Texas for the Lone Star project",
                    "score": 0.95,
                }],
            }),
            patch("src.db.get_anthropic_client", return_value=MagicMock()),
        ):
            result, log, tokens = await run_research_loop(
                project=_sample_project(),
                knowledge_context=None,
            )

        assert result.epc_contractor == "McCarthy"


class TestAuthenticationError:
    """API auth failure returns structured error."""

    async def test_auth_error(self):
        import anthropic as anth

        async def mock_api(client, **kwargs):
            raise anth.AuthenticationError(
                message="Invalid key",
                response=MagicMock(status_code=401),
                body=None,
            )

        with (
            patch("src.research_loop._call_api", side_effect=mock_api),
            patch("src.db.get_anthropic_client", return_value=MagicMock()),
        ):
            result, log, tokens = await run_research_loop(
                project=_sample_project(),
                knowledge_context=None,
            )

        assert result.error is not None
        assert result.error.category == "api_key_missing"
