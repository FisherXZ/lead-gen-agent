"""Tests for db.py — store_discovery and reject_pending_discovery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src import db
from src.models import AgentResult, EpcSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_supabase_response(data):
    """Build a mock Supabase response with .data attribute."""
    resp = MagicMock()
    resp.data = data
    return resp


# ---------------------------------------------------------------------------
# reject_pending_discovery
# ---------------------------------------------------------------------------


class TestRejectPendingDiscovery:
    @patch.object(db, "update_discovery")
    @patch.object(db, "get_active_discovery")
    def test_rejects_pending(self, mock_get, mock_update):
        mock_get.return_value = {"id": "disc-99", "review_status": "pending"}
        db.reject_pending_discovery("proj-001")

        mock_update.assert_called_once_with("disc-99", {"review_status": "rejected"})

    @patch.object(db, "update_discovery")
    @patch.object(db, "get_active_discovery")
    def test_noop_when_accepted(self, mock_get, mock_update):
        mock_get.return_value = {"id": "disc-99", "review_status": "accepted"}
        db.reject_pending_discovery("proj-001")

        mock_update.assert_not_called()

    @patch.object(db, "update_discovery")
    @patch.object(db, "get_active_discovery")
    def test_noop_when_no_discovery(self, mock_get, mock_update):
        mock_get.return_value = None
        db.reject_pending_discovery("proj-001")

        mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# store_discovery
# ---------------------------------------------------------------------------


class TestStoreDiscovery:
    @patch.object(db, "insert_discovery")
    @patch.object(db, "reject_pending_discovery")
    def test_stores_and_returns(self, mock_reject, mock_insert):
        agent_result = AgentResult(
            epc_contractor="Blattner Energy",
            confidence="confirmed",
            sources=[EpcSource(channel="trade_publication", excerpt="Blattner awarded contract")],
            reasoning="Two independent sources confirm.",
            related_leads=[],
            searches_performed=["query 1"],
        )
        agent_log = [{"iteration": 0, "stop_reason": "tool_use"}]
        tokens = 3000

        mock_insert.return_value = {"id": "disc-new", "project_id": "proj-001"}

        result = db.store_discovery("proj-001", agent_result, agent_log, tokens)

        # Rejects pending first
        mock_reject.assert_called_once_with("proj-001")

        # Inserts correct data
        call_data = mock_insert.call_args[0][0]
        assert call_data["project_id"] == "proj-001"
        assert call_data["epc_contractor"] == "Blattner Energy"
        assert call_data["confidence"] == "confirmed"
        assert call_data["review_status"] == "pending"
        assert call_data["tokens_used"] == 3000
        assert len(call_data["sources"]) == 1
        assert call_data["sources"][0]["channel"] == "trade_publication"
        assert call_data["agent_log"] == agent_log

        assert result["id"] == "disc-new"

    @patch.object(db, "insert_discovery")
    @patch.object(db, "reject_pending_discovery")
    def test_unknown_epc_defaults_to_unknown_string(self, mock_reject, mock_insert):
        agent_result = AgentResult(
            epc_contractor=None,
            confidence="unknown",
            reasoning="Nothing found.",
            searches_performed=["dead end"],
        )
        mock_insert.return_value = {"id": "disc-x"}

        db.store_discovery("proj-001", agent_result, [], 1000)

        call_data = mock_insert.call_args[0][0]
        assert call_data["epc_contractor"] == "Unknown"

    @patch.object(db, "insert_discovery")
    @patch.object(db, "reject_pending_discovery")
    def test_empty_sources_list(self, mock_reject, mock_insert):
        agent_result = AgentResult(
            epc_contractor="SomeCo",
            confidence="possible",
            reasoning="Weak signal.",
            searches_performed=["query"],
        )
        mock_insert.return_value = {"id": "disc-y"}

        db.store_discovery("proj-001", agent_result, [], 500)

        call_data = mock_insert.call_args[0][0]
        assert call_data["sources"] == []


# ---------------------------------------------------------------------------
# get_active_discovery
# ---------------------------------------------------------------------------


class TestGetActiveDiscovery:
    @patch.object(db, "get_client")
    def test_returns_first_non_rejected(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        chain = mock_client.table.return_value.select.return_value.eq.return_value.neq.return_value
        chain.execute.return_value = _mock_supabase_response(
            [{"id": "disc-1", "review_status": "pending"}]
        )

        result = db.get_active_discovery("proj-001")
        assert result["id"] == "disc-1"

    @patch.object(db, "get_client")
    def test_returns_none_when_empty(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        chain = mock_client.table.return_value.select.return_value.eq.return_value.neq.return_value
        chain.execute.return_value = _mock_supabase_response([])

        result = db.get_active_discovery("proj-001")
        assert result is None


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------


class TestGetProject:
    @patch.object(db, "get_client")
    def test_returns_project(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.execute.return_value = _mock_supabase_response(
            [{"id": "proj-001", "project_name": "Sunrise"}]
        )

        result = db.get_project("proj-001")
        assert result["project_name"] == "Sunrise"

    @patch.object(db, "get_client")
    def test_returns_none_for_missing(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        chain = mock_client.table.return_value.select.return_value.eq.return_value
        chain.execute.return_value = _mock_supabase_response([])

        assert db.get_project("nonexistent") is None
