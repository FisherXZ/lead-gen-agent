"""Tests for v3 synthesizer module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.evidence import EvidenceStore
from src.models import AgentResult, EpcSource, Finding, ResearchError
from src.v3.synthesizer import _SynthesisResult, llm_synthesize

PROJECT = {
    "project_name": "Copper Valley Solar",
    "developer": "Clearway Energy",
    "mw_capacity": 150,
    "state": "NV",
}


def _make_evidence(n: int = 2) -> EvidenceStore:
    ev = EvidenceStore()
    for i in range(n):
        ev.add(
            Finding(
                text=f"Clearway selected Mortenson Construction as EPC for Copper Valley [{i}]",
                source_url=f"https://clearway.com/news/copper-{i}",
                source_tool="tavily_search",
                reliability="high",
            )
        )
        ev.record_search(f"Clearway Copper Valley EPC query {i}")
    return ev


def _make_fake_result() -> AgentResult:
    return AgentResult(
        epc_contractor="Mortenson Construction",
        confidence="likely",
        sources=[
            EpcSource(
                channel="press_release",
                url="https://clearway.com/news/copper-0",
                excerpt="Clearway selects Mortenson as EPC",
                reliability="high",
            )
        ],
        reasoning="Found in press release [1]",
        searches_performed=["Clearway Copper Valley EPC query 0"],
    )


# ---------------------------------------------------------------------------
# test_synthesize_structured_output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_structured_output():
    """mock messages.parse returns ParsedMessage-like object → verify AgentResult fields."""
    fake_synthesis = _SynthesisResult(
        epc_contractor="Mortenson Construction",
        confidence="likely",
        sources=[
            EpcSource(
                channel="press_release",
                url="https://clearway.com/news/copper-0",
                excerpt="Clearway selects Mortenson as EPC",
                reliability="high",
            )
        ],
        reasoning="Found in press release [1]",
        searches_performed=["query 0"],
    )
    fake_response = SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=500), parsed_output=fake_synthesis)

    mock_client = MagicMock()
    mock_client.messages.parse = AsyncMock(return_value=fake_response)

    with patch("src.v3.synthesizer.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_synthesize(PROJECT, _make_evidence(), api_key="test-key")

    assert isinstance(result, AgentResult)
    assert result.epc_contractor == "Mortenson Construction"
    assert result.confidence in ("likely", "confirmed")  # may be upgraded
    assert len(result.sources) == 1
    assert result.reasoning == "Found in press release [1]"
    assert result.source_count >= 1


# ---------------------------------------------------------------------------
# test_synthesize_applies_confidence_upgrade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_applies_confidence_upgrade():
    """compute_confidence_upgrade is applied: agent_confidence captures pre-upgrade value."""
    # Two high-reliability sources → "likely" should be upgraded to "confirmed"
    fake_synthesis = _SynthesisResult(
        epc_contractor="Mortenson Construction",
        confidence="likely",
        sources=[
            EpcSource(
                channel="press_release",
                url="https://clearway.com/news/a",
                excerpt="EPC confirmed",
                reliability="high",
                source_method="press_release",
            ),
            EpcSource(
                channel="trade_pub",
                url="https://pv-tech.org/mortenson",
                excerpt="Mortenson wins Copper Valley contract",
                reliability="high",
                source_method="trade_pub",
            ),
        ],
        reasoning="Two independent sources confirm Mortenson.",
        searches_performed=["query 0"],
    )
    fake_response = SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=500), parsed_output=fake_synthesis)

    mock_client = MagicMock()
    mock_client.messages.parse = AsyncMock(return_value=fake_response)

    with patch("src.v3.synthesizer.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_synthesize(PROJECT, _make_evidence(), api_key="test-key")

    # agent_confidence should capture the pre-upgrade value
    assert result.agent_confidence == "likely"
    # With 2 high-reliability independent sources, should be upgraded to confirmed
    assert result.confidence == "confirmed"
    assert result.source_count == 2


# ---------------------------------------------------------------------------
# test_synthesize_fallback_on_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_fallback_on_error():
    """messages.parse raises → returns AgentResult with error field set."""
    mock_client = MagicMock()
    mock_client.messages.parse = AsyncMock(side_effect=Exception("structured output failed"))

    with patch("src.v3.synthesizer.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_synthesize(PROJECT, _make_evidence(), api_key="test-key")

    assert isinstance(result, AgentResult)
    assert result.error is not None
    assert result.error.category == "anthropic_error"
    assert "structured output failed" in result.error.message
    # searches_performed should still be populated from evidence
    assert len(result.searches_performed) >= 1


# ---------------------------------------------------------------------------
# test_prompt_includes_evidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_includes_evidence():
    """Verify the prompt passed to the LLM contains evidence text from the store."""
    captured_calls: list[dict] = []

    async def capture_parse(**kwargs):
        captured_calls.append(kwargs)
        fake_synthesis = _SynthesisResult(
            epc_contractor="Mortenson",
            confidence="possible",
            reasoning="Some evidence",
        )
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=500), parsed_output=fake_synthesis)

    mock_client = MagicMock()
    mock_client.messages.parse = capture_parse

    ev = _make_evidence(n=2)

    with patch("src.v3.synthesizer.anthropic.AsyncAnthropic", return_value=mock_client):
        await llm_synthesize(PROJECT, ev, api_key="test-key")

    assert len(captured_calls) == 1
    messages = captured_calls[0]["messages"]
    prompt_text = messages[0]["content"]

    # Evidence text should appear in the prompt
    assert "Mortenson Construction" in prompt_text or "Clearway" in prompt_text
    assert "Copper Valley Solar" in prompt_text
    # Search queries should appear
    assert "query 0" in prompt_text or "query 1" in prompt_text


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_empty_evidence():
    """Synthesizer handles an empty evidence store gracefully."""
    fake_synthesis = _SynthesisResult(
        epc_contractor=None,
        confidence="unknown",
        reasoning="No evidence found.",
    )
    fake_response = SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=500), parsed_output=fake_synthesis)

    mock_client = MagicMock()
    mock_client.messages.parse = AsyncMock(return_value=fake_response)

    with patch("src.v3.synthesizer.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_synthesize(PROJECT, EvidenceStore(), api_key="test-key")

    assert result.confidence == "unknown"
    assert result.epc_contractor is None
    assert result.error is None


@pytest.mark.asyncio
async def test_synthesize_uses_evidence_searches_on_empty_parsed():
    """When parsed.searches_performed is empty, falls back to evidence.searches_performed."""
    fake_synthesis = _SynthesisResult(
        epc_contractor="SomeEPC",
        confidence="possible",
        reasoning="Indirect evidence only.",
        searches_performed=[],  # empty
    )
    fake_response = SimpleNamespace(usage=SimpleNamespace(input_tokens=2000, output_tokens=500), parsed_output=fake_synthesis)

    mock_client = MagicMock()
    mock_client.messages.parse = AsyncMock(return_value=fake_response)

    ev = _make_evidence(n=1)  # has 1 recorded search

    with patch("src.v3.synthesizer.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_synthesize(PROJECT, ev, api_key="test-key")

    # Should fall back to evidence.searches_performed
    assert len(result.searches_performed) >= 1
