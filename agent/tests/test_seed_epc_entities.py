"""Tests for seed_epc_entities — KB seeding pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# merge_rankings tests
# ---------------------------------------------------------------------------

def test_merge_exact_name_match():
    from src.seed_epc_entities import merge_rankings

    ws = [{"name": "SOLV Energy", "mw_installed": 13200, "rank": 1}]
    spw = [{"name": "SOLV Energy", "spw_rank": 1, "spw_kw_installed": 15000000, "spw_markets": ["utility"], "spw_service_type": "EPC"}]

    merged = merge_rankings(ws, spw)
    assert len(merged) == 1
    assert merged[0]["name"] == "SOLV Energy"
    assert merged[0]["wiki_solar_rank"] == 1
    assert merged[0]["spw_rank"] == 1
    assert merged[0]["mw_installed"] == 13200


def test_merge_alias_match():
    """Swinerton Renewable Energy should match to SOLV Energy."""
    from src.seed_epc_entities import merge_rankings

    ws = [{"name": "SOLV Energy", "mw_installed": 13200, "rank": 1}]
    spw = [{"name": "Swinerton Renewable Energy", "spw_rank": 1, "spw_kw_installed": 15000000, "spw_markets": ["utility"], "spw_service_type": "EPC"}]

    merged = merge_rankings(ws, spw)
    assert len(merged) == 1
    assert merged[0]["name"] == "SOLV Energy"
    assert merged[0]["spw_rank"] == 1


def test_merge_fuzzy_match():
    """'McCarthy Building' should fuzzy match 'McCarthy Building Companies'."""
    from src.seed_epc_entities import merge_rankings

    ws = [{"name": "McCarthy Building Companies", "mw_installed": 6200, "rank": 7}]
    spw = [{"name": "McCarthy Building Companies", "spw_rank": 2, "spw_kw_installed": 8500000, "spw_markets": ["utility"], "spw_service_type": "EPC"}]

    merged = merge_rankings(ws, spw)
    assert len(merged) == 1
    assert merged[0]["spw_rank"] == 2


def test_merge_unmatched_kept():
    """Entries in only one source should still appear in merged output."""
    from src.seed_epc_entities import merge_rankings

    ws = [{"name": "Acme Solar Builders", "mw_installed": 1000, "rank": 50}]
    spw = [{"name": "Zenith Renewable Construction", "spw_rank": 50, "spw_kw_installed": 500000, "spw_markets": ["utility"], "spw_service_type": "EPC"}]

    merged = merge_rankings(ws, spw)
    assert len(merged) == 2
    names = {m["name"] for m in merged}
    assert "Acme Solar Builders" in names
    assert "Zenith Renewable Construction" in names


def test_merge_no_double_matching():
    """Each SPW entry should match at most one Wiki-Solar entry."""
    from src.seed_epc_entities import merge_rankings

    ws = [
        {"name": "SOLV Energy", "mw_installed": 13200, "rank": 1},
        {"name": "Signal Energy", "mw_installed": 4800, "rank": 11},
    ]
    spw = [
        {"name": "SOLV Energy", "spw_rank": 1, "spw_kw_installed": 15000000, "spw_markets": ["utility"], "spw_service_type": "EPC"},
    ]

    merged = merge_rankings(ws, spw)
    assert len(merged) == 2
    solv = [m for m in merged if m["name"] == "SOLV Energy"][0]
    signal = [m for m in merged if m["name"] == "Signal Energy"][0]
    assert solv["spw_rank"] == 1
    assert "spw_rank" not in signal or signal.get("spw_rank") is None


# ---------------------------------------------------------------------------
# seed_entities tests
# ---------------------------------------------------------------------------

def test_seed_dry_run_no_writes():
    """Dry run should not write to DB."""
    from src.seed_epc_entities import seed_entities

    merged = [{"name": "Test EPC", "wiki_solar_rank": 1, "mw_installed": 5000, "ranking_source": "test"}]

    with patch("src.knowledge_base.resolve_entity", return_value=None), \
         patch("src.knowledge_base.resolve_or_create_entity") as mock_create:
        summary = seed_entities(merged, dry_run=True)

    mock_create.assert_not_called()
    assert summary["created"] == 1
    assert summary["updated"] == 0


def test_seed_skips_already_seeded():
    """Should skip entities that already have ranking metadata (without --force)."""
    from src.seed_epc_entities import seed_entities

    existing_entity = {
        "id": "entity-1",
        "name": "SOLV Energy",
        "entity_type": ["epc"],
        "metadata": {"wiki_solar_rank": 1, "mw_installed": 13200},
        "aliases": [],
    }

    merged = [{"name": "SOLV Energy", "wiki_solar_rank": 1, "mw_installed": 13200, "ranking_source": "test"}]

    with patch("src.knowledge_base.resolve_or_create_entity", return_value=existing_entity), \
         patch("src.db.get_client") as mock_get_client:
        summary = seed_entities(merged, dry_run=False, force=False)

    assert summary["skipped"] == 1
    mock_get_client.return_value.table.return_value.update.assert_not_called()


def test_seed_force_overwrites():
    """With --force, should overwrite existing metadata."""
    from src.seed_epc_entities import seed_entities

    existing_entity = {
        "id": "entity-1",
        "name": "SOLV Energy",
        "entity_type": ["epc"],
        "metadata": {"wiki_solar_rank": 2, "mw_installed": 10000},
        "aliases": [],
    }

    merged = [{"name": "SOLV Energy", "wiki_solar_rank": 1, "mw_installed": 13200, "ranking_source": "test"}]

    mock_client = MagicMock()
    with patch("src.knowledge_base.resolve_or_create_entity", return_value=existing_entity), \
         patch("src.db.get_client", return_value=mock_client):
        summary = seed_entities(merged, dry_run=False, force=True)

    assert summary["updated"] == 1
    # Verify the update was called with new metadata
    update_call = mock_client.table.return_value.update.call_args[0][0]
    assert update_call["metadata"]["wiki_solar_rank"] == 1
    assert update_call["metadata"]["mw_installed"] == 13200


def test_seed_adds_known_aliases():
    """Should populate aliases from KNOWN_ALIASES."""
    from src.seed_epc_entities import seed_entities

    new_entity = {
        "id": "entity-1",
        "name": "SOLV Energy",
        "entity_type": ["epc"],
        "metadata": {},
        "aliases": [],
    }

    merged = [{"name": "SOLV Energy", "wiki_solar_rank": 1, "mw_installed": 13200, "ranking_source": "test"}]

    mock_client = MagicMock()
    with patch("src.knowledge_base.resolve_or_create_entity", return_value=new_entity), \
         patch("src.db.get_client", return_value=mock_client):
        seed_entities(merged, dry_run=False, force=True)

    update_call = mock_client.table.return_value.update.call_args[0][0]
    aliases = update_call["aliases"]
    assert "Swinerton Renewable Energy" in aliases
    assert "Swinerton RE" in aliases


# ---------------------------------------------------------------------------
# Fallback data tests
# ---------------------------------------------------------------------------

def test_wiki_solar_fallback_has_data():
    from src.seed_epc_entities import _WIKI_SOLAR_FALLBACK

    assert len(_WIKI_SOLAR_FALLBACK) >= 15
    assert _WIKI_SOLAR_FALLBACK[0]["name"] == "SOLV Energy"
    assert _WIKI_SOLAR_FALLBACK[0]["rank"] == 1


def test_spw_fallback_has_data():
    from src.seed_epc_entities import _SPW_FALLBACK

    assert len(_SPW_FALLBACK) >= 10
    assert all("spw_rank" in e for e in _SPW_FALLBACK)
    assert all("spw_service_type" in e for e in _SPW_FALLBACK)


# ---------------------------------------------------------------------------
# Alias matching
# ---------------------------------------------------------------------------

def test_is_alias_positive():
    from src.seed_epc_entities import _is_alias

    assert _is_alias("Swinerton Renewable Energy", "SOLV Energy") is True
    assert _is_alias("Swinerton RE", "SOLV Energy") is True
    assert _is_alias("Blattner", "Blattner Energy") is True


def test_is_alias_negative():
    from src.seed_epc_entities import _is_alias

    assert _is_alias("Random Corp", "SOLV Energy") is False
    assert _is_alias("SOLV Energy", "SOLV Energy") is False  # Not an alias of itself
