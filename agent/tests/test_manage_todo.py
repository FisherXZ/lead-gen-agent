"""Tests for the manage_todo tool."""

from unittest.mock import patch

import pytest

from src.tools.manage_todo import execute


@pytest.fixture
def mock_db():
    """Mock DB calls for manage_todo."""
    with (
        patch("src.tools.manage_todo.upsert_scratch") as mock_upsert,
        patch("src.tools.manage_todo.read_scratch") as mock_read,
    ):
        yield mock_upsert, mock_read


# --- CREATE ---


@pytest.mark.asyncio
async def test_create_basic(mock_db):
    mock_upsert, _ = mock_db
    tasks = [
        {"id": 1, "description": "Search SEC EDGAR"},
        {"id": 2, "description": "Check EPC portfolios"},
    ]
    result = await execute({"operation": "create", "session_id": "s1", "tasks": tasks})
    assert result["status"] == "created"
    assert result["task_count"] == 2
    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_create_empty_tasks(mock_db):
    mock_upsert, _ = mock_db
    result = await execute({"operation": "create", "session_id": "s1", "tasks": []})
    assert result["status"] == "created"
    assert result["task_count"] == 0


@pytest.mark.asyncio
async def test_create_duplicate_ids(mock_db):
    tasks = [
        {"id": 1, "description": "Task A"},
        {"id": 1, "description": "Task B"},
    ]
    result = await execute({"operation": "create", "session_id": "s1", "tasks": tasks})
    assert "error" in result
    assert "Duplicate" in result["error"]


@pytest.mark.asyncio
async def test_create_defaults_status_to_pending(mock_db):
    mock_upsert, _ = mock_db
    tasks = [{"id": 1, "description": "Do something"}]
    await execute({"operation": "create", "session_id": "s1", "tasks": tasks})
    # Check the tasks passed to upsert have status defaulted
    call_args = mock_upsert.call_args
    stored_tasks = call_args[0][2]["tasks"]
    assert stored_tasks[0]["status"] == "pending"


# --- UPDATE ---


@pytest.mark.asyncio
async def test_update_existing_task(mock_db):
    mock_upsert, mock_read = mock_db
    mock_read.return_value = [
        {
            "value": {
                "tasks": [
                    {
                        "id": 1,
                        "description": "Search SEC EDGAR",
                        "status": "pending",
                        "result_summary": "",
                    },
                ]
            }
        }
    ]
    result = await execute(
        {
            "operation": "update",
            "session_id": "s1",
            "tasks": [{"id": 1, "status": "done", "result_summary": "Found 3 filings"}],
        }
    )
    assert result["status"] == "updated"
    assert 1 in result["updated_ids"]


@pytest.mark.asyncio
async def test_update_before_create(mock_db):
    _, mock_read = mock_db
    mock_read.return_value = []
    result = await execute(
        {
            "operation": "update",
            "session_id": "s1",
            "tasks": [{"id": 1, "status": "done"}],
        }
    )
    assert "error" in result
    assert "create" in result["error"].lower()


@pytest.mark.asyncio
async def test_update_adds_new_task(mock_db):
    mock_upsert, mock_read = mock_db
    mock_read.return_value = [
        {
            "value": {
                "tasks": [
                    {
                        "id": 1,
                        "description": "Existing task",
                        "status": "done",
                        "result_summary": "Done",
                    },
                ]
            }
        }
    ]
    result = await execute(
        {
            "operation": "update",
            "session_id": "s1",
            "tasks": [{"id": 2, "description": "New task"}],
        }
    )
    assert result["status"] == "updated"
    assert 2 in result["added_ids"]
    assert result["total_tasks"] == 2


# --- READ ---


@pytest.mark.asyncio
async def test_read_existing_todo(mock_db):
    _, mock_read = mock_db
    mock_read.return_value = [
        {
            "value": {
                "tasks": [
                    {
                        "id": 1,
                        "description": "Task A",
                        "status": "done",
                        "result_summary": "Found it",
                    },
                    {"id": 2, "description": "Task B", "status": "pending", "result_summary": ""},
                ]
            }
        }
    ]
    result = await execute({"operation": "read", "session_id": "s1"})
    assert len(result["tasks"]) == 2
    assert result["summary"]["total"] == 2
    assert result["summary"]["done"] == 1
    assert result["summary"]["pending"] == 1
    assert result["summary"]["completion_rate"] == 0.5


@pytest.mark.asyncio
async def test_read_no_todo(mock_db):
    _, mock_read = mock_db
    mock_read.return_value = []
    result = await execute({"operation": "read", "session_id": "s1"})
    assert result["tasks"] == []
    assert "No plan" in result["message"]


# --- UNKNOWN OPERATION ---


@pytest.mark.asyncio
async def test_unknown_operation(mock_db):
    result = await execute({"operation": "delete", "session_id": "s1"})
    assert "error" in result
