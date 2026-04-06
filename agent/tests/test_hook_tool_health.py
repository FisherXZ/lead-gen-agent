import pytest
from agent.src.runtime import RunContext
from agent.src.hooks.tool_health import ToolHealthHook

def _ctx(**kw):
    d = dict(conversation_id="c", session_id="s", user_id="u", iteration=0, tool_history=[], messages=[])
    d.update(kw)
    return RunContext(**d)

@pytest.mark.asyncio
async def test_no_warning_on_success():
    result = await ToolHealthHook(error_threshold=3).post_tool("web_search", {}, {"results": ["ok"]}, _ctx())
    assert "_guidance" not in result

@pytest.mark.asyncio
async def test_warning_after_consecutive_errors():
    hook = ToolHealthHook(error_threshold=3)
    ctx = _ctx()
    await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    await hook.post_tool("web_search", {}, {"error": "500"}, ctx)
    result = await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    assert "_guidance" in result

@pytest.mark.asyncio
async def test_success_resets_counter():
    hook = ToolHealthHook(error_threshold=3)
    ctx = _ctx()
    await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    await hook.post_tool("web_search", {}, {"error": "500"}, ctx)
    await hook.post_tool("web_search", {}, {"results": ["ok"]}, ctx)
    result = await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    assert "_guidance" not in result

@pytest.mark.asyncio
async def test_pre_tool_passthrough():
    action = await ToolHealthHook().pre_tool("web_search", {"q": "test"}, _ctx())
    assert action.kind == "continue"
