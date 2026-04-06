"""Tests for the post-research reflection loop in research.py.

NOTE: _run_reflection and REFLECTION_MAX_RETRIES were removed from src/research.py.
These tests are skipped until the reflection loop is re-implemented.
"""

import pytest

pytest.skip(
    "src.research no longer exports _run_reflection or REFLECTION_MAX_RETRIES — "
    "reflection loop was removed; update these tests when it is re-added",
    allow_module_level=True,
)

from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from src.models import AgentResult  # noqa: E402

REFLECTION_MAX_RETRIES = 3  # placeholder so tests below are syntactically valid
_run_reflection = None  # placeholder


def _make_response(*, stop_reason="end_turn", content=None, input_tokens=100, output_tokens=50):
    """Build a mock API response."""
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content or [SimpleNamespace(type="text", text="Reflection looks good.")],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _make_tool_use_block(name, tool_input, block_id="tool-1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _make_text_block(text):
    return SimpleNamespace(type="text", text=text)


@pytest.mark.asyncio
async def test_reflection_no_gaps_returns_original():
    """Agent reflects and finds no issues — returns original result."""
    original = AgentResult(epc_contractor="McCarthy", confidence="confirmed")
    client = AsyncMock()
    client.messages.create = AsyncMock(
        return_value=_make_response(
            stop_reason="end_turn",
            content=[_make_text_block("Everything checks out. All tasks done.")],
        )
    )

    result, log, tokens = await _run_reflection(
        client,
        original,
        "session-1",
        [],
        MagicMock(content=[]),
        [],
        agent_log=[],
        total_tokens=0,
    )
    assert result.epc_contractor == "McCarthy"
    assert result.confidence == "confirmed"
    assert any("reflection" in str(entry) for entry in log)


@pytest.mark.asyncio
async def test_reflection_updated_report():
    """Agent reflects and calls report_findings with updated result."""
    original = AgentResult(epc_contractor="McCarthy", confidence="possible")

    # First call: agent calls report_findings with upgraded confidence
    updated_input = {
        "epc_contractor": "McCarthy Building Companies",
        "confidence": "likely",
        "sources": [],
        "reasoning": "Found additional source confirming.",
    }
    response = _make_response(
        stop_reason="tool_use",
        content=[
            _make_text_block("Found additional evidence."),
            _make_tool_use_block("report_findings", updated_input),
        ],
    )
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=response)

    result, log, tokens = await _run_reflection(
        client,
        original,
        "session-1",
        [],
        MagicMock(content=[]),
        [],
        agent_log=[],
        total_tokens=0,
    )
    # Should use the updated result, not the original
    assert result.epc_contractor == "McCarthy Building Companies"
    assert result.confidence == "likely"


@pytest.mark.asyncio
async def test_reflection_retry_then_report():
    """Agent identifies gap, uses tools, then reports."""
    original = AgentResult(epc_contractor="Unknown", confidence="unknown")

    # Turn 1: agent calls manage_todo read (not report_findings)
    turn1 = _make_response(
        stop_reason="tool_use",
        content=[_make_tool_use_block("manage_todo", {"operation": "read", "session_id": "s1"})],
    )
    # Turn 2: agent calls report_findings
    turn2 = _make_response(
        stop_reason="tool_use",
        content=[
            _make_tool_use_block(
                "report_findings",
                {
                    "epc_contractor": "Signal Energy",
                    "confidence": "possible",
                    "sources": [],
                    "reasoning": "Found after reflection.",
                },
                block_id="tool-2",
            )
        ],
    )

    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=[turn1, turn2])

    with patch("src.research.execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"tasks": [], "message": "No plan"}
        result, log, tokens = await _run_reflection(
            client,
            original,
            "session-1",
            [],
            MagicMock(content=[]),
            [],
            agent_log=[],
            total_tokens=0,
        )

    assert result.epc_contractor == "Signal Energy"
    assert result.confidence == "possible"


@pytest.mark.asyncio
async def test_reflection_max_retries_fallback():
    """Agent keeps using tools without reporting — hits max retries, falls back to original."""
    original = AgentResult(epc_contractor="McCarthy", confidence="likely")

    # Every turn: agent calls a tool but never report_findings
    tool_response = _make_response(
        stop_reason="tool_use",
        content=[_make_tool_use_block("web_search", {"query": "more info"})],
    )

    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=tool_response)

    with patch("src.research.execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"results": []}
        result, log, tokens = await _run_reflection(
            client,
            original,
            "session-1",
            [],
            MagicMock(content=[]),
            [],
            agent_log=[],
            total_tokens=0,
        )

    # Should fall back to original after max retries
    assert result.epc_contractor == "McCarthy"
    assert result.confidence == "likely"
    # Should have made REFLECTION_MAX_RETRIES + 1 API calls
    assert client.messages.create.call_count == REFLECTION_MAX_RETRIES + 1


@pytest.mark.asyncio
async def test_reflection_api_error_returns_original():
    """API error during reflection — returns original result gracefully."""
    import anthropic

    original = AgentResult(epc_contractor="Blattner", confidence="confirmed")

    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=anthropic.APIError(
            message="Rate limited",
            request=MagicMock(),
            body=None,
        )
    )

    result, log, tokens = await _run_reflection(
        client,
        original,
        "session-1",
        [],
        MagicMock(content=[]),
        [],
        agent_log=[],
        total_tokens=0,
    )
    assert result.epc_contractor == "Blattner"
    assert result.confidence == "confirmed"
