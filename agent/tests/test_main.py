"""Tests for FastAPI endpoints in main.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models import AgentResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_project():
    return {
        "id": "proj-001",
        "queue_id": "Q-100",
        "project_name": "Sunrise Solar",
        "developer": "SunDev LLC",
        "state": "TX",
    }


@pytest.fixture()
def sample_discovery():
    return {
        "id": "disc-001",
        "project_id": "proj-001",
        "epc_contractor": "McCarthy Building",
        "confidence": "likely",
        "sources": [],
        "reasoning": "Found evidence.",
        "related_leads": [],
        "review_status": "pending",
        "agent_log": [],
        "tokens_used": 3000,
        "created_at": "2025-03-01T00:00:00Z",
        "updated_at": "2025-03-01T00:00:00Z",
    }


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /api/discover
# ---------------------------------------------------------------------------


class TestDiscover:
    @patch("src.main.db.store_discovery")
    @patch("src.main.run_research", new_callable=AsyncMock)
    @patch("src.main.build_knowledge_context")
    @patch("src.main.db.get_active_discovery")
    @patch("src.main.db.get_project")
    async def test_success(
        self,
        mock_get_proj,
        mock_get_active,
        mock_kb,
        mock_research,
        mock_store,
        client,
        sample_project,
        sample_discovery,
    ):
        mock_get_proj.return_value = sample_project
        mock_get_active.return_value = None
        mock_kb.return_value = None
        mock_research.return_value = (
            AgentResult(epc_contractor="McCarthy", confidence="likely", reasoning="ok"),
            [{"iteration": 0}],
            3000,
        )
        mock_store.return_value = sample_discovery

        resp = await client.post("/api/discover", json={"project_id": "proj-001"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["epc_contractor"] == "McCarthy Building"
        mock_store.assert_called_once()

    @patch("src.main.db.get_project")
    async def test_404_missing_project(self, mock_get_proj, client):
        mock_get_proj.return_value = None
        resp = await client.post("/api/discover", json={"project_id": "nonexistent"})
        assert resp.status_code == 404

    @patch("src.main.db.get_active_discovery")
    @patch("src.main.db.get_project")
    async def test_409_already_accepted(
        self, mock_get_proj, mock_get_active, client, sample_project
    ):
        mock_get_proj.return_value = sample_project
        mock_get_active.return_value = {"id": "disc-old", "review_status": "accepted"}

        resp = await client.post("/api/discover", json={"project_id": "proj-001"})
        assert resp.status_code == 409

    @patch("src.main.run_research", new_callable=AsyncMock)
    @patch("src.main.build_knowledge_context")
    @patch("src.main.db.get_active_discovery")
    @patch("src.main.db.get_project")
    async def test_500_agent_error(
        self, mock_get_proj, mock_get_active, mock_kb, mock_research, client, sample_project
    ):
        mock_get_proj.return_value = sample_project
        mock_get_active.return_value = None
        mock_kb.return_value = None
        mock_research.side_effect = RuntimeError("Agent crashed")

        resp = await client.post("/api/discover", json={"project_id": "proj-001"})
        assert resp.status_code == 500
        assert "Agent error" in resp.json()["detail"]

    async def test_422_missing_body(self, client):
        resp = await client.post("/api/discover", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/discover/batch — SSE streaming
# ---------------------------------------------------------------------------


class TestDiscoverBatch:
    async def test_400_empty_ids(self, client):
        resp = await client.post("/api/discover/batch", json={"project_ids": []})
        assert resp.status_code == 400

    @patch("src.main.db.get_project")
    async def test_404_no_valid_projects(self, mock_get_proj, client):
        mock_get_proj.return_value = None
        resp = await client.post("/api/discover/batch", json={"project_ids": ["bad-1", "bad-2"]})
        assert resp.status_code == 404

    @patch("src.main.run_batch")
    @patch("src.main.db.get_project")
    async def test_streams_sse_events(
        self, mock_get_proj, mock_run_batch, client, sample_project, sample_discovery
    ):
        mock_get_proj.return_value = sample_project

        async def fake_batch(projects, on_progress, **kwargs):
            await on_progress(
                {"project_id": "proj-001", "status": "started", "project_name": "Sunrise Solar"}
            )
            await on_progress(
                {"project_id": "proj-001", "status": "completed", "discovery": sample_discovery}
            )
            return [{"project_id": "proj-001", "status": "completed"}]

        mock_run_batch.side_effect = fake_batch

        resp = await client.post("/api/discover/batch", json={"project_ids": ["proj-001"]})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"

        # Parse SSE events from response body
        lines = resp.text.strip().split("\n")
        events = []
        for line in lines:
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        # Expect: started, completed, done
        assert len(events) == 3
        assert events[0]["type"] == "started"
        assert events[0]["project_name"] == "Sunrise Solar"
        assert events[1]["type"] == "completed"
        assert events[1]["completed"] == 1
        assert events[1]["discovery"]["id"] == "disc-001"
        assert events[2]["type"] == "done"
        assert events[2]["completed"] == 1

    @patch("src.main.run_batch")
    @patch("src.main.db.get_project")
    async def test_sse_skipped_event(self, mock_get_proj, mock_run_batch, client, sample_project):
        mock_get_proj.return_value = sample_project

        async def fake_batch(projects, on_progress, **kwargs):
            await on_progress(
                {"project_id": "proj-001", "status": "skipped", "reason": "already_accepted"}
            )
            return [{"project_id": "proj-001", "status": "skipped"}]

        mock_run_batch.side_effect = fake_batch

        resp = await client.post("/api/discover/batch", json={"project_ids": ["proj-001"]})

        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert events[0]["type"] == "skipped"
        assert events[0]["reason"] == "already_accepted"
        assert events[0]["completed"] == 1

    @patch("src.main.run_batch")
    @patch("src.main.db.get_project")
    async def test_sse_error_event(self, mock_get_proj, mock_run_batch, client, sample_project):
        mock_get_proj.return_value = sample_project

        async def fake_batch(projects, on_progress, **kwargs):
            await on_progress({"project_id": "proj-001", "status": "error", "error": "Tavily down"})
            return [{"project_id": "proj-001", "status": "error"}]

        mock_run_batch.side_effect = fake_batch

        resp = await client.post("/api/discover/batch", json={"project_ids": ["proj-001"]})

        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert events[0]["type"] == "error"
        assert "Tavily down" in events[0]["error"]
        assert events[0]["completed"] == 1

    @patch("src.main.run_batch")
    @patch("src.main.db.get_project")
    async def test_sse_multiple_projects_progress_counter(
        self, mock_get_proj, mock_run_batch, client
    ):
        """Verify completed counter increments correctly across multiple projects."""
        projects_db = {
            "proj-a": {"id": "proj-a", "queue_id": "QA", "project_name": "Alpha"},
            "proj-b": {"id": "proj-b", "queue_id": "QB", "project_name": "Beta"},
            "proj-c": {"id": "proj-c", "queue_id": "QC", "project_name": "Charlie"},
        }
        mock_get_proj.side_effect = lambda pid: projects_db.get(pid)

        async def fake_batch(projects, on_progress, **kwargs):
            for p in projects:
                await on_progress(
                    {"project_id": p["id"], "status": "started", "project_name": p["project_name"]}
                )
                await on_progress(
                    {
                        "project_id": p["id"],
                        "status": "completed",
                        "discovery": {"id": f"disc-{p['id']}", "epc_contractor": "X"},
                    }
                )
            return []

        mock_run_batch.side_effect = fake_batch

        resp = await client.post(
            "/api/discover/batch", json={"project_ids": ["proj-a", "proj-b", "proj-c"]}
        )

        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        completed_events = [e for e in events if e["type"] == "completed"]
        assert len(completed_events) == 3
        assert completed_events[0]["completed"] == 1
        assert completed_events[1]["completed"] == 2
        assert completed_events[2]["completed"] == 3

        done_event = [e for e in events if e["type"] == "done"][0]
        assert done_event["completed"] == 3
        assert done_event["total"] == 3

    async def test_422_missing_body(self, client):
        resp = await client.post("/api/discover/batch", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/discover/{id}/review
# ---------------------------------------------------------------------------


class TestReviewDiscovery:
    @patch("src.main.db.update_project_epc")
    @patch("src.main.db.update_discovery")
    @patch("src.main.db.get_client")
    async def test_accept(
        self, mock_client_fn, mock_update, mock_update_epc, client, sample_discovery
    ):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.execute.return_value = MagicMock(data=[sample_discovery])

        accepted_discovery = {**sample_discovery, "review_status": "accepted"}
        mock_update.return_value = accepted_discovery

        resp = await client.patch("/api/discover/disc-001/review", json={"action": "accepted"})

        assert resp.status_code == 200
        mock_update.assert_called_once_with("disc-001", {"review_status": "accepted"})
        mock_update_epc.assert_called_once_with("proj-001", "McCarthy Building")

    @patch("src.main.db.update_project_epc")
    @patch("src.main.db.update_discovery")
    @patch("src.main.db.get_client")
    async def test_reject(
        self, mock_client_fn, mock_update, mock_update_epc, client, sample_discovery
    ):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.execute.return_value = MagicMock(data=[sample_discovery])

        mock_update.return_value = {**sample_discovery, "review_status": "rejected"}

        resp = await client.patch("/api/discover/disc-001/review", json={"action": "rejected"})

        assert resp.status_code == 200
        mock_update_epc.assert_not_called()

    @patch("src.main.db.get_client")
    async def test_404_missing(self, mock_client_fn, client):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.execute.return_value = MagicMock(data=[])

        resp = await client.patch("/api/discover/nonexistent/review", json={"action": "accepted"})
        assert resp.status_code == 404

    async def test_400_invalid_action(self, client):
        # FastAPI will route this — we need to mock DB to get past lookup
        with patch("src.main.db.get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            chain = mock_client.table.return_value.select.return_value.eq.return_value
            chain.execute.return_value = MagicMock(
                data=[{"id": "disc-001", "review_status": "pending"}]
            )

            resp = await client.patch("/api/discover/disc-001/review", json={"action": "invalid"})
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/discoveries
# ---------------------------------------------------------------------------


class TestListDiscoveries:
    @patch("src.main.db.list_discoveries")
    async def test_returns_list(self, mock_list, client, sample_discovery):
        mock_list.return_value = [sample_discovery]

        resp = await client.get("/api/discoveries")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "disc-001"

    @patch("src.main.db.list_discoveries")
    async def test_returns_empty(self, mock_list, client):
        mock_list.return_value = []

        resp = await client.get("/api/discoveries")
        assert resp.status_code == 200
        assert resp.json() == []
