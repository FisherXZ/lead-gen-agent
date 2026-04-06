"""Tests for the batch_research_epc chat tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from src.chat_agent import _format_batch_progress
from src.tools.batch_research_epc import DEFINITION, execute

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_project(pid: str, name: str = "Solar Test") -> dict:
    return {
        "id": pid,
        "queue_id": f"Q-{pid}",
        "project_name": name,
        "developer": "TestDev",
        "state": "TX",
        "mw_capacity": 200,
    }


def _fake_discovery(pid: str) -> dict:
    return {
        "id": f"disc-{pid}",
        "project_id": pid,
        "epc_contractor": "McCarthy Building",
        "confidence": "likely",
        "review_status": "pending",
    }


# ---------------------------------------------------------------------------
# DEFINITION
# ---------------------------------------------------------------------------


class TestDefinition:
    def test_has_correct_name(self):
        assert DEFINITION["name"] == "batch_research_epc"

    def test_has_required_project_ids(self):
        assert "project_ids" in DEFINITION["input_schema"]["properties"]
        assert "project_ids" in DEFINITION["input_schema"]["required"]

    def test_has_optional_concurrency(self):
        assert "concurrency" in DEFINITION["input_schema"]["properties"]
        assert "concurrency" not in DEFINITION["input_schema"]["required"]


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------


class TestExecute:
    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_valid_projects_returns_correct_shape(self, mock_get_project, mock_run_batch):
        """execute() with valid project IDs returns results/total/completed/errors."""
        mock_get_project.side_effect = lambda pid: _fake_project(pid)
        mock_run_batch.return_value = [
            {"project_id": "p1", "status": "completed", "discovery": _fake_discovery("p1")},
            {"project_id": "p2", "status": "completed", "discovery": _fake_discovery("p2")},
        ]

        result = await execute({"project_ids": ["p1", "p2"]})

        assert "results" in result
        assert result["total"] == 2
        assert result["completed"] == 2
        assert result["errors"] == 0
        assert len(result["results"]) == 2

    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_no_valid_projects_returns_error(self, mock_get_project, mock_run_batch):
        """execute() with no valid project IDs returns error dict."""
        mock_get_project.return_value = None

        result = await execute({"project_ids": ["bad-1", "bad-2"]})

        assert "error" in result
        assert result["total"] == 0
        assert result["completed"] == 0
        assert result["errors"] == 0
        mock_run_batch.assert_not_called()

    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_concurrency_capped_at_10(self, mock_get_project, mock_run_batch):
        """execute() caps concurrency at 10 even if higher is requested."""
        mock_get_project.side_effect = lambda pid: _fake_project(pid)
        mock_run_batch.return_value = [
            {"project_id": "p1", "status": "completed", "discovery": _fake_discovery("p1")},
        ]

        await execute({"project_ids": ["p1"], "concurrency": 50})

        _, kwargs = mock_run_batch.call_args
        assert kwargs["concurrency"] == 10

    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_default_concurrency_is_5(self, mock_get_project, mock_run_batch):
        """execute() defaults concurrency to 5."""
        mock_get_project.side_effect = lambda pid: _fake_project(pid)
        mock_run_batch.return_value = []

        await execute({"project_ids": ["p1"]})

        _, kwargs = mock_run_batch.call_args
        assert kwargs["concurrency"] == 5

    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_progress_callback_receives_updates(self, mock_get_project, mock_run_batch):
        """Progress callback injected via _progress_callback receives updates."""
        mock_get_project.side_effect = lambda pid: _fake_project(pid)

        progress_events = []

        async def capture_progress(update):
            progress_events.append(update)

        async def fake_run_batch(projects, on_progress, concurrency=5):
            await on_progress({"project_id": "p1", "status": "started", "project_name": "Solar"})
            await on_progress(
                {"project_id": "p1", "status": "completed", "discovery": _fake_discovery("p1")}
            )
            return [{"project_id": "p1", "status": "completed", "discovery": _fake_discovery("p1")}]

        mock_run_batch.side_effect = fake_run_batch

        await execute(
            {
                "project_ids": ["p1"],
                "_progress_callback": capture_progress,
            }
        )

        assert len(progress_events) == 2
        assert progress_events[0]["status"] == "started"
        assert progress_events[1]["status"] == "completed"

    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_enriches_results_with_project_names(self, mock_get_project, mock_run_batch):
        """Results get project_name from the fetched project records."""
        mock_get_project.side_effect = lambda pid: _fake_project(pid, name=f"Project {pid}")
        mock_run_batch.return_value = [
            {"project_id": "p1", "status": "completed", "discovery": _fake_discovery("p1")},
        ]

        result = await execute({"project_ids": ["p1"]})

        assert result["results"][0]["project_name"] == "Project p1"

    @patch("src.batch.run_batch", new_callable=AsyncMock)
    @patch("src.db.get_project")
    async def test_mixed_results_counted_correctly(self, mock_get_project, mock_run_batch):
        """Completed and error counts are tallied correctly."""
        mock_get_project.side_effect = lambda pid: _fake_project(pid)
        mock_run_batch.return_value = [
            {"project_id": "p1", "status": "completed", "discovery": _fake_discovery("p1")},
            {"project_id": "p2", "status": "error", "error": "boom"},
            {"project_id": "p3", "status": "skipped", "reason": "already_accepted"},
        ]

        result = await execute({"project_ids": ["p1", "p2", "p3"]})

        assert result["total"] == 3
        assert result["completed"] == 1
        assert result["errors"] == 1


# ---------------------------------------------------------------------------
# _format_batch_progress
# ---------------------------------------------------------------------------


class TestFormatBatchProgress:
    def test_started(self):
        line = _format_batch_progress({"status": "started", "project_name": "Solar A"})
        assert "Researching Solar A" in line

    def test_completed(self):
        line = _format_batch_progress(
            {
                "status": "completed",
                "project_name": "Solar B",
                "discovery": {"epc_contractor": "McCarthy", "confidence": "likely"},
            }
        )
        assert "Solar B" in line
        assert "McCarthy" in line
        assert "likely" in line

    def test_skipped(self):
        line = _format_batch_progress({"status": "skipped", "project_name": "Solar C"})
        assert "skipped" in line
        assert "Solar C" in line

    def test_error(self):
        line = _format_batch_progress({"status": "error", "project_name": "Solar D"})
        assert "error" in line
        assert "Solar D" in line

    def test_unknown_status_returns_none(self):
        assert _format_batch_progress({"status": "unknown_thing"}) is None

    def test_falls_back_to_project_id(self):
        line = _format_batch_progress({"status": "started", "project_id": "proj-123"})
        assert "proj-123" in line
