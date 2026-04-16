"""Tests for v3 reflector module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.evidence import EvidenceStore
from src.models import Finding, ReflectionResult
from src.v3.reflector import _parse_reflection, llm_reflect

PROJECT = {
    "project_name": "Desert Wind Solar",
    "developer": "NextEra Energy",
    "mw_capacity": 400,
    "state": "AZ",
}


def _make_evidence(n_findings: int = 2, n_searches: int = 2) -> EvidenceStore:
    ev = EvidenceStore()
    for i in range(n_findings):
        ev.add(
            Finding(
                text=f"Finding {i}: McCarthy Building Companies selected as EPC",
                source_url=f"https://example.com/article-{i}",
                source_tool="tavily_search",
                reliability="medium",
            )
        )
    for i in range(n_searches):
        ev.record_search(f"search query {i}")
    return ev


# ---------------------------------------------------------------------------
# test_reflect_returns_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_returns_result():
    """Mock LLM returns valid JSON → ReflectionResult with correct fields."""
    payload = {
        "summary": "McCarthy identified as EPC from press release.",
        "gaps": ["No second source confirming McCarthy"],
        "should_continue": True,
        "next_search_topic": "McCarthy Building Companies Desert Wind Solar AZ",
    }

    mock_response = MagicMock()
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_response.content = [MagicMock(text=json.dumps(payload))]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("src.v3.reflector.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await llm_reflect(PROJECT, _make_evidence(), minutes_remaining=5.0, api_key="k")

    assert isinstance(result, ReflectionResult)
    assert result.summary == payload["summary"]
    assert result.gaps == payload["gaps"]
    assert result.should_continue is True
    assert result.next_search_topic == payload["next_search_topic"]


# ---------------------------------------------------------------------------
# test_reflect_time_warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_time_warning():
    """When minutes_remaining < 1, the prompt must contain the time warning text."""
    captured_prompts: list[str] = []

    async def capture_create(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])
        mock_response = MagicMock()
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {"summary": "done", "gaps": [], "should_continue": False}
                )
            )
        ]
        return mock_response

    mock_client = MagicMock()
    mock_client.messages.create = capture_create

    with patch("src.v3.reflector.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await llm_reflect(
            PROJECT, _make_evidence(), minutes_remaining=0.5, api_key="k"
        )

    assert len(captured_prompts) == 1
    assert "Less than 1 minute remains" in captured_prompts[0]
    assert result.should_continue is False


# ---------------------------------------------------------------------------
# test_reflect_failure_continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_failure_continues():
    """When LLM raises, should return ReflectionResult with should_continue=True."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("connection error"))

    with patch("src.v3.reflector.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await llm_reflect(PROJECT, _make_evidence(), minutes_remaining=3.0, api_key="k")

    assert isinstance(result, ReflectionResult)
    assert result.should_continue is True
    assert "Reflection failed" in result.summary


# ---------------------------------------------------------------------------
# test_parse_reflection_fallbacks
# ---------------------------------------------------------------------------


def test_parse_reflection_direct_json():
    """Level 1: direct JSON parse."""
    raw = json.dumps({"summary": "Good evidence", "should_continue": False})
    result = _parse_reflection(raw)
    assert result.summary == "Good evidence"
    assert result.should_continue is False


def test_parse_reflection_code_block():
    """Level 2: JSON inside markdown code block."""
    payload = {"summary": "Some evidence", "gaps": ["gap1"], "should_continue": True}
    raw = f"Here is my analysis:\n```json\n{json.dumps(payload)}\n```"
    result = _parse_reflection(raw)
    assert result.summary == "Some evidence"
    assert result.gaps == ["gap1"]


def test_parse_reflection_embedded_json():
    """Level 3: JSON object embedded in prose."""
    payload = {"summary": "Embedded", "should_continue": True}
    raw = f"Some preamble text. {json.dumps(payload)} trailing text."
    result = _parse_reflection(raw)
    assert result.summary == "Embedded"


def test_parse_reflection_all_fallbacks_fail():
    """When all 3 parse attempts fail → returns safe default with should_continue=True."""
    result = _parse_reflection("this is not json at all!!")
    assert result.should_continue is True
    assert "Could not parse" in result.summary
