import sys, pytest
from unittest.mock import AsyncMock, patch, MagicMock
sys.modules.setdefault("supabase", MagicMock())
from agent.src.tools.run_research import DEFINITION, execute

def test_definition():
    assert DEFINITION["name"] == "run_research"
    assert "project_id" in DEFINITION["input_schema"]["required"]

@pytest.mark.asyncio
async def test_execute_calls_runtime():
    mock_rt = MagicMock()
    mock_rt.run_turn = AsyncMock(return_value=MagicMock(
        messages=[{"role": "assistant", "content": [{"type": "text", "text": "Found EPC: Blattner"}]}],
        iterations=5,
    ))
    with patch("agent.src.agents.research.build_research_runtime", return_value=mock_rt), \
         patch("agent.src.db.get_project", return_value={"id": 42, "project_name": "Test Solar"}), \
         patch("agent.src.knowledge_base.build_knowledge_context", return_value=""), \
         patch("agent.src.prompts.build_user_message", return_value="Research this"):
        result = await execute({"project_id": 42, "_api_key": "k"})
    assert "findings" in result
    assert result["iterations"] == 5
