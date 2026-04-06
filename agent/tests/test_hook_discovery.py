import sys, pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agent.src.runtime import RunContext

# Stub out db module before importing hook
mock_db = MagicMock()
mock_parsing = MagicMock()
sys.modules.setdefault("agent.src.db", mock_db)

from agent.src.hooks.discovery import DiscoveryHook

def _ctx(**kw):
    d = dict(conversation_id="conv-1", session_id="s", user_id="u", iteration=0, tool_history=[], messages=[])
    d.update(kw)
    return RunContext(**d)

@pytest.mark.asyncio
async def test_ignores_non_report():
    result = await DiscoveryHook().post_tool("web_search", {}, {"results": []}, _ctx())
    assert result == {"results": []}

@pytest.mark.asyncio
async def test_persists_discovery():
    hook = DiscoveryHook()
    inp = {"epc_contractor": "Blattner", "confidence": "confirmed", "sources": [], "reasoning": {"summary": "Found"}, "_project_id": 42}
    with patch("agent.src.parsing.parse_report_findings", return_value={"epc_contractor": "Blattner"}) as mp:
        # Mock the lazy imports inside post_tool
        mock_db_mod = MagicMock()
        mock_db_mod.get_project.return_value = {"id": 42, "project_name": "Test"}
        mock_db_mod.store_discovery.return_value = {"id": 99}
        with patch.dict(sys.modules, {"agent.src.db": mock_db_mod}):
            result = await hook.post_tool("report_findings", inp, {"status": "ok"}, _ctx())
    assert result.get("discovery_id") == 99

@pytest.mark.asyncio
async def test_handles_missing_project_id():
    with patch("agent.src.parsing.parse_report_findings", return_value={"epc_contractor": "SunPower"}):
        result = await DiscoveryHook().post_tool("report_findings", {"epc_contractor": "SunPower"}, {"status": "ok"}, _ctx())
    assert result.get("note") is not None

@pytest.mark.asyncio
async def test_pre_passthrough():
    action = await DiscoveryHook().pre_tool("report_findings", {"epc": "test"}, _ctx())
    assert action.kind == "continue"
