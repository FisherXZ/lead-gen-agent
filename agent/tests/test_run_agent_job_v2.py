"""Tests for _run_agent_job_v2 — the active chat agent background runner.

Covers:
  - SSE lifecycle (start/finish bookends)
  - Text-only response: text_start / text_delta / text_end in output
  - Tool round → text: text-* events (not thinking-*) after tool calls
  - tool-input-start and tool-output-available SSE events
  - Escalation: properly wrapped text part (start + delta + end)
  - db.save_message called with correct args
  - all_parts persistence (tool-invocation + text)
  - CancelledError → clean finish events emitted
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.main import _run_agent_job_v2
from src.sse import StreamWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_events(raw: list[str]) -> list[dict]:
    result = []
    for e in raw:
        if e.strip() == "data: [DONE]":
            result.append({"type": "DONE"})
        elif e.startswith("data: "):
            result.append(json.loads(e.removeprefix("data: ").strip()))
    return result


def _types(raw: list[str]) -> list[str]:
    return [e["type"] for e in _parse_events(raw)]


class MockJob:
    def __init__(self):
        self.job_id = "test-job-1"
        self.events: list[str] = []

    def append_event(self, event: str) -> None:
        self.events.append(event)


def _make_runtime_mock(event_sequence: list[dict], messages_passthrough=None):
    """Return a mock runtime whose run_turn fires on_event with event_sequence."""

    async def mock_run_turn(messages, on_event):
        for evt in event_sequence:
            on_event(evt)
        from src.runtime.types import TurnResult
        return TurnResult(
            messages=messages_passthrough or messages,
            usage={},
            iterations=len([e for e in event_sequence if e["type"] == "tool_result"]) + 1,
        )

    mock = MagicMock()
    mock.run_turn = mock_run_turn
    return mock


async def _run(event_sequence: list[dict], conversation_id: str = "conv-1") -> MockJob:
    job = MockJob()
    mock_runtime = _make_runtime_mock(event_sequence)
    with (
        patch("src.main.build_chat_runtime", return_value=mock_runtime),
        patch("src.main.db"),
        patch("src.main.mark_job_done"),
    ):
        await _run_agent_job_v2(
            job,
            [{"role": "user", "content": "test"}],
            conversation_id,
            StreamWriter(),
        )
    return job


# ---------------------------------------------------------------------------
# SSE lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_lifecycle_bookends():
    """Every response starts with start + start-step and ends with finish-step + finish + DONE."""
    job = await _run([
        {"type": "text_start"},
        {"type": "text_delta", "text": "Hello"},
        {"type": "text_end"},
    ])
    types = _types(job.events)
    assert types[0] == "start"
    assert types[1] == "start-step"
    assert types[-3] == "finish-step"
    assert types[-2] == "finish"
    assert types[-1] == "DONE"


# ---------------------------------------------------------------------------
# Text-only response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_only_emits_text_start_delta_end():
    """Text-only response streams text-start, text-delta, text-end."""
    job = await _run([
        {"type": "text_start"},
        {"type": "text_delta", "text": "Hi there"},
        {"type": "text_end"},
    ])
    types = _types(job.events)
    assert "text-start" in types
    assert "text-delta" in types
    assert "text-end" in types
    assert "thinking-start" not in types
    assert "thinking-delta" not in types


@pytest.mark.asyncio
async def test_text_delta_content_preserved():
    """text-delta event contains the correct text."""
    job = await _run([
        {"type": "text_start"},
        {"type": "text_delta", "text": "Pick: Alpha Solar"},
        {"type": "text_end"},
    ])
    parsed = _parse_events(job.events)
    deltas = [e for e in parsed if e["type"] == "text-delta"]
    assert len(deltas) == 1
    assert deltas[0]["delta"] == "Pick: Alpha Solar"


# ---------------------------------------------------------------------------
# Tool round → final text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_after_tool_round_uses_text_events_not_thinking():
    """After a tool call, the final response must use text-* not thinking-* events."""
    job = await _run([
        {"type": "tool_input_start", "tool_name": "think", "tool_id": "tc-1"},
        {"type": "tool_result", "tool_name": "think", "tool_id": "tc-1",
         "input": {"thought": "reasoning..."}, "result": {"recorded": True}},
        {"type": "text_start"},
        {"type": "text_delta", "text": "My top 3 picks are:"},
        {"type": "text_end"},
    ])
    types = _types(job.events)
    assert "text-start" in types, f"Expected text-start, got: {types}"
    assert "text-delta" in types
    assert "text-end" in types
    assert "thinking-start" not in types, f"Got thinking-start: {types}"
    assert "thinking-delta" not in types


@pytest.mark.asyncio
async def test_tool_input_start_emits_sse_event():
    """tool_input_start fires tool-input-start SSE event."""
    job = await _run([
        {"type": "tool_input_start", "tool_name": "search_projects", "tool_id": "tc-2"},
        {"type": "tool_result", "tool_name": "search_projects", "tool_id": "tc-2",
         "input": {"state": "TX"}, "result": {"count": 5, "projects": []}},
        {"type": "text_start"},
        {"type": "text_delta", "text": "Done."},
        {"type": "text_end"},
    ])
    types = _types(job.events)
    assert "tool-input-start" in types


@pytest.mark.asyncio
async def test_tool_result_emits_tool_output_available():
    """tool_result fires tool-output-available SSE event with the result payload."""
    job = await _run([
        {"type": "tool_input_start", "tool_name": "think", "tool_id": "tc-3"},
        {"type": "tool_result", "tool_name": "think", "tool_id": "tc-3",
         "input": {}, "result": {"recorded": True}},
        {"type": "text_start"},
        {"type": "text_delta", "text": "OK."},
        {"type": "text_end"},
    ])
    parsed = _parse_events(job.events)
    output_events = [e for e in parsed if e["type"] == "tool-output-available"]
    assert len(output_events) == 1
    assert output_events[0]["output"] == {"recorded": True}


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_emits_proper_text_part():
    """Escalation suggestion is wrapped in text-start + text-delta + text-end."""
    job = await _run([
        {"type": "escalation", "suggestion": "I've hit my limit — please refine your query."},
    ])
    types = _types(job.events)
    assert "text-start" in types
    assert "text-delta" in types
    assert "text-end" in types
    parsed = _parse_events(job.events)
    delta = next(e for e in parsed if e["type"] == "text-delta")
    assert "limit" in delta["delta"]


@pytest.mark.asyncio
async def test_escalation_with_no_suggestion_emits_nothing():
    """Escalation event with empty suggestion does not emit any SSE text events."""
    job = await _run([
        {"type": "escalation", "suggestion": ""},
    ])
    types = _types(job.events)
    assert "text-start" not in types
    assert "text-delta" not in types


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_message_called_with_correct_args():
    """db.save_message receives correct conversation_id, role, and content."""
    job = MockJob()
    mock_runtime = _make_runtime_mock([
        {"type": "text_start"},
        {"type": "text_delta", "text": "Here is your answer."},
        {"type": "text_end"},
    ])
    mock_db = MagicMock()
    with (
        patch("src.main.build_chat_runtime", return_value=mock_runtime),
        patch("src.main.db", mock_db),
        patch("src.main.mark_job_done"),
    ):
        await _run_agent_job_v2(
            job,
            [{"role": "user", "content": "question"}],
            "conv-persist",
            StreamWriter(),
        )

    mock_db.save_message.assert_called_once()
    kwargs = mock_db.save_message.call_args.kwargs
    assert kwargs["conversation_id"] == "conv-persist"
    assert kwargs["role"] == "assistant"
    assert kwargs["content"] == "Here is your answer."


@pytest.mark.asyncio
async def test_all_parts_includes_tool_invocation_and_text():
    """all_parts passed to save_message contains tool-invocation and text entries."""
    job = MockJob()
    mock_runtime = _make_runtime_mock([
        {"type": "tool_input_start", "tool_name": "search_projects", "tool_id": "tc-p"},
        {"type": "tool_result", "tool_name": "search_projects", "tool_id": "tc-p",
         "input": {"state": "CA"}, "result": {"count": 2, "projects": []}},
        {"type": "text_start"},
        {"type": "text_delta", "text": "Found 2 projects."},
        {"type": "text_end"},
    ])
    mock_db = MagicMock()
    with (
        patch("src.main.build_chat_runtime", return_value=mock_runtime),
        patch("src.main.db", mock_db),
        patch("src.main.mark_job_done"),
    ):
        await _run_agent_job_v2(
            job,
            [{"role": "user", "content": "find projects"}],
            "conv-parts",
            StreamWriter(),
        )

    parts = mock_db.save_message.call_args.kwargs["parts"]
    part_types = [p["type"] for p in parts]
    assert "tool-invocation" in part_types
    assert "text" in part_types
    tool_part = next(p for p in parts if p["type"] == "tool-invocation")
    assert tool_part["toolName"] == "search_projects"
    assert tool_part["input"] == {"state": "CA"}


# ---------------------------------------------------------------------------
# CancelledError handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_error_emits_clean_finish_events():
    """If the agent job is cancelled, finish-step + finish + DONE are still emitted."""
    import asyncio

    job = MockJob()

    async def mock_run_turn_raises(messages, on_event):
        raise asyncio.CancelledError()

    mock_runtime = MagicMock()
    mock_runtime.run_turn = mock_run_turn_raises

    mock_db = MagicMock()
    with (
        patch("src.main.build_chat_runtime", return_value=mock_runtime),
        patch("src.main.db", mock_db),
        patch("src.main.mark_job_done"),
    ):
        await _run_agent_job_v2(
            job,
            [{"role": "user", "content": "test"}],
            "conv-cancel",
            StreamWriter(),
        )

    types = _types(job.events)
    assert "finish-step" in types
    assert "finish" in types
    assert "DONE" in types
