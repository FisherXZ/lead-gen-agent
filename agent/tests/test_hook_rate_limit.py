import pytest
from src.hooks.rate_limit import RateLimitHook
from src.runtime import RunContext


def _ctx(**kw):
    d = dict(
        conversation_id="c", session_id="s", user_id="u", iteration=0, tool_history=[], messages=[]
    )
    d.update(kw)
    return RunContext(**d)


@pytest.mark.asyncio
async def test_allows_under_limit():
    action = await RateLimitHook(limits={"remember": 5}).pre_tool(
        "remember", {"fact": "x"}, _ctx(tool_history=["remember", "remember"])
    )
    assert action.kind == "continue"


@pytest.mark.asyncio
async def test_denies_at_limit():
    action = await RateLimitHook(limits={"remember": 3}).pre_tool(
        "remember", {"fact": "x"}, _ctx(tool_history=["remember"] * 3)
    )
    assert action.kind == "deny" and "rate limit" in action.reason.lower()


@pytest.mark.asyncio
async def test_no_limit_for_unlisted():
    action = await RateLimitHook(limits={"remember": 5}).pre_tool(
        "web_search", {}, _ctx(tool_history=["web_search"] * 100)
    )
    assert action.kind == "continue"


@pytest.mark.asyncio
async def test_counts_only_matching():
    action = await RateLimitHook(limits={"remember": 2}).pre_tool(
        "remember", {}, _ctx(tool_history=["web_search", "remember", "fetch_page", "remember"])
    )
    assert action.kind == "deny"


@pytest.mark.asyncio
async def test_post_passthrough():
    result = await RateLimitHook().post_tool("remember", {}, {"ok": True}, _ctx())
    assert result == {"ok": True}
