"""Tests for chat_agent.py — streaming chat loop with shared tool registry."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.chat_agent import run_chat_agent
from src.sse import StreamWriter
from src.tools import execute_tool

from tests.conftest import make_agent_result


# ---------------------------------------------------------------------------
# Helpers for mocking the Anthropic streaming API
# ---------------------------------------------------------------------------

def _make_event(event_type: str, **kwargs):
    """Build a mock streaming event."""
    ev = MagicMock()
    ev.type = event_type
    for k, v in kwargs.items():
        setattr(ev, k, v)
    return ev


def _text_block_start(index: int = 0):
    block = MagicMock()
    block.type = "text"
    return _make_event("content_block_start", index=index, content_block=block)


def _text_delta(text: str):
    delta = MagicMock()
    delta.type = "text_delta"
    delta.text = text
    return _make_event("content_block_delta", delta=delta)


def _block_stop():
    return _make_event("content_block_stop")


def _tool_block_start(tool_id: str, name: str, index: int = 1):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    return _make_event("content_block_start", index=index, content_block=block)


def _tool_input_delta(partial_json: str):
    delta = MagicMock()
    delta.type = "input_json_delta"
    delta.partial_json = partial_json
    return _make_event("content_block_delta", delta=delta)


def _mock_stream(events: list, final_message: MagicMock):
    """Build an async context manager that yields events, then exposes get_final_message."""

    class FakeStream:
        def __init__(self):
            self._events = events

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._events:
                raise StopAsyncIteration
            return self._events.pop(0)

        async def get_final_message(self):
            return final_message

    return FakeStream()


def _final_message(stop_reason: str = "end_turn", content=None):
    msg = MagicMock()
    msg.stop_reason = stop_reason
    msg.content = content or []
    return msg


def _parse_sse_types(collected: list[str]) -> list[str]:
    """Extract event types from collected SSE chunks."""
    types = []
    for c in collected:
        if c.strip() == "data: [DONE]":
            types.append("DONE")
        elif c.startswith("data: "):
            parsed = json.loads(c.removeprefix("data: ").strip())
            types.append(parsed["type"])
    return types


async def _run_chat(messages=None, conversation_id="conv-test"):
    """Run the chat agent generator and collect all SSE chunks."""
    writer = StreamWriter()
    collected = []
    async for chunk in run_chat_agent(
        messages or [{"role": "user", "content": "test"}],
        conversation_id,
        writer,
    ):
        collected.append(chunk)
    return collected


# ---------------------------------------------------------------------------
# Tool dispatch via shared registry
# ---------------------------------------------------------------------------

class TestToolRegistryDispatch:
    @patch("src.tools.search_projects.db")
    async def test_search_projects_returns_count(self, mock_db):
        mock_db.search_projects.return_value = [
            {"id": "p1", "project_name": "Alpha"},
            {"id": "p2", "project_name": "Beta"},
        ]

        result = await execute_tool("search_projects", {"state": "TX", "limit": 10})

        assert result["count"] == 2
        assert len(result["projects"]) == 2

    @patch("src.tools.search_projects.db")
    async def test_empty_results(self, mock_db):
        mock_db.search_projects.return_value = []

        result = await execute_tool("search_projects", {})

        assert result["count"] == 0
        assert result["projects"] == []

    @patch("src.tools.get_discoveries.db")
    async def test_get_discoveries_with_ids(self, mock_db):
        mock_db.get_discoveries_for_projects.return_value = [{"id": "d1"}]
        valid_uuid = "00000000-0000-0000-0000-000000000001"

        result = await execute_tool("get_discoveries", {"project_ids": [valid_uuid]})

        assert result["count"] == 1
        mock_db.get_discoveries_for_projects.assert_called_once_with([valid_uuid])

    @patch("src.tools.get_discoveries.db")
    async def test_get_discoveries_all(self, mock_db):
        mock_db.list_discoveries.return_value = [{"id": "d1"}, {"id": "d2"}]

        result = await execute_tool("get_discoveries", {})

        assert result["count"] == 2
        mock_db.list_discoveries.assert_called_once()

    async def test_unknown_tool_raises(self):
        import pytest
        with pytest.raises(KeyError, match="Unknown tool"):
            await execute_tool("nonexistent_tool", {})


# ---------------------------------------------------------------------------
# run_chat_agent — text-only response (no tool calls)
# ---------------------------------------------------------------------------

class TestChatAgentTextOnly:
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_streams_text_and_persists(self, MockClient, mock_db):
        """Agent returns text without calling tools."""
        events = [
            _text_block_start(),
            _text_delta("Hello "),
            _text_delta("world!"),
            _block_stop(),
        ]
        final = _final_message(stop_reason="end_turn")

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _mock_stream(events, final)
        MockClient.return_value = mock_client

        collected = await _run_chat(conversation_id="conv-1")

        types = _parse_sse_types(collected)
        assert "start" in types
        assert "text-start" in types
        assert types.count("text-delta") == 2
        assert "text-end" in types
        assert "finish" in types

        # Persistence
        mock_db.save_message.assert_called_once()
        call_args = mock_db.save_message.call_args
        assert call_args.kwargs["conversation_id"] == "conv-1"
        assert call_args.kwargs["role"] == "assistant"
        assert "Hello world!" in call_args.kwargs["content"]


# ---------------------------------------------------------------------------
# run_chat_agent — single tool round then text
# ---------------------------------------------------------------------------

class TestChatAgentSingleTool:
    @patch("src.chat_agent.execute_tool", new_callable=AsyncMock)
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_tool_then_text(self, MockClient, mock_db, mock_exec_tool):
        """Agent calls a tool, gets result, then responds with text."""

        # Round 1: tool call
        round1_events = [
            _tool_block_start("tc-1", "search_projects"),
            _tool_input_delta(json.dumps({"state": "TX"})),
            _block_stop(),
        ]
        round1_final = _final_message(
            stop_reason="tool_use",
            content=[MagicMock(type="tool_use", id="tc-1", name="search_projects", input={"state": "TX"})],
        )

        # Round 2: text response
        round2_events = [
            _text_block_start(),
            _text_delta("Found 3 projects in Texas."),
            _block_stop(),
        ]
        round2_final = _final_message(stop_reason="end_turn")

        mock_exec_tool.return_value = {"projects": [{"id": "p1"}], "count": 1}

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [
            _mock_stream(round1_events, round1_final),
            _mock_stream(round2_events, round2_final),
        ]
        MockClient.return_value = mock_client

        collected = await _run_chat()

        mock_exec_tool.assert_called_once_with("search_projects", {"state": "TX"})

        types = _parse_sse_types(collected)
        assert "tool-input-start" in types
        assert "tool-input-available" in types
        assert "tool-output-available" in types
        assert "text-delta" in types
        assert mock_client.messages.stream.call_count == 2


# ---------------------------------------------------------------------------
# run_chat_agent — multi-round tool loop
# ---------------------------------------------------------------------------

class TestChatAgentMultiRound:
    @patch("src.chat_agent.execute_tool", new_callable=AsyncMock)
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_two_tool_rounds_then_text(self, MockClient, mock_db, mock_exec_tool):
        """Agent calls tools twice, then responds with text."""

        # Round 1: search_projects
        r1_events = [
            _tool_block_start("tc-1", "search_projects"),
            _tool_input_delta(json.dumps({"state": "TX"})),
            _block_stop(),
        ]
        r1_final = _final_message(
            stop_reason="tool_use",
            content=[MagicMock(type="tool_use")],
        )

        # Round 2: web_search
        r2_events = [
            _tool_block_start("tc-2", "web_search"),
            _tool_input_delta(json.dumps({"query": "test"})),
            _block_stop(),
        ]
        r2_final = _final_message(
            stop_reason="tool_use",
            content=[MagicMock(type="tool_use")],
        )

        # Round 3: text
        r3_events = [
            _text_block_start(),
            _text_delta("Done researching."),
            _block_stop(),
        ]
        r3_final = _final_message(stop_reason="end_turn")

        mock_exec_tool.side_effect = [
            {"projects": [{"id": "p1"}], "count": 1},
            {"results": [{"title": "Article", "url": "https://example.com", "content": "McCarthy", "score": 0.9}]},
        ]

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [
            _mock_stream(r1_events, r1_final),
            _mock_stream(r2_events, r2_final),
            _mock_stream(r3_events, r3_final),
        ]
        MockClient.return_value = mock_client

        collected = await _run_chat()

        assert mock_exec_tool.call_count == 2
        assert mock_client.messages.stream.call_count == 3


# ---------------------------------------------------------------------------
# run_chat_agent — max tool rounds safety
# ---------------------------------------------------------------------------

class TestChatAgentMaxRounds:
    @patch("src.chat_agent.MAX_TOOL_ROUNDS", 2)
    @patch("src.chat_agent.execute_tool", new_callable=AsyncMock)
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_stops_after_max_rounds(self, MockClient, mock_db, mock_exec_tool):
        """Agent stops looping after MAX_TOOL_ROUNDS even if Claude keeps calling tools."""

        def make_tool_round(tool_id):
            events = [
                _tool_block_start(tool_id, "search_projects"),
                _tool_input_delta(json.dumps({})),
                _block_stop(),
            ]
            final = _final_message(
                stop_reason="tool_use",
                content=[MagicMock(type="tool_use")],
            )
            return _mock_stream(events, final)

        mock_exec_tool.return_value = {"projects": [], "count": 0}

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [
            make_tool_round("tc-1"),
            make_tool_round("tc-2"),
            make_tool_round("tc-3"),  # should NOT be reached
        ]
        MockClient.return_value = mock_client

        collected = await _run_chat()

        assert mock_client.messages.stream.call_count == 2
        assert mock_exec_tool.call_count == 2


# ---------------------------------------------------------------------------
# run_chat_agent — malformed tool input JSON
# ---------------------------------------------------------------------------

class TestChatAgentJsonError:
    @patch("src.chat_agent.execute_tool", new_callable=AsyncMock)
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_bad_json_falls_back_to_empty_dict(self, MockClient, mock_db, mock_exec_tool):
        """If tool input JSON is malformed, falls back to empty dict — no crash."""

        events = [
            _tool_block_start("tc-bad", "search_projects"),
            _tool_input_delta("{invalid json"),
            _block_stop(),
        ]
        round1_final = _final_message(
            stop_reason="tool_use",
            content=[MagicMock(type="tool_use")],
        )

        # Round 2: end
        round2_events = [
            _text_block_start(),
            _text_delta("OK"),
            _block_stop(),
        ]
        round2_final = _final_message(stop_reason="end_turn")

        mock_exec_tool.return_value = {"projects": [], "count": 0}

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [
            _mock_stream(events, round1_final),
            _mock_stream(round2_events, round2_final),
        ]
        MockClient.return_value = mock_client

        collected = await _run_chat()

        mock_exec_tool.assert_called_once_with("search_projects", {})


# ---------------------------------------------------------------------------
# run_chat_agent — save_message persistence
# ---------------------------------------------------------------------------

class TestChatAgentPersistence:
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_saves_assistant_message_with_parts(self, MockClient, mock_db):
        """After streaming completes, the full message + parts are persisted."""
        events = [
            _text_block_start(),
            _text_delta("Test reply"),
            _block_stop(),
        ]
        final = _final_message(stop_reason="end_turn")

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _mock_stream(events, final)
        MockClient.return_value = mock_client

        await _run_chat(conversation_id="conv-persist")

        mock_db.save_message.assert_called_once()
        call_kwargs = mock_db.save_message.call_args.kwargs
        assert call_kwargs["conversation_id"] == "conv-persist"
        assert call_kwargs["role"] == "assistant"
        assert call_kwargs["content"] == "Test reply"
        assert isinstance(call_kwargs["parts"], list)
        assert len(call_kwargs["parts"]) == 1
        assert call_kwargs["parts"][0]["type"] == "text"

    @patch("src.chat_agent.execute_tool", new_callable=AsyncMock)
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_parts_include_tool_invocations(self, MockClient, mock_db, mock_exec_tool):
        """Parts list includes tool-invocation entries after tool calls."""

        # Round 1: tool
        r1_events = [
            _tool_block_start("tc-1", "search_projects"),
            _tool_input_delta(json.dumps({"state": "TX"})),
            _block_stop(),
        ]
        r1_final = _final_message(
            stop_reason="tool_use",
            content=[MagicMock(type="tool_use")],
        )

        # Round 2: text
        r2_events = [
            _text_block_start(),
            _text_delta("Here you go."),
            _block_stop(),
        ]
        r2_final = _final_message(stop_reason="end_turn")

        mock_exec_tool.return_value = {"projects": [], "count": 0}

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [
            _mock_stream(r1_events, r1_final),
            _mock_stream(r2_events, r2_final),
        ]
        MockClient.return_value = mock_client

        await _run_chat(conversation_id="conv-parts")

        parts = mock_db.save_message.call_args.kwargs["parts"]
        part_types = [p["type"] for p in parts]
        assert "tool-invocation" in part_types
        assert "text" in part_types

        tool_part = next(p for p in parts if p["type"] == "tool-invocation")
        assert tool_part["toolName"] == "search_projects"
        assert tool_part["input"] == {"state": "TX"}


# ---------------------------------------------------------------------------
# run_chat_agent — SSE event ordering
# ---------------------------------------------------------------------------

class TestChatAgentEventOrdering:
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_start_and_finish_bookend_stream(self, MockClient, mock_db):
        """Every stream starts with start/start-step and ends with finish-step/finish/DONE."""
        events = [
            _text_block_start(),
            _text_delta("hi"),
            _block_stop(),
        ]
        final = _final_message(stop_reason="end_turn")

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = _mock_stream(events, final)
        MockClient.return_value = mock_client

        collected = await _run_chat()
        types = _parse_sse_types(collected)

        assert types[0] == "start"
        assert types[1] == "start-step"
        assert types[-3] == "finish-step"
        assert types[-2] == "finish"
        assert types[-1] == "DONE"

    @patch("src.chat_agent.execute_tool", new_callable=AsyncMock)
    @patch("src.chat_agent.db")
    @patch("src.chat_agent.anthropic.AsyncAnthropic")
    async def test_step_boundaries_around_tool_rounds(self, MockClient, mock_db, mock_exec_tool):
        """Each tool round gets finish-step + start-step boundaries."""

        # Round 1: tool
        r1_events = [
            _tool_block_start("tc-1", "get_discoveries"),
            _tool_input_delta(json.dumps({})),
            _block_stop(),
        ]
        r1_final = _final_message(
            stop_reason="tool_use",
            content=[MagicMock(type="tool_use")],
        )

        # Round 2: text
        r2_events = [
            _text_block_start(),
            _text_delta("Done."),
            _block_stop(),
        ]
        r2_final = _final_message(stop_reason="end_turn")

        mock_exec_tool.return_value = {"discoveries": [], "count": 0}

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [
            _mock_stream(r1_events, r1_final),
            _mock_stream(r2_events, r2_final),
        ]
        MockClient.return_value = mock_client

        collected = await _run_chat()
        types = _parse_sse_types(collected)

        # Between tool rounds there should be finish-step, start-step pair
        for i, t in enumerate(types):
            if t == "finish-step" and i + 1 < len(types) and types[i + 1] != "finish":
                assert types[i + 1] == "start-step", f"Expected start-step after finish-step at index {i}"
