"""Tests for knowledge_base module — entity resolution, context building, write-back."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import make_agent_result


# ---------------------------------------------------------------------------
# Helpers to build mock Supabase responses
# ---------------------------------------------------------------------------

def _mock_response(data):
    """Build a mock Supabase response with .data attribute."""
    resp = MagicMock()
    resp.data = data
    return resp


def _make_entity(name="SunDev LLC", entity_type=None, **overrides):
    return {
        "id": overrides.get("id", "ent-001"),
        "name": name,
        "entity_type": entity_type or ["developer"],
        "aliases": [],
        "profile": overrides.get("profile"),
        "profile_rebuilt_at": overrides.get("profile_rebuilt_at"),
        "metadata": {},
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


def _make_engagement(**overrides):
    defaults = {
        "id": "eng-001",
        "developer_entity_id": "ent-001",
        "epc_entity_id": "ent-002",
        "project_id": "proj-001",
        "confidence": "likely",
        "sources": [],
        "state": "TX",
        "epc": {"id": "ent-002", "name": "McCarthy Building"},
        "project": {"project_name": "Sunrise Solar", "mw_capacity": 250, "state": "TX"},
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# resolve_entity
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.get_client")
def test_resolve_entity_found(mock_get_client):
    from src.knowledge_base import resolve_entity

    entity = _make_entity()
    table = MagicMock()
    table.select.return_value.ilike.return_value.limit.return_value.execute.return_value = _mock_response([entity])
    mock_get_client.return_value.table.return_value = table

    result = resolve_entity("SunDev LLC")
    assert result is not None
    assert result["name"] == "SunDev LLC"


@patch("src.knowledge_base.get_client")
def test_resolve_entity_not_found(mock_get_client):
    from src.knowledge_base import resolve_entity

    table = MagicMock()
    table.select.return_value.ilike.return_value.limit.return_value.execute.return_value = _mock_response([])
    mock_get_client.return_value.table.return_value = table

    result = resolve_entity("Nonexistent Corp")
    assert result is None


def test_resolve_entity_empty_name():
    from src.knowledge_base import resolve_entity
    assert resolve_entity("") is None
    assert resolve_entity(None) is None


# ---------------------------------------------------------------------------
# resolve_or_create_entity
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.resolve_entity")
@patch("src.knowledge_base.get_client")
def test_resolve_or_create_existing(mock_get_client, mock_resolve):
    from src.knowledge_base import resolve_or_create_entity

    entity = _make_entity()
    mock_resolve.return_value = entity

    result = resolve_or_create_entity("SunDev LLC", "developer")
    assert result["id"] == "ent-001"
    # Should not insert
    mock_get_client.return_value.table.return_value.insert.assert_not_called()


@patch("src.knowledge_base.resolve_entity")
@patch("src.knowledge_base.get_client")
def test_resolve_or_create_new(mock_get_client, mock_resolve):
    from src.knowledge_base import resolve_or_create_entity

    mock_resolve.return_value = None
    new_entity = _make_entity(id="ent-new")
    table = MagicMock()
    table.insert.return_value.execute.return_value = _mock_response([new_entity])
    mock_get_client.return_value.table.return_value = table

    result = resolve_or_create_entity("NewCorp", "epc")
    assert result["id"] == "ent-new"


@patch("src.knowledge_base.resolve_entity")
@patch("src.knowledge_base.get_client")
def test_resolve_or_create_merges_type(mock_get_client, mock_resolve):
    from src.knowledge_base import resolve_or_create_entity

    # Entity exists as developer, we're adding epc type
    entity = _make_entity(entity_type=["developer"])
    mock_resolve.return_value = entity
    table = MagicMock()
    table.update.return_value.eq.return_value.execute.return_value = _mock_response([entity])
    mock_get_client.return_value.table.return_value = table

    result = resolve_or_create_entity("SunDev LLC", "epc")
    assert "epc" in result["entity_type"]


# ---------------------------------------------------------------------------
# _classify_outcome
# ---------------------------------------------------------------------------

def test_classify_outcome():
    from src.knowledge_base import _classify_outcome

    assert _classify_outcome(make_agent_result(confidence="confirmed")) == "found"
    assert _classify_outcome(make_agent_result(confidence="likely")) == "found"
    assert _classify_outcome(make_agent_result(confidence="possible")) == "inconclusive"
    assert _classify_outcome(make_agent_result(confidence="unknown")) == "not_found"


# ---------------------------------------------------------------------------
# build_knowledge_context
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.get_developer_engagements")
@patch("src.knowledge_base.rebuild_profile_if_stale")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_with_data(mock_resolve, mock_rebuild, mock_engs, mock_attempts, mock_epcs):
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = _make_entity()
    mock_rebuild.return_value = "Developer profile text"
    mock_engs.return_value = [_make_engagement()]
    mock_attempts.return_value = [{
        "created_at": "2025-02-28T00:00:00Z",
        "outcome": "not_found",
        "epc_found": None,
        "searches_performed": ["SunDev Sunrise Solar EPC"],
    }]
    mock_epcs.return_value = [_make_engagement(
        epc={"id": "ent-003", "name": "SOLV Energy"},
        project={"project_name": "Oberon", "mw_capacity": 339},
        confidence="confirmed",
    )]

    project = {"id": "proj-001", "developer": "SunDev LLC", "state": "TX"}
    context = build_knowledge_context(project)

    assert context is not None
    assert "What We Already Know" in context
    assert "SunDev LLC" in context
    assert "McCarthy Building" in context
    assert "Prior Research" in context
    assert "not_found" in context
    assert "SOLV Energy" in context


@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_no_data(mock_resolve, mock_attempts, mock_epcs):
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = None
    mock_attempts.return_value = []
    mock_epcs.return_value = []
    project = {"id": "proj-001", "developer": "Unknown Dev", "state": None}
    context = build_knowledge_context(project)
    assert context is None


# ---------------------------------------------------------------------------
# process_discovery_into_kb
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.resolve_or_create_entity")
@patch("src.knowledge_base.get_client")
def test_process_discovery_found(mock_get_client, mock_resolve):
    from src.knowledge_base import process_discovery_into_kb

    dev = _make_entity(name="SunDev LLC", id="ent-dev")
    epc = _make_entity(name="McCarthy Building", id="ent-epc", entity_type=["epc"])
    mock_resolve.side_effect = [dev, epc]

    table = MagicMock()
    table.insert.return_value.execute.return_value = _mock_response([{}])
    table.update.return_value.eq.return_value.execute.return_value = _mock_response([{}])
    mock_get_client.return_value.table.return_value = table

    result = make_agent_result(confidence="likely")
    project = {"id": "proj-001", "developer": "SunDev LLC", "state": "TX"}

    process_discovery_into_kb("proj-001", result, project)

    # Phase 2: process_discovery_into_kb only logs research_attempt (not engagement)
    # Engagement creation moved to promote_discovery_to_kb (on acceptance)
    assert table.insert.call_count == 1  # research_attempt only


@patch("src.knowledge_base.resolve_or_create_entity")
@patch("src.knowledge_base.get_client")
def test_process_discovery_not_found(mock_get_client, mock_resolve):
    from src.knowledge_base import process_discovery_into_kb

    dev = _make_entity(name="SunDev LLC", id="ent-dev")
    mock_resolve.return_value = dev

    table = MagicMock()
    table.insert.return_value.execute.return_value = _mock_response([{}])
    table.update.return_value.eq.return_value.execute.return_value = _mock_response([{}])
    mock_get_client.return_value.table.return_value = table

    result = make_agent_result(
        epc_contractor=None, confidence="unknown", sources=[], searches_performed=["test query"]
    )
    project = {"id": "proj-001", "developer": "SunDev LLC", "state": "TX"}

    process_discovery_into_kb("proj-001", result, project)

    # Should insert research_attempt but NOT engagement
    assert table.insert.call_count == 1  # only research_attempt


# ---------------------------------------------------------------------------
# query_knowledge_base
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.rebuild_profile_if_stale")
@patch("src.knowledge_base.resolve_entity")
def test_query_kb_by_name(mock_resolve, mock_rebuild):
    from src.knowledge_base import query_knowledge_base

    mock_resolve.return_value = _make_entity()
    mock_rebuild.return_value = "# SunDev LLC\nType: developer"

    result = query_knowledge_base(entity_name="SunDev LLC")
    assert "SunDev LLC" in result


@patch("src.knowledge_base.get_epcs_in_state")
def test_query_kb_by_state(mock_epcs):
    from src.knowledge_base import query_knowledge_base

    mock_epcs.return_value = [_make_engagement(
        epc={"id": "ent-002", "name": "SOLV Energy"},
        project={"project_name": "Oberon", "mw_capacity": 339},
        confidence="confirmed",
    )]

    result = query_knowledge_base(state="TX")
    assert "SOLV Energy" in result
    assert "TX" in result
    assert "339MW" in result


# ---------------------------------------------------------------------------
# build_knowledge_context — Developer Loyalty Stats
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.get_developer_engagements")
@patch("src.knowledge_base.rebuild_profile_if_stale")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_loyalty_stats(mock_resolve, mock_rebuild, mock_engs, mock_attempts, mock_epcs):
    """Developer loyalty stats show EPC usage percentages and strongest signal."""
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = _make_entity()
    mock_rebuild.return_value = ""
    mock_engs.return_value = [
        _make_engagement(id="eng-1", epc={"id": "e1", "name": "Blattner"}, state="TX",
                         project={"project_name": "Alpha", "mw_capacity": 200, "state": "TX"}),
        _make_engagement(id="eng-2", epc={"id": "e1", "name": "Blattner"}, state="TX",
                         project={"project_name": "Beta", "mw_capacity": 300, "state": "TX"}),
        _make_engagement(id="eng-3", epc={"id": "e2", "name": "McCarthy"}, state="IL",
                         project={"project_name": "Gamma", "mw_capacity": 150, "state": "IL"}),
    ]
    mock_attempts.return_value = []
    mock_epcs.return_value = []

    context = build_knowledge_context({"id": "p1", "developer": "SunDev LLC", "state": None})

    assert "3 engagements across 2 EPCs" in context
    assert "Blattner: 2 of 3 projects (67%)" in context
    assert "McCarthy: 1 of 3 projects (33%)" in context
    assert "Strongest signal" in context
    assert "Blattner" in context


@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.get_developer_engagements")
@patch("src.knowledge_base.rebuild_profile_if_stale")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_no_strongest_signal_when_even(mock_resolve, mock_rebuild, mock_engs, mock_attempts, mock_epcs):
    """No strongest signal note when EPCs are evenly split (50/50)."""
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = _make_entity()
    mock_rebuild.return_value = ""
    mock_engs.return_value = [
        _make_engagement(id="eng-1", epc={"id": "e1", "name": "Blattner"}, state="TX"),
        _make_engagement(id="eng-2", epc={"id": "e2", "name": "McCarthy"}, state="TX"),
    ]
    mock_attempts.return_value = []
    mock_epcs.return_value = []

    context = build_knowledge_context({"id": "p1", "developer": "SunDev LLC", "state": None})

    assert "Strongest signal" not in context


# ---------------------------------------------------------------------------
# build_knowledge_context — Negative Knowledge (failed searches)
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_negative_knowledge(mock_resolve, mock_attempts, mock_epcs):
    """Failed research attempts list tried searches and suggest new angles."""
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = None
    mock_attempts.return_value = [{
        "created_at": "2025-03-05T00:00:00Z",
        "outcome": "not_found",
        "epc_found": None,
        "searches_performed": ["Acme Solar TX EPC", "Acme Solar construction"],
    }]
    mock_epcs.return_value = []

    context = build_knowledge_context({"id": "proj-001", "developer": None, "state": None})

    assert "not_found after 2 searches" in context
    assert "do NOT repeat" in context
    assert '"Acme Solar TX EPC"' in context
    assert '"Acme Solar construction"' in context
    assert "Try different angles" in context


@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_found_attempt_no_negative_note(mock_resolve, mock_attempts, mock_epcs):
    """Successful research attempts don't show 'do NOT repeat' guidance."""
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = None
    mock_attempts.return_value = [{
        "created_at": "2025-03-05T00:00:00Z",
        "outcome": "found",
        "epc_found": "Blattner",
        "searches_performed": ["Acme Solar TX EPC"],
    }]
    mock_epcs.return_value = []

    context = build_knowledge_context({"id": "proj-001", "developer": None, "state": None})

    assert "Found: Blattner" in context
    assert "do NOT repeat" not in context


# ---------------------------------------------------------------------------
# build_knowledge_context — Enriched State EPC Stats
# ---------------------------------------------------------------------------

@patch("src.knowledge_base.get_epcs_in_state")
@patch("src.knowledge_base.get_project_research_attempts")
@patch("src.knowledge_base.resolve_entity")
def test_build_context_enriched_state_epcs(mock_resolve, mock_attempts, mock_epcs):
    """State EPC section shows aggregated project count, MW, recency."""
    from src.knowledge_base import build_knowledge_context

    mock_resolve.return_value = None
    mock_attempts.return_value = []
    mock_epcs.return_value = [
        _make_engagement(id="eng-1", epc={"id": "e1", "name": "Blattner"},
                         project={"project_name": "Alpha", "mw_capacity": 600},
                         confidence="confirmed", created_at="2026-02-15T00:00:00Z"),
        _make_engagement(id="eng-2", epc={"id": "e1", "name": "Blattner"},
                         project={"project_name": "Beta", "mw_capacity": 600},
                         confidence="confirmed", created_at="2026-01-10T00:00:00Z"),
        _make_engagement(id="eng-3", epc={"id": "e2", "name": "McCarthy"},
                         project={"project_name": "Gamma", "mw_capacity": 800},
                         confidence="likely", created_at="2025-11-20T00:00:00Z"),
    ]

    context = build_knowledge_context({"id": "p1", "developer": None, "state": "TX"})

    assert "from 3 known engagements" in context
    assert "Blattner" in context
    assert "2 projects" in context
    assert "1.2GW" in context
    assert "2026-02" in context
    assert "McCarthy" in context
    assert "800MW" in context
