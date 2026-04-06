"""Tests for Hook protocol and runners."""

import pytest
from src.runtime.hooks import Hook, run_post_hooks, run_pre_hooks
from src.runtime.types import HookAction, RunContext


class AllowAllHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        return result


class InjectIdHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        if tool_name == "remember":
            tool_input["_conversation_id"] = context.conversation_id
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        return result


class DenyHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        if tool_name == "blocked_tool":
            return HookAction.deny("not allowed")
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        return result


class AnnotateHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        result["_annotated"] = True
        return result


def _ctx(**kw):
    d = dict(
        conversation_id="c", session_id="s", user_id="u", iteration=0, tool_history=[], messages=[]
    )
    d.update(kw)
    return RunContext(**d)


@pytest.mark.asyncio
async def test_pre_hooks_pass_through():
    action = await run_pre_hooks([AllowAllHook()], "web_search", {"query": "test"}, _ctx())
    assert action.kind == "continue"


@pytest.mark.asyncio
async def test_pre_hooks_modify_input():
    action = await run_pre_hooks(
        [InjectIdHook()], "remember", {"fact": "x"}, _ctx(conversation_id="conv-42")
    )
    assert action.modified_input["_conversation_id"] == "conv-42"


@pytest.mark.asyncio
async def test_pre_hooks_deny_short_circuits():
    action = await run_pre_hooks([DenyHook(), InjectIdHook()], "blocked_tool", {}, _ctx())
    assert action.kind == "deny"


@pytest.mark.asyncio
async def test_post_hooks_transform():
    result = await run_post_hooks([AnnotateHook()], "web_search", {}, {"data": "x"}, _ctx())
    assert result["_annotated"] is True


@pytest.mark.asyncio
async def test_post_hooks_chain():
    result = await run_post_hooks(
        [AnnotateHook(), AllowAllHook()], "web_search", {}, {"data": "x"}, _ctx()
    )
    assert result["_annotated"] is True
