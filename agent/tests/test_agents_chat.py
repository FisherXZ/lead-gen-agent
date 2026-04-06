import sys
from unittest.mock import MagicMock

# Stub supabase before any imports
sys.modules.setdefault("supabase", MagicMock())

from src.agents.chat import build_chat_runtime
from src.runtime import AgentRuntime


def test_build_chat_runtime():
    rt = build_chat_runtime(conversation_id="c", user_id="u", api_key="k")
    assert isinstance(rt, AgentRuntime)
    assert rt.conversation_id == "c" and rt.user_id == "u"


def test_chat_has_tools():
    rt = build_chat_runtime(conversation_id="c", user_id="u", api_key="k")
    names = [t["name"] for t in rt.tools]
    assert "web_search" in names and "report_findings" in names


def test_chat_has_hooks():
    assert len(build_chat_runtime(conversation_id="c", user_id="u", api_key="k").hooks) >= 3


def test_chat_escalation_user_mode():
    assert (
        build_chat_runtime(conversation_id="c", user_id="u", api_key="k").escalation.escalation_mode
        == "user"
    )
