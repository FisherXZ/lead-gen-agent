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
