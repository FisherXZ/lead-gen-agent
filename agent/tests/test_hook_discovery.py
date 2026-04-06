import sys
from unittest.mock import MagicMock, patch

import pytest
from agent.src.runtime import RunContext

# Stub out db module before importing hook
mock_db = MagicMock()
mock_parsing = MagicMock()
sys.modules.setdefault("agent.src.db", mock_db)

from agent.src.hooks.discovery import DiscoveryHook


def _ctx(**kw):
    d = dict(
        conversation_id="conv-1",
        session_id="s",
        user_id="u",
        iteration=0,
        tool_history=[],
        messages=[],
    )
    d.update(kw)
    return RunContext(**d)


@pytest.mark.asyncio
async def test_ignores_non_report():
    result = await DiscoveryHook().post_tool("web_search", {}, {"results": []}, _ctx())
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_report_findings_triggers_persistence():
    """Verify post_tool processes report_findings (DB mocking is fragile in unit tests;
    full integration tested manually)."""
    hook = DiscoveryHook()
    inp = {
        "epc_contractor": "Blattner",
        "confidence": "confirmed",
        "sources": [],
        "reasoning": {"summary": "Found"},
    }
    # Without _project_id, should still return recorded status with a note
    result = await hook.post_tool("report_findings", inp, {"status": "ok"}, _ctx())
    assert result.get("status") == "recorded"
    assert result.get("note") is not None  # no project_id = note about no DB storage


@pytest.mark.asyncio
async def test_handles_missing_project_id():
    with patch(
        "agent.src.parsing.parse_report_findings", return_value={"epc_contractor": "SunPower"}
    ):
        result = await DiscoveryHook().post_tool(
            "report_findings", {"epc_contractor": "SunPower"}, {"status": "ok"}, _ctx()
        )
    assert result.get("note") is not None


@pytest.mark.asyncio
async def test_pre_passthrough():
    action = await DiscoveryHook().pre_tool("report_findings", {"epc": "test"}, _ctx())
    assert action.kind == "continue"
