"""Tests for InjectContextHook."""
import pytest
from agent.src.runtime import RunContext
from agent.src.hooks.inject_context import InjectContextHook

def _ctx(**kw):
    d = dict(conversation_id="conv-1", session_id="sess-1", user_id="u", iteration=0, tool_history=[], messages=[])
    d.update(kw)
    return RunContext(**d)

@pytest.mark.asyncio
async def test_injects_conversation_id_for_remember():
    action = await InjectContextHook().pre_tool("remember", {"fact": "test"}, _ctx(conversation_id="conv-42"))
    assert action.modified_input["_conversation_id"] == "conv-42"

@pytest.mark.asyncio
async def test_injects_conversation_id_for_recall():
    action = await InjectContextHook().pre_tool("recall", {"query": "epc"}, _ctx(conversation_id="conv-99"))
    assert action.modified_input["_conversation_id"] == "conv-99"

@pytest.mark.asyncio
async def test_injects_session_id_for_manage_todo():
    action = await InjectContextHook().pre_tool("manage_todo", {"action": "list"}, _ctx(session_id="sess-7"))
    assert action.modified_input["session_id"] == "sess-7"

@pytest.mark.asyncio
async def test_injects_session_id_for_research_scratchpad():
    action = await InjectContextHook().pre_tool("research_scratchpad", {"data": "x"}, _ctx(session_id="sess-3"))
    assert action.modified_input["session_id"] == "sess-3"

@pytest.mark.asyncio
async def test_no_injection_for_other_tools():
    action = await InjectContextHook().pre_tool("web_search", {"query": "test"}, _ctx())
    assert "_conversation_id" not in action.modified_input
    assert "session_id" not in action.modified_input

@pytest.mark.asyncio
async def test_does_not_overwrite_existing_session_id():
    action = await InjectContextHook().pre_tool("manage_todo", {"action": "list", "session_id": "custom"}, _ctx(session_id="sess-7"))
    assert action.modified_input["session_id"] == "custom"

@pytest.mark.asyncio
async def test_post_tool_passthrough():
    result = await InjectContextHook().post_tool("remember", {}, {"status": "ok"}, _ctx())
    assert result == {"status": "ok"}
