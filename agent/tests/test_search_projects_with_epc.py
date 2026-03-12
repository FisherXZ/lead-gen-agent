"""Tests for search_projects_with_epc — DB function and tool."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from src.db import search_projects_with_epc, _normalize_project_first, _normalize_epc_first


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_project_row(*, project_id="proj-001", discovery=None):
    """Build a project row as returned by PostgREST with latest_discovery join."""
    row = {
        "id": project_id,
        "project_name": "Sunrise Solar",
        "developer": "SunDev LLC",
        "mw_capacity": 250,
        "state": "TX",
        "expected_cod": "2026-12-01",
        "fuel_type": "Solar",
        "epc_company": None,
        "latest_discovery": discovery or [],
    }
    return row


def _make_disc_row(*, epc="McCarthy Building", confidence="likely", status="pending"):
    """Build a discovery row as returned by PostgREST with project join."""
    return {
        "id": "disc-001",
        "epc_contractor": epc,
        "confidence": confidence,
        "review_status": status,
        "source_count": 2,
        "created_at": "2026-03-10T00:00:00Z",
        "project": {
            "id": "proj-001",
            "project_name": "Sunrise Solar",
            "developer": "SunDev LLC",
            "mw_capacity": 250,
            "state": "TX",
            "expected_cod": "2026-12-01",
            "fuel_type": "Solar",
            "epc_company": None,
        },
    }


def _mock_execute(data):
    """Return a mock Supabase response with .data attribute."""
    resp = MagicMock()
    resp.data = data
    return resp


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_project_first_with_discovery(self):
        row = _make_project_row(discovery=[{
            "id": "disc-001",
            "epc_contractor": "McCarthy Building",
            "confidence": "likely",
            "review_status": "pending",
            "source_count": 2,
            "created_at": "2026-03-10",
        }])
        results = _normalize_project_first([row])
        assert len(results) == 1
        r = results[0]
        assert r["project_id"] == "proj-001"
        assert r["epc_contractor"] == "McCarthy Building"
        assert r["confidence"] == "likely"
        assert r["review_status"] == "pending"
        assert r["source_count"] == 2
        assert r["discovery_date"] == "2026-03-10"

    def test_project_first_without_discovery(self):
        row = _make_project_row(discovery=[])
        results = _normalize_project_first([row])
        r = results[0]
        assert r["project_id"] == "proj-001"
        assert r["epc_contractor"] is None
        assert r["confidence"] is None
        assert r["review_status"] is None

    def test_epc_first_normalization(self):
        row = _make_disc_row()
        results = _normalize_epc_first([row])
        assert len(results) == 1
        r = results[0]
        assert r["project_id"] == "proj-001"
        assert r["project_name"] == "Sunrise Solar"
        assert r["epc_contractor"] == "McCarthy Building"
        assert r["confidence"] == "likely"

    def test_both_modes_same_shape(self):
        proj_row = _make_project_row(discovery=[{
            "id": "disc-001",
            "epc_contractor": "McCarthy Building",
            "confidence": "likely",
            "review_status": "pending",
            "source_count": 2,
            "created_at": "2026-03-10",
        }])
        disc_row = _make_disc_row()
        proj_result = _normalize_project_first([proj_row])[0]
        epc_result = _normalize_epc_first([disc_row])[0]
        assert set(proj_result.keys()) == set(epc_result.keys())


# ---------------------------------------------------------------------------
# Mode 1: Project-first
# ---------------------------------------------------------------------------

class TestProjectFirstMode:
    @patch("src.db.get_client")
    def test_project_first_calls_correct_table(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Build the chained query mock
        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_order = mock_select.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([_make_project_row()])

        results = search_projects_with_epc(limit=10)

        mock_client.table.assert_called_with("projects")
        assert len(results) == 1
        assert results[0]["project_id"] == "proj-001"

    @patch("src.db.get_client")
    def test_project_first_applies_state_filter(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_eq = mock_select.eq.return_value
        mock_order = mock_eq.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([])

        search_projects_with_epc(state="TX")

        mock_select.eq.assert_called_with("state", "TX")

    @patch("src.db.get_client")
    def test_project_first_applies_cod_year_filter(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_gte = mock_select.gte.return_value
        mock_lte = mock_gte.lte.return_value
        mock_order = mock_lte.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([])

        search_projects_with_epc(cod_year=2026)

        mock_select.gte.assert_called_with("expected_cod", "2026-01-01")
        mock_gte.lte.assert_called_with("expected_cod", "2026-12-31")


# ---------------------------------------------------------------------------
# Mode 2: EPC-first
# ---------------------------------------------------------------------------

class TestEpcFirstMode:
    @patch("src.db.get_client")
    def test_epc_first_queries_discoveries_table(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_ilike = mock_select.ilike.return_value
        mock_neq = mock_ilike.neq.return_value
        mock_order = mock_neq.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([_make_disc_row()])

        results = search_projects_with_epc(epc_name="McCarthy")

        mock_client.table.assert_called_with("epc_discoveries")
        mock_select.ilike.assert_called_with("epc_contractor", "%McCarthy%")
        mock_ilike.neq.assert_called_with("review_status", "rejected")
        assert len(results) == 1
        assert results[0]["epc_contractor"] == "McCarthy Building"

    @patch("src.db.get_client")
    def test_epc_first_post_filters_state(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Two discoveries: one TX, one CA
        disc_tx = _make_disc_row()
        disc_ca = _make_disc_row()
        disc_ca["project"]["state"] = "CA"

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_ilike = mock_select.ilike.return_value
        mock_neq = mock_ilike.neq.return_value
        mock_order = mock_neq.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([disc_tx, disc_ca])

        results = search_projects_with_epc(epc_name="McCarthy", state="TX")

        assert len(results) == 1
        assert results[0]["state"] == "TX"


# ---------------------------------------------------------------------------
# Post-query filters
# ---------------------------------------------------------------------------

class TestPostQueryFilters:
    @patch("src.db.get_client")
    def test_confidence_min_filters_below_threshold(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        disc_confirmed = {
            "id": "disc-001", "epc_contractor": "A", "confidence": "confirmed",
            "review_status": "accepted", "source_count": 3, "created_at": "2026-03-10",
        }
        disc_possible = {
            "id": "disc-002", "epc_contractor": "B", "confidence": "possible",
            "review_status": "pending", "source_count": 1, "created_at": "2026-03-09",
        }
        row1 = _make_project_row(project_id="proj-001", discovery=[disc_confirmed])
        row2 = _make_project_row(project_id="proj-002", discovery=[disc_possible])

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_order = mock_select.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([row1, row2])

        results = search_projects_with_epc(confidence_min="likely")

        # Only confirmed should pass (confirmed <= likely rank)
        assert len(results) == 1
        assert results[0]["confidence"] == "confirmed"

    @patch("src.db.get_client")
    def test_include_pending_false_excludes_pending(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        disc_pending = {
            "id": "disc-001", "epc_contractor": "A", "confidence": "likely",
            "review_status": "pending", "source_count": 2, "created_at": "2026-03-10",
        }
        disc_accepted = {
            "id": "disc-002", "epc_contractor": "B", "confidence": "confirmed",
            "review_status": "accepted", "source_count": 3, "created_at": "2026-03-09",
        }
        row1 = _make_project_row(project_id="proj-001", discovery=[disc_pending])
        row2 = _make_project_row(project_id="proj-002", discovery=[disc_accepted])

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_order = mock_select.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([row1, row2])

        results = search_projects_with_epc(include_pending=False)

        assert len(results) == 1
        assert results[0]["review_status"] == "accepted"

    @patch("src.db.get_client")
    def test_limit_enforcement(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Create 5 rows but request limit=2
        rows = [_make_project_row(project_id=f"proj-{i}") for i in range(5)]

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_order = mock_select.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute(rows)

        results = search_projects_with_epc(limit=2)

        # DB limit is applied via PostgREST, but final slice also enforces
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# Tool execute
# ---------------------------------------------------------------------------

class TestToolExecute:
    @patch("src.db.search_projects_with_epc")
    @pytest.mark.asyncio
    async def test_tool_returns_correct_shape(self, mock_search):
        from src.tools.search_projects_with_epc import execute

        mock_search.return_value = [
            {"project_id": "proj-001", "epc_contractor": "McCarthy Building", "confidence": "likely"}
        ]

        result = await execute({"state": "TX"})

        assert result["count"] == 1
        assert result["query_mode"] == "project_search"
        assert len(result["results"]) == 1

    @patch("src.db.search_projects_with_epc")
    @pytest.mark.asyncio
    async def test_tool_epc_mode(self, mock_search):
        from src.tools.search_projects_with_epc import execute

        mock_search.return_value = []

        result = await execute({"epc_name": "McCarthy"})

        assert result["query_mode"] == "epc_search"
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["epc_name"] == "McCarthy"

    @patch("src.db.search_projects_with_epc")
    @pytest.mark.asyncio
    async def test_tool_caps_limit_at_100(self, mock_search):
        from src.tools.search_projects_with_epc import execute

        mock_search.return_value = []

        await execute({"limit": 500})

        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["limit"] == 100


# ---------------------------------------------------------------------------
# Fix regression tests
# ---------------------------------------------------------------------------

class TestConfidenceMinPreservesUnresearched:
    """FIX 1: confidence_min should keep projects with no discovery (confidence=None)."""

    @patch("src.db.get_client")
    def test_confidence_min_keeps_no_discovery_projects(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        disc_confirmed = {
            "id": "disc-001", "epc_contractor": "A", "confidence": "confirmed",
            "review_status": "accepted", "source_count": 3, "created_at": "2026-03-10",
        }
        row_with_disc = _make_project_row(project_id="proj-001", discovery=[disc_confirmed])
        row_no_disc = _make_project_row(project_id="proj-002", discovery=[])
        row_possible = _make_project_row(project_id="proj-003", discovery=[{
            "id": "disc-003", "epc_contractor": "C", "confidence": "possible",
            "review_status": "pending", "source_count": 1, "created_at": "2026-03-08",
        }])

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_order = mock_select.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([row_with_disc, row_no_disc, row_possible])

        results = search_projects_with_epc(confidence_min="likely")

        ids = [r["project_id"] for r in results]
        # confirmed passes, no-discovery preserved, possible dropped
        assert "proj-001" in ids
        assert "proj-002" in ids
        assert "proj-003" not in ids


class TestRejectedDiscoveriesFiltered:
    """FIX 2: _normalize_project_first filters rejected and sorts by date."""

    def test_rejected_discoveries_excluded(self):
        row = _make_project_row(discovery=[
            {
                "id": "disc-old", "epc_contractor": "BadCo", "confidence": "possible",
                "review_status": "rejected", "source_count": 1, "created_at": "2026-03-01",
            },
            {
                "id": "disc-new", "epc_contractor": "GoodCo", "confidence": "likely",
                "review_status": "pending", "source_count": 2, "created_at": "2026-03-10",
            },
        ])
        results = _normalize_project_first([row])
        assert results[0]["epc_contractor"] == "GoodCo"

    def test_all_rejected_yields_empty_discovery(self):
        row = _make_project_row(discovery=[
            {
                "id": "disc-rej", "epc_contractor": "BadCo", "confidence": "possible",
                "review_status": "rejected", "source_count": 1, "created_at": "2026-03-01",
            },
        ])
        results = _normalize_project_first([row])
        assert results[0]["epc_contractor"] is None
        assert results[0]["confidence"] is None

    def test_sorts_by_created_at_desc(self):
        row = _make_project_row(discovery=[
            {
                "id": "disc-older", "epc_contractor": "OldCo", "confidence": "possible",
                "review_status": "pending", "source_count": 1, "created_at": "2026-03-01",
            },
            {
                "id": "disc-newer", "epc_contractor": "NewCo", "confidence": "likely",
                "review_status": "pending", "source_count": 2, "created_at": "2026-03-10",
            },
        ])
        results = _normalize_project_first([row])
        assert results[0]["epc_contractor"] == "NewCo"


class TestCodYearEpcFirstMode:
    """FIX 3: cod_year should filter results in EPC-first mode."""

    @patch("src.db.get_client")
    def test_cod_year_filters_epc_first(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        disc_2026 = _make_disc_row()
        disc_2026["project"]["expected_cod"] = "2026-12-01"

        disc_2027 = _make_disc_row()
        disc_2027["project"]["expected_cod"] = "2027-06-01"
        disc_2027["project"]["id"] = "proj-002"

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_ilike = mock_select.ilike.return_value
        mock_neq = mock_ilike.neq.return_value
        mock_order = mock_neq.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.return_value = _mock_execute([disc_2026, disc_2027])

        results = search_projects_with_epc(epc_name="McCarthy", cod_year=2026)

        assert len(results) == 1
        assert results[0]["expected_cod"].startswith("2026")


class TestErrorHandling:
    """FIX 5: PostgREST execute() failures return empty list."""

    @patch("src.db.get_client")
    def test_project_first_returns_empty_on_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_order = mock_select.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.side_effect = Exception("PostgREST timeout")

        results = search_projects_with_epc()

        assert results == []

    @patch("src.db.get_client")
    def test_epc_first_returns_empty_on_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_table = mock_client.table.return_value
        mock_select = mock_table.select.return_value
        mock_ilike = mock_select.ilike.return_value
        mock_neq = mock_ilike.neq.return_value
        mock_order = mock_neq.order.return_value
        mock_limit = mock_order.limit.return_value
        mock_limit.execute.side_effect = Exception("PostgREST timeout")

        results = search_projects_with_epc(epc_name="McCarthy")

        assert results == []
