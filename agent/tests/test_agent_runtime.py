"""Tests for the AgentRuntime core loop."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.src.runtime.agent_runtime import AgentRuntime
from agent.src.runtime.compactor import Compactor
from agent.src.runtime.escalation import EscalationPolicy
from agent.src.runtime.hooks import Hook
from agent.src.runtime.types import HookAction, RunContext


# -- Mock helpers --

class MockContentBlock:
    def __init__(self, block_type, **kwargs):
        self.type = block_type
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockResponse:
    def __init__(self, stop_reason, content_blocks):
        self.stop_reason = stop_reason
        self.content = content_blocks
        self.usage = MagicMock(input_tokens=100, output_tokens=50,
                                cache_creation_input_tokens=0,
                                cache_read_input_tokens=0)


def _text_response(text="Hello!"):
    """Mock a simple text response (no tool calls)."""
    return MockResponse(
        stop_reason="end_turn",
        content_blocks=[MockContentBlock("text", text=text)],
    )


def _tool_use_response(tool_name, tool_input, tool_id="tool-1"):
    """Mock a response that calls a tool."""
    return MockResponse(
        stop_reason="tool_use",
        content_blocks=[MockContentBlock(
            "tool_use", id=tool_id, name=tool_name, input=tool_input,
        )],
    )


class NoOpHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        return HookAction.continue_with(tool_input)
    async def post_tool(self, tool_name, tool_input, result, context):
        return result


# -- Tests --

@pytest.mark.asyncio
async def test_simple_text_response():
    """Runtime handles a simple text response with no tool calls."""
    events = []

    runtime = AgentRuntime(
        system_prompt="You are helpful.",
        tools=[],
        hooks=[],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = _text_response("Hello!")
        result = await runtime.run_turn(
            messages=[{"role": "user", "content": "Hi"}],
            on_event=events.append,
        )

    assert result.iterations == 1
    assert len(result.messages) > 0


@pytest.mark.asyncio
async def test_tool_call_and_response():
    """Runtime executes a tool call and feeds result back."""
    events = []
    tool_def = {"name": "web_search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}

    runtime = AgentRuntime(
        system_prompt="You are helpful.",
        tools=[tool_def],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    # First call: tool_use. Second call: end_turn.
    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            _tool_use_response("web_search", {"query": "test"}),
            _text_response("Found results."),
        ]
        mock_exec.return_value = {"results": [{"title": "Result 1"}]}

        result = await runtime.run_turn(
            messages=[{"role": "user", "content": "Search for test"}],
            on_event=events.append,
        )

    assert result.iterations == 2
    mock_exec.assert_called_once_with("web_search", {"query": "test"})


@pytest.mark.asyncio
async def test_hooks_run_on_tool_calls():
    """Pre and post hooks are called for each tool execution."""
    pre_called = []
    post_called = []

    class TrackingHook(Hook):
        async def pre_tool(self, tool_name, tool_input, context):
            pre_called.append(tool_name)
            return HookAction.continue_with(tool_input)
        async def post_tool(self, tool_name, tool_input, result, context):
            post_called.append(tool_name)
            return result

    runtime = AgentRuntime(
        system_prompt="test",
        tools=[{"name": "web_search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}],
        hooks=[TrackingHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            _tool_use_response("web_search", {"query": "test"}),
            _text_response("Done"),
        ]
        mock_exec.return_value = {"results": []}
        await runtime.run_turn(
            messages=[{"role": "user", "content": "search"}],
            on_event=lambda e: None,
        )

    assert pre_called == ["web_search"]
    assert post_called == ["web_search"]


@pytest.mark.asyncio
async def test_hook_deny_skips_tool():
    """A deny hook prevents tool execution."""
    class DenyAllHook(Hook):
        async def pre_tool(self, tool_name, tool_input, context):
            return HookAction.deny("blocked")
        async def post_tool(self, tool_name, tool_input, result, context):
            return result

    runtime = AgentRuntime(
        system_prompt="test",
        tools=[{"name": "blocked_tool", "description": "X", "input_schema": {"type": "object", "properties": {}}}],
        hooks=[DenyAllHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            _tool_use_response("blocked_tool", {}),
            _text_response("OK"),
        ]
        await runtime.run_turn(
            messages=[{"role": "user", "content": "do thing"}],
            on_event=lambda e: None,
        )

    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_hard_stop_on_max_iterations():
    """Runtime stops when escalation policy says hard_stop."""
    runtime = AgentRuntime(
        system_prompt="test",
        tools=[{"name": "web_search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=2),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        # Always return tool calls (would loop forever without hard stop)
        mock_api.return_value = _tool_use_response("web_search", {"query": "test"})
        mock_exec.return_value = {"results": []}

        result = await runtime.run_turn(
            messages=[{"role": "user", "content": "search forever"}],
            on_event=lambda e: None,
        )

    assert result.iterations <= 3  # max_iterations=2, may execute 1-2 tool rounds before stop
