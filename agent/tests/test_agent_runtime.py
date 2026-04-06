"""Tests for AgentRuntime core loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.runtime.agent_runtime import AgentRuntime
from src.runtime.compactor import Compactor
from src.runtime.escalation import EscalationPolicy
from src.runtime.hooks import Hook
from src.runtime.types import HookAction


class MockContentBlock:
    def __init__(self, block_type, **kwargs):
        self.type = block_type
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockResponse:
    def __init__(self, stop_reason, content_blocks):
        self.stop_reason = stop_reason
        self.content = content_blocks
        self.usage = MagicMock(input_tokens=100, output_tokens=50)


def _text_response(text="Hello!"):
    return MockResponse("end_turn", [MockContentBlock("text", text=text)])


def _tool_response(name, inp, tid="tool-1"):
    return MockResponse("tool_use", [MockContentBlock("tool_use", id=tid, name=name, input=inp)])


class NoOpHook(Hook):
    async def pre_tool(self, n, i, c):
        return HookAction.continue_with(i)

    async def post_tool(self, n, i, r, c):
        return r


@pytest.mark.asyncio
async def test_simple_text():
    rt = AgentRuntime(
        system_prompt="test",
        tools=[],
        hooks=[],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="k",
    )
    with patch.object(rt, "_call_api", new_callable=AsyncMock) as mock:
        mock.return_value = _text_response("Hi")
        result = await rt.run_turn([{"role": "user", "content": "Hi"}], lambda e: None)
    assert result.iterations == 1


@pytest.mark.asyncio
async def test_tool_call():
    td = {
        "name": "web_search",
        "description": "S",
        "input_schema": {"type": "object", "properties": {}},
    }
    rt = AgentRuntime(
        system_prompt="t",
        tools=[td],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="k",
    )
    with (
        patch.object(rt, "_call_api", new_callable=AsyncMock) as mock_api,
        patch.object(rt, "_execute_tool", new_callable=AsyncMock) as mock_exec,
    ):
        mock_api.side_effect = [
            _tool_response("web_search", {"query": "test"}),
            _text_response("Done"),
        ]
        mock_exec.return_value = {"results": [{"title": "R1"}]}
        result = await rt.run_turn([{"role": "user", "content": "search"}], lambda e: None)
    assert result.iterations == 2
    mock_exec.assert_called_once_with("web_search", {"query": "test"})


@pytest.mark.asyncio
async def test_hooks_called():
    pre, post = [], []

    class TrackHook(Hook):
        async def pre_tool(self, n, i, c):
            pre.append(n)
            return HookAction.continue_with(i)

        async def post_tool(self, n, i, r, c):
            post.append(n)
            return r

    td = {
        "name": "web_search",
        "description": "S",
        "input_schema": {"type": "object", "properties": {}},
    }
    rt = AgentRuntime(
        system_prompt="t",
        tools=[td],
        hooks=[TrackHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="k",
    )
    with (
        patch.object(rt, "_call_api", new_callable=AsyncMock) as m1,
        patch.object(rt, "_execute_tool", new_callable=AsyncMock) as m2,
    ):
        m1.side_effect = [_tool_response("web_search", {}), _text_response()]
        m2.return_value = {}
        await rt.run_turn([{"role": "user", "content": "x"}], lambda e: None)
    assert pre == ["web_search"] and post == ["web_search"]


@pytest.mark.asyncio
async def test_hook_deny():
    class DenyHook(Hook):
        async def pre_tool(self, n, i, c):
            return HookAction.deny("blocked")

        async def post_tool(self, n, i, r, c):
            return r

    td = {"name": "x", "description": "X", "input_schema": {"type": "object", "properties": {}}}
    rt = AgentRuntime(
        system_prompt="t",
        tools=[td],
        hooks=[DenyHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="k",
    )
    with (
        patch.object(rt, "_call_api", new_callable=AsyncMock) as m1,
        patch.object(rt, "_execute_tool", new_callable=AsyncMock) as m2,
    ):
        m1.side_effect = [_tool_response("x", {}), _text_response()]
        await rt.run_turn([{"role": "user", "content": "do"}], lambda e: None)
    m2.assert_not_called()


@pytest.mark.asyncio
async def test_hard_stop():
    td = {
        "name": "web_search",
        "description": "S",
        "input_schema": {"type": "object", "properties": {}},
    }
    rt = AgentRuntime(
        system_prompt="t",
        tools=[td],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=2),
        api_key="k",
    )
    with (
        patch.object(rt, "_call_api", new_callable=AsyncMock) as m1,
        patch.object(rt, "_execute_tool", new_callable=AsyncMock) as m2,
    ):
        m1.return_value = _tool_response("web_search", {})
        m2.return_value = {}
        result = await rt.run_turn([{"role": "user", "content": "loop"}], lambda e: None)
    assert result.iterations <= 3


# ---------------------------------------------------------------------------
# _call_api streaming unit tests
# ---------------------------------------------------------------------------


def _mk_stream_event(etype, **kw):
    ev = MagicMock()
    ev.type = etype
    for k, v in kw.items():
        setattr(ev, k, v)
    return ev


def _fake_stream(events, stop_reason="end_turn"):
    final = MagicMock()
    final.stop_reason = stop_reason
    final.content = []
    final.usage = MagicMock(
        input_tokens=10, output_tokens=5,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )

    class FakeStream:
        def __init__(self):
            self._events = list(events)

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
            return final

    return FakeStream()


def _make_rt():
    return AgentRuntime(
        system_prompt="test", tools=[], hooks=[],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="k",
    )


@pytest.mark.asyncio
async def test_call_api_text_block_emits_start_delta_end():
    """_call_api must emit text_start, text_delta, and text_end (in order)
    when a text content block starts, produces a delta, and then stops."""
    rt = _make_rt()

    text_block = MagicMock()
    text_block.type = "text"

    text_delta_obj = MagicMock()
    text_delta_obj.type = "text_delta"
    text_delta_obj.text = "Hello world"

    stream_events = [
        _mk_stream_event("content_block_start", content_block=text_block),
        _mk_stream_event("content_block_delta", delta=text_delta_obj),
        _mk_stream_event("content_block_stop"),
    ]

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _fake_stream(stream_events)
    rt._client = mock_client

    emitted: list[dict] = []
    await rt._call_api(
        [{"role": "user", "content": "hi"}],
        on_event=lambda e: emitted.append(e),
    )

    types = [e["type"] for e in emitted]
    assert types == ["text_start", "text_delta", "text_end"], (
        f"Expected exactly [text_start, text_delta, text_end], got: {types}"
    )
    delta_events = [e for e in emitted if e["type"] == "text_delta"]
    assert delta_events[0]["text"] == "Hello world", (
        f"Expected text_delta to carry 'Hello world', got: {delta_events}"
    )


@pytest.mark.asyncio
async def test_call_api_tool_block_emits_input_start_and_available():
    """_call_api must emit tool_input_start then tool_input_available with parsed
    input dict when a tool_use content block starts, accumulates JSON, then stops."""
    rt = _make_rt()

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "web_search"
    tool_block.id = "tc-1"

    input_delta_obj = MagicMock()
    input_delta_obj.type = "input_json_delta"
    input_delta_obj.partial_json = '{"query": "test"}'

    stream_events = [
        _mk_stream_event("content_block_start", content_block=tool_block),
        _mk_stream_event("content_block_delta", delta=input_delta_obj),
        _mk_stream_event("content_block_stop"),
    ]

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _fake_stream(stream_events)
    rt._client = mock_client

    emitted: list[dict] = []
    await rt._call_api(
        [{"role": "user", "content": "search"}],
        on_event=lambda e: emitted.append(e),
    )

    types = [e["type"] for e in emitted]
    assert "tool_input_start" in types, f"Expected tool_input_start, got: {types}"
    assert "tool_input_available" in types, f"Expected tool_input_available, got: {types}"

    available = next(e for e in emitted if e["type"] == "tool_input_available")
    assert available["input"] == {"query": "test"}, (
        f"Expected input={{'query': 'test'}}, got: {available['input']}"
    )


@pytest.mark.asyncio
async def test_call_api_malformed_tool_json_falls_back_to_empty():
    """_call_api must emit tool_input_available with input={} when the
    accumulated JSON for a tool block cannot be parsed."""
    rt = _make_rt()

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "web_search"
    tool_block.id = "tc-bad"

    input_delta_obj = MagicMock()
    input_delta_obj.type = "input_json_delta"
    input_delta_obj.partial_json = "{not valid json"

    stream_events = [
        _mk_stream_event("content_block_start", content_block=tool_block),
        _mk_stream_event("content_block_delta", delta=input_delta_obj),
        _mk_stream_event("content_block_stop"),
    ]

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = _fake_stream(stream_events)
    rt._client = mock_client

    emitted: list[dict] = []
    await rt._call_api(
        [{"role": "user", "content": "search"}],
        on_event=lambda e: emitted.append(e),
    )

    available = next(
        (e for e in emitted if e["type"] == "tool_input_available"), None
    )
    assert available is not None, "Expected tool_input_available to be emitted"
    assert available["input"] == {}, (
        f"Expected empty dict fallback for malformed JSON, got: {available['input']}"
    )
