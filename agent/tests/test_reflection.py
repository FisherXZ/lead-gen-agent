"""Tests for the reflection module (analyze_and_plan, v2 research loop)."""

import json
from unittest.mock import AsyncMock, patch

from src.evidence import EvidenceStore
from src.models import Finding, ReflectionResult
from src.reflection import _format_project_summary, _parse_reflection, analyze_and_plan


# ---------------------------------------------------------------------------
# _format_project_summary
# ---------------------------------------------------------------------------


class TestFormatProjectSummary:
    def test_full_project(self):
        result = _format_project_summary({
            "project_name": "Lone Star Solar",
            "developer": "NextEra Energy",
            "mw_capacity": 200,
            "state": "TX",
        })
        assert "Lone Star Solar" in result
        assert "NextEra Energy" in result
        assert "200MW" in result
        assert "TX" in result

    def test_empty_project(self):
        result = _format_project_summary({})
        assert result == "Unknown project"

    def test_partial_project(self):
        result = _format_project_summary({"developer": "AES"})
        assert "AES" in result


# ---------------------------------------------------------------------------
# _parse_reflection
# ---------------------------------------------------------------------------


class TestParseReflection:
    def test_direct_json(self):
        raw = json.dumps({
            "summary": "Found McCarthy as likely EPC",
            "gaps": ["No second source"],
            "should_continue": True,
            "next_search_topic": "McCarthy portfolio",
        })
        result = _parse_reflection(raw)
        assert isinstance(result, ReflectionResult)
        assert result.should_continue is True
        assert "McCarthy" in result.summary

    def test_json_in_code_block(self):
        raw = '```json\n{"summary": "test", "gaps": [], "should_continue": false}\n```'
        result = _parse_reflection(raw)
        assert result.should_continue is False

    def test_json_in_plain_code_block(self):
        raw = '```\n{"summary": "test", "gaps": ["gap1"], "should_continue": true}\n```'
        result = _parse_reflection(raw)
        assert result.should_continue is True
        assert len(result.gaps) == 1

    def test_json_embedded_in_text(self):
        raw = 'Here is my analysis: {"summary": "test", "should_continue": false} That is all.'
        result = _parse_reflection(raw)
        assert result.should_continue is False

    def test_garbage_input(self):
        raw = "This is not JSON at all, just random text about solar panels."
        result = _parse_reflection(raw)
        assert isinstance(result, ReflectionResult)
        assert result.should_continue is True  # safe default

    def test_empty_input(self):
        result = _parse_reflection("")
        assert result.should_continue is True

    def test_partial_json_fields(self):
        raw = json.dumps({"summary": "only summary"})
        result = _parse_reflection(raw)
        assert result.summary == "only summary"
        assert result.gaps == []
        assert result.should_continue is True


# ---------------------------------------------------------------------------
# analyze_and_plan (integration with mocked LLM)
# ---------------------------------------------------------------------------


def _make_store_with_finding():
    store = EvidenceStore()
    store.add(Finding(
        text="McCarthy Building Companies awarded 200MW solar EPC contract",
        source_url="https://example.com/pr",
        source_tool="tavily_search",
        reliability="high",
        iteration=1,
    ))
    store.record_search("McCarthy solar EPC Texas")
    return store


def _sample_project():
    return {
        "id": "test-123",
        "project_name": "Lone Star Solar",
        "developer": "NextEra Energy",
        "mw_capacity": 200,
        "state": "TX",
        "iso_region": "ERCOT",
    }


class TestAnalyzeAndPlan:
    async def test_returns_reflection_result(self):
        mock_response = json.dumps({
            "summary": "Found McCarthy as likely EPC from press release",
            "gaps": ["No second independent source"],
            "should_continue": True,
            "next_search_topic": "McCarthy Building solar portfolio",
        })

        with patch("src.reflection._call_reflection_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            result = await analyze_and_plan(
                project=_sample_project(),
                evidence=_make_store_with_finding(),
                minutes_remaining=3.0,
            )

        assert isinstance(result, ReflectionResult)
        assert result.should_continue is True
        assert "McCarthy" in result.summary
        assert len(result.gaps) == 1

    async def test_prompt_includes_project_and_evidence(self):
        with patch("src.reflection._call_reflection_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps({
                "summary": "test", "gaps": [], "should_continue": False,
            })
            await analyze_and_plan(
                project=_sample_project(),
                evidence=_make_store_with_finding(),
                minutes_remaining=3.0,
            )

        prompt = mock_llm.call_args[0][0]
        assert "Lone Star Solar" in prompt
        assert "NextEra Energy" in prompt
        assert "McCarthy" in prompt
        assert "3.0" in prompt

    async def test_time_warning_injected_when_low(self):
        with patch("src.reflection._call_reflection_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps({
                "summary": "test", "gaps": [], "should_continue": False,
            })
            await analyze_and_plan(
                project=_sample_project(),
                evidence=EvidenceStore(),
                minutes_remaining=0.5,
            )

        prompt = mock_llm.call_args[0][0]
        assert "Less than 1 minute" in prompt

    async def test_no_time_warning_when_plenty(self):
        with patch("src.reflection._call_reflection_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps({
                "summary": "test", "gaps": [], "should_continue": False,
            })
            await analyze_and_plan(
                project=_sample_project(),
                evidence=EvidenceStore(),
                minutes_remaining=3.0,
            )

        prompt = mock_llm.call_args[0][0]
        assert "Less than 1 minute" not in prompt

    async def test_handles_llm_exception(self):
        with patch("src.reflection._call_reflection_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API timeout")
            result = await analyze_and_plan(
                project=_sample_project(),
                evidence=EvidenceStore(),
                minutes_remaining=3.0,
            )

        assert isinstance(result, ReflectionResult)
        assert result.should_continue is True

    async def test_handles_malformed_llm_output(self):
        with patch("src.reflection._call_reflection_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "This is not JSON at all"
            result = await analyze_and_plan(
                project=_sample_project(),
                evidence=EvidenceStore(),
                minutes_remaining=3.0,
            )

        assert isinstance(result, ReflectionResult)
        assert result.should_continue is True
