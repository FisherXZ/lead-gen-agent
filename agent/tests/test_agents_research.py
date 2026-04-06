import sys
from unittest.mock import MagicMock
sys.modules.setdefault("supabase", MagicMock())

from agent.src.agents.research import build_research_runtime, RESEARCH_TOOL_NAMES
from agent.src.runtime import AgentRuntime

def test_build_research_runtime():
    assert isinstance(build_research_runtime(project={"id": 1}, api_key="k"), AgentRuntime)

def test_research_limited_tools():
    rt = build_research_runtime(project={"id": 1}, api_key="k")
    names = [t["name"] for t in rt.tools]
    assert "web_search" in names and "batch_research_epc" not in names

def test_research_autonomous():
    assert build_research_runtime(project={"id": 1}, api_key="k").escalation.escalation_mode == "autonomous"

def test_research_tool_names_valid():
    from agent.src.tools import get_tool_names
    registered = get_tool_names()
    for name in RESEARCH_TOOL_NAMES:
        assert name in registered, f"'{name}' not in registry"
