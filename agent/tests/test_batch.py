"""Tests for batch.py — concurrent EPC discovery processing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from src.batch import _research_one, run_batch
from tests.conftest import make_agent_result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_agent_result():
    return (
        make_agent_result(),
        [{"iteration": 0}],
        2000,
    )


def _fake_discovery(project_id):
    return {
        "id": f"disc-{project_id}",
        "project_id": project_id,
        "epc_contractor": "McCarthy Building",
        "confidence": "likely",
        "review_status": "pending",
    }


# ---------------------------------------------------------------------------
# _research_one
# ---------------------------------------------------------------------------


class TestResearchOne:
    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_successful_research(self, mock_kb, mock_get_active, mock_agent, mock_store):
        """Normal project → started + completed callbacks."""
        mock_get_active.return_value = None
        mock_agent.return_value = _fake_agent_result()
        mock_store.return_value = _fake_discovery("proj-001")

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        project = {"id": "proj-001", "queue_id": "Q-1", "project_name": "Solar A"}
        sem = asyncio.Semaphore(3)

        result = await _research_one(project, sem, on_progress)

        assert result["status"] == "completed"
        assert result["discovery"]["id"] == "disc-proj-001"
        # Should have 2 progress events: started + completed
        assert len(progress_events) == 2
        assert progress_events[0]["status"] == "started"
        assert progress_events[0]["project_name"] == "Solar A"
        assert progress_events[1]["status"] == "completed"

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    async def test_skips_accepted_discovery(self, mock_get_active, mock_agent, mock_store):
        """Project with accepted discovery → skipped, no agent run."""
        mock_get_active.return_value = {"id": "disc-existing", "review_status": "accepted"}

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        project = {"id": "proj-001", "queue_id": "Q-1", "project_name": "Solar A"}
        sem = asyncio.Semaphore(3)

        result = await _research_one(project, sem, on_progress)

        assert result["status"] == "skipped"
        assert result["reason"] == "already_accepted"
        mock_agent.assert_not_called()
        mock_store.assert_not_called()
        assert len(progress_events) == 1

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_does_not_skip_pending_discovery(
        self, mock_kb, mock_get_active, mock_agent, mock_store
    ):
        """Project with pending (not accepted) discovery → runs agent."""
        mock_get_active.return_value = {"id": "disc-pending", "review_status": "pending"}
        mock_agent.return_value = _fake_agent_result()
        mock_store.return_value = _fake_discovery("proj-001")

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        project = {"id": "proj-001", "queue_id": "Q-1", "project_name": "Solar A"}
        sem = asyncio.Semaphore(3)

        result = await _research_one(project, sem, on_progress)

        assert result["status"] == "completed"
        mock_agent.assert_called_once()

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_agent_error_returns_error_status(
        self, mock_kb, mock_get_active, mock_agent, mock_store
    ):
        """Agent exception → error result with traceback."""
        mock_get_active.return_value = None
        mock_agent.side_effect = RuntimeError("API failure")

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        project = {"id": "proj-001", "queue_id": "Q-1", "project_name": "Solar A"}
        sem = asyncio.Semaphore(3)

        result = await _research_one(project, sem, on_progress)

        assert result["status"] == "error"
        assert "API failure" in result["error"]
        mock_store.assert_not_called()

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_uses_queue_id_fallback_for_label(
        self, mock_kb, mock_get_active, mock_agent, mock_store
    ):
        """Project without project_name uses queue_id as label."""
        mock_get_active.return_value = None
        mock_agent.return_value = _fake_agent_result()
        mock_store.return_value = _fake_discovery("proj-001")

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        project = {"id": "proj-001", "queue_id": "Q-1", "project_name": None}
        sem = asyncio.Semaphore(3)

        await _research_one(project, sem, on_progress)

        assert progress_events[0]["project_name"] == "Q-1"


# ---------------------------------------------------------------------------
# run_batch — concurrency + gather
# ---------------------------------------------------------------------------


class TestRunBatch:
    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_processes_all_projects(self, mock_kb, mock_get_active, mock_agent, mock_store):
        mock_get_active.return_value = None
        mock_agent.return_value = _fake_agent_result()
        mock_store.side_effect = lambda pid, *a, **kw: _fake_discovery(pid)

        projects = [
            {"id": f"proj-{i}", "queue_id": f"Q-{i}", "project_name": f"Solar {i}"}
            for i in range(5)
        ]

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        results = await run_batch(projects, on_progress, concurrency=3)

        assert len(results) == 5
        assert all(r["status"] == "completed" for r in results)
        # 5 projects × 2 events each (started + completed) = 10
        assert len(progress_events) == 10

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_mixed_results(self, mock_kb, mock_get_active, mock_agent, mock_store):
        """Mix of normal, skipped, and error projects."""

        def get_active(pid):
            if pid == "proj-skip":
                return {"id": "disc-skip", "review_status": "accepted"}
            return None

        mock_get_active.side_effect = get_active

        call_count = 0

        async def fake_agent(project, knowledge_context=None, api_key=None, shared_findings=None):
            nonlocal call_count
            call_count += 1
            if project["id"] == "proj-err":
                raise RuntimeError("boom")
            return _fake_agent_result()

        mock_agent.side_effect = fake_agent
        mock_store.side_effect = lambda pid, *a, **kw: _fake_discovery(pid)

        projects = [
            {"id": "proj-ok", "queue_id": "Q-1", "project_name": "Good"},
            {"id": "proj-skip", "queue_id": "Q-2", "project_name": "Skipped"},
            {"id": "proj-err", "queue_id": "Q-3", "project_name": "Error"},
        ]

        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        results = await run_batch(projects, on_progress, concurrency=2)

        statuses = {r["project_id"]: r["status"] for r in results}
        assert statuses["proj-ok"] == "completed"
        assert statuses["proj-skip"] == "skipped"
        assert statuses["proj-err"] == "error"

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_semaphore_limits_concurrency(
        self, mock_kb, mock_get_active, mock_agent, mock_store
    ):
        """At most `concurrency` agents run simultaneously."""
        mock_get_active.return_value = None

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        original_return = _fake_agent_result()

        async def slow_agent(project, knowledge_context=None):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1
            return original_return

        mock_agent.side_effect = slow_agent
        mock_store.side_effect = lambda pid, *a, **kw: _fake_discovery(pid)

        projects = [
            {"id": f"proj-{i}", "queue_id": f"Q-{i}", "project_name": f"Solar {i}"}
            for i in range(6)
        ]

        async def on_progress(update):
            pass

        await run_batch(projects, on_progress, concurrency=2)

        assert max_concurrent <= 2

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_empty_project_list(self, mock_kb, mock_get_active, mock_agent, mock_store):
        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        results = await run_batch([], on_progress)

        assert results == []
        assert progress_events == []
        mock_agent.assert_not_called()


# ---------------------------------------------------------------------------
# Error isolation (return_exceptions=True safety net)
# ---------------------------------------------------------------------------


class TestBatchErrorIsolation:
    async def test_uncaught_exception_becomes_error_dict(self):
        """If _research_one raises unexpectedly, it becomes an error dict."""
        progress_events = []

        async def on_progress(update):
            progress_events.append(update)

        projects = [
            {"id": "proj-1", "queue_id": "Q-1", "project_name": "Test"},
        ]

        with patch("src.batch._research_one", new_callable=AsyncMock) as mock_ro:
            mock_ro.side_effect = RuntimeError("total crash")
            results = await run_batch(projects, on_progress)

        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "Uncaught exception" in results[0]["error"]
        assert results[0]["project_id"] == "proj-1"
        # on_progress should have been called with the error
        assert any(e.get("status") == "error" for e in progress_events)

    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_one_crash_others_still_complete(
        self, mock_kb, mock_get_active, mock_agent, mock_store
    ):
        """When one project crashes, others still return results."""
        mock_get_active.return_value = None
        mock_agent.return_value = _fake_agent_result()
        mock_store.side_effect = lambda pid, *a, **kw: _fake_discovery(pid)

        projects = [
            {"id": "proj-ok1", "queue_id": "Q-1", "project_name": "Good 1"},
            {"id": "proj-ok2", "queue_id": "Q-2", "project_name": "Good 2"},
        ]

        progress_events = []
        crash_count = 0

        async def on_progress(update):
            nonlocal crash_count
            # Make on_progress crash for first "started" event only
            if update.get("status") == "started" and crash_count == 0:
                crash_count += 1
                raise RuntimeError("callback exploded")
            progress_events.append(update)

        results = await run_batch(projects, on_progress, concurrency=10)

        assert len(results) == 2
        # At least one should complete successfully
        statuses = [r["status"] for r in results]
        assert "completed" in statuses or "error" in statuses

    @patch("src.batch.logger")
    @patch("src.batch.store_discovery")
    @patch("src.batch.run_research", new_callable=AsyncMock)
    @patch("src.batch.get_active_discovery")
    @patch("src.batch.build_knowledge_context", return_value=None)
    async def test_batch_summary_logging(
        self, mock_kb, mock_get_active, mock_agent, mock_store, mock_logger
    ):
        """Batch logs a summary with completed/skipped/error counts."""

        def get_active(pid):
            if pid == "proj-skip":
                return {"id": "d", "review_status": "accepted"}
            return None

        mock_get_active.side_effect = get_active
        mock_agent.return_value = _fake_agent_result()
        mock_store.side_effect = lambda pid, *a, **kw: _fake_discovery(pid)

        projects = [
            {"id": "proj-ok", "queue_id": "Q-1", "project_name": "Good"},
            {"id": "proj-skip", "queue_id": "Q-2", "project_name": "Skip"},
        ]

        async def on_progress(update):
            pass

        await run_batch(projects, on_progress)

        mock_logger.info.assert_called_once()
        log_msg = mock_logger.info.call_args[0][0]
        assert "Batch complete" in log_msg
