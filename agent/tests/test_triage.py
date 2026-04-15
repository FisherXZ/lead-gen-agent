"""Tests for the triage pre-check module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import TriageResult
from src.triage import _is_poi_name, _is_utility, triage_project

# ──────────────────────────────────────────────────────────────
# Rule 1: Utility allow-list
# ──────────────────────────────────────────────────────────────


def test_utility_allowlist_match_sce():
    assert _is_utility("Southern California Edison") is True


def test_utility_allowlist_match_normalized():
    """Whitespace + case normalization."""
    assert _is_utility("  pg&e  ") is True


def test_utility_allowlist_no_match():
    assert _is_utility("NextEra Energy") is False


# ──────────────────────────────────────────────────────────────
# Rule 2: POI regex patterns
# ──────────────────────────────────────────────────────────────


def test_poi_regex_substation():
    assert _is_poi_name("Reynolds - Olive 345 kV") is True


def test_poi_regex_numeric_prefix():
    assert _is_poi_name("7COFFEEN - 7PANA 345.0kV") is True


def test_poi_regex_switching_station():
    assert _is_poi_name("Wheatley 500 kV Switching Station") is True


def test_poi_regex_marketing_name():
    assert _is_poi_name("Honey Creek Solar") is False


def test_poi_regex_taping():
    assert _is_poi_name("Taping 'Newport AB' to 'Cash' 345kV Line.") is True


# ──────────────────────────────────────────────────────────────
# Integration: triage_project
# ──────────────────────────────────────────────────────────────


def _mock_db_no_cache():
    """Return a mock Supabase client with no cached triage result."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [{"triage_result": None}]
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_resp
    )
    # Also mock update chain for _persist_triage
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )
    return mock_client


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_both_rules_fire(mock_get_client, mock_resolve, sample_project):
    """Utility developer + POI name -> both rules logged, resolution attempted."""
    mock_get_client.return_value = _mock_db_no_cache()
    mock_resolve.return_value = {
        "project_name": "Sunrise Solar Farm",
        "developer": "RealDev Corp",
        "confidence": "high",
        "sources": [],
    }

    sample_project["developer"] = "Southern California Edison"
    sample_project["project_name"] = "Reynolds - Olive 345 kV"

    result = await triage_project(sample_project)

    assert result.action == "research"
    assert result.corrected_project is not None
    assert result.corrected_project["project_name"] == "Sunrise Solar Farm"
    # Both rules should appear in triage_log
    rules = [entry.get("rule") for entry in result.triage_log]
    assert "utility_allowlist" in rules
    assert "poi_regex" in rules
    mock_resolve.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_neither_rule_fires(mock_get_client, mock_resolve, sample_project):
    """Real developer + marketing name -> pass through, no resolution."""
    mock_get_client.return_value = _mock_db_no_cache()

    result = await triage_project(sample_project)

    assert result.action == "research"
    assert result.corrected_project is None
    rules = [entry.get("rule") for entry in result.triage_log]
    assert "pass_through" in rules
    mock_resolve.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_resolve_success(mock_get_client, mock_resolve, sample_project):
    """High-confidence resolution -> corrected_project set."""
    mock_get_client.return_value = _mock_db_no_cache()
    mock_resolve.return_value = {
        "project_name": "Desert Bloom Solar",
        "developer": "SolarDev Inc",
        "confidence": "high",
        "sources": ["https://example.com"],
    }

    sample_project["developer"] = "PG&E"

    result = await triage_project(sample_project)

    assert result.action == "research"
    assert result.corrected_project["project_name"] == "Desert Bloom Solar"
    assert result.corrected_project["developer"] == "SolarDev Inc"


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_resolve_low_confidence(mock_get_client, mock_resolve, sample_project):
    """Low-confidence resolution -> action=skip."""
    mock_get_client.return_value = _mock_db_no_cache()
    mock_resolve.return_value = {
        "project_name": None,
        "developer": None,
        "confidence": "low",
        "sources": [],
    }

    sample_project["developer"] = "Entergy Arkansas"

    result = await triage_project(sample_project)

    assert result.action == "skip"
    assert result.skip_reason == "utility_as_developer_unresolved"


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_resolve_fails(mock_get_client, mock_resolve, sample_project):
    """Resolution returns low confidence with no name -> skip."""
    mock_get_client.return_value = _mock_db_no_cache()
    mock_resolve.return_value = {
        "project_name": None,
        "developer": None,
        "confidence": "low",
        "sources": [],
    }

    sample_project["project_name"] = "Reynolds - Olive 345 kV"

    result = await triage_project(sample_project)

    assert result.action == "skip"
    assert result.skip_reason == "poi_name_unresolved"


@pytest.mark.asyncio
@patch("src.triage.get_client")
async def test_cache_reuse(mock_get_client, sample_project):
    """Fresh cached triage_result -> used directly, no resolution."""
    mock_client = MagicMock()
    fresh_triaged_at = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    cached_result = {
        "action": "skip",
        "skip_reason": "utility_as_developer_unresolved",
        "corrected_project": None,
        "triaged_at": fresh_triaged_at,
    }
    mock_resp = MagicMock()
    mock_resp.data = [{"triage_result": cached_result}]
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_resp
    )
    mock_get_client.return_value = mock_client

    result = await triage_project(sample_project)

    assert result.action == "skip"
    assert result.skip_reason == "utility_as_developer_unresolved"
    rules = [entry.get("rule") for entry in result.triage_log]
    assert "cache_hit" in rules


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_cache_expired(mock_get_client, mock_resolve, sample_project):
    """Expired cached triage_result -> re-triages from scratch."""
    mock_client = MagicMock()
    old_triaged_at = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    cached_result = {
        "action": "skip",
        "skip_reason": "utility_as_developer_unresolved",
        "corrected_project": None,
        "triaged_at": old_triaged_at,
    }
    mock_resp = MagicMock()
    mock_resp.data = [{"triage_result": cached_result}]
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_resp
    )
    # Also mock update chain for _persist_triage
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock()
    )
    mock_get_client.return_value = mock_client

    mock_resolve.return_value = {
        "project_name": None,
        "developer": None,
        "confidence": "low",
        "sources": [],
    }

    # Give it a utility developer so a rule fires and resolution is attempted
    sample_project["developer"] = "SCE"

    result = await triage_project(sample_project)

    # Should NOT use cache — should re-triage
    rules = [entry.get("rule") for entry in result.triage_log]
    assert "cache_hit" not in rules
    mock_resolve.assert_awaited_once()


@pytest.mark.asyncio
@patch("src.triage._resolve_project_name", new_callable=AsyncMock)
@patch("src.triage.get_client")
async def test_returns_pydantic_model(mock_get_client, mock_resolve, sample_project):
    """Result is always a TriageResult instance."""
    mock_get_client.return_value = _mock_db_no_cache()
    mock_resolve.return_value = {
        "project_name": "Resolved Name",
        "developer": "Resolved Dev",
        "confidence": "medium",
        "sources": [],
    }

    sample_project["developer"] = "AEP"

    result = await triage_project(sample_project)

    assert isinstance(result, TriageResult)
    assert hasattr(result, "action")
    assert hasattr(result, "corrected_project")
    assert hasattr(result, "skip_reason")
    assert hasattr(result, "triage_log")
    assert hasattr(result, "tokens_used")
