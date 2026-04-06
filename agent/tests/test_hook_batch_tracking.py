import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub modules before import
mock_db = MagicMock()
mock_bp = MagicMock()
sys.modules.setdefault("agent.src.db", mock_db)
sys.modules.setdefault("agent.src.batch_progress", mock_bp)

from agent.src.hooks.batch_tracking import BatchTrackingHook
from agent.src.runtime import RunContext


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
async def test_ignores_non_batch():
    action = await BatchTrackingHook().pre_tool("web_search", {"query": "test"}, _ctx())
    assert "_batch_id" not in action.modified_input


@pytest.mark.asyncio
async def test_injects_batch_id():
    mock_db_mod = MagicMock()
    mock_db_mod.get_project.side_effect = lambda pid: {
        "id": pid,
        "project_name": f"P{pid}",
        "queue_id": f"Q{pid}",
    }
    mock_bp_mod = MagicMock()
    mock_bp_mod.create_batch.return_value = MagicMock(cancelled=False, projects=[], total=3)
    mock_bp_mod.get_cancel_event.return_value = MagicMock()

    with patch.dict(
        sys.modules, {"agent.src.db": mock_db_mod, "agent.src.batch_progress": mock_bp_mod}
    ):
        action = await BatchTrackingHook().pre_tool(
            "batch_research_epc", {"project_ids": [1, 2, 3]}, _ctx()
        )
    assert action.kind == "continue"
    assert "_batch_id" in action.modified_input
    assert "_progress_callback" in action.modified_input


@pytest.mark.asyncio
async def test_post_marks_done():
    hook = BatchTrackingHook()
    mock_bp_mod = MagicMock()
    with patch.dict(sys.modules, {"agent.src.batch_progress": mock_bp_mod}):
        await hook.post_tool(
            "batch_research_epc", {"_batch_id": "batch-42"}, {"results": []}, _ctx()
        )
    mock_bp_mod.mark_done.assert_called_once_with("batch-42")


@pytest.mark.asyncio
async def test_pre_passthrough_other():
    action = await BatchTrackingHook().pre_tool("remember", {"fact": "x"}, _ctx())
    assert "_batch_id" not in action.modified_input
