"""Tests for search_wiki_solar and search_spw tool modules."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Wiki-Solar tool tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wiki_solar_empty_name():
    from src.tools.search_wiki_solar import execute

    result = await execute({"epc_name": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_wiki_solar_entity_not_found():
    from src.tools.search_wiki_solar import execute

    with patch("src.knowledge_base.resolve_entity", return_value=None):
        result = await execute({"epc_name": "Nonexistent Corp"})

    assert result["found"] is False


@pytest.mark.asyncio
async def test_wiki_solar_entity_with_ranking():
    from src.tools.search_wiki_solar import execute

    entity = {
        "name": "SOLV Energy",
        "entity_type": ["epc"],
        "aliases": ["Swinerton Renewable Energy"],
        "metadata": {
            "wiki_solar_rank": 1,
            "mw_installed": 13200,
            "ranking_source": "wiki-solar-2024-11",
        },
    }

    with patch("src.knowledge_base.resolve_entity", return_value=entity):
        result = await execute({"epc_name": "SOLV Energy"})

    assert result["found"] is True
    assert result["wiki_solar_rank"] == 1
    assert result["mw_installed"] == 13200
    assert result["source_type"] == "wiki_solar_ranking"
    assert any("Swinerton" in a for a in result["aliases"])


@pytest.mark.asyncio
async def test_wiki_solar_entity_without_ranking():
    from src.tools.search_wiki_solar import execute

    entity = {
        "name": "Small Solar Co",
        "entity_type": ["epc"],
        "aliases": [],
        "metadata": {},
    }

    with patch("src.knowledge_base.resolve_entity", return_value=entity):
        result = await execute({"epc_name": "Small Solar Co"})

    assert result["found"] is True
    assert result["ranked"] is False


# ---------------------------------------------------------------------------
# SPW tool tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spw_empty_name():
    from src.tools.search_spw import execute

    result = await execute({"epc_name": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_spw_entity_with_ranking():
    from src.tools.search_spw import execute

    entity = {
        "name": "McCarthy Building Companies",
        "entity_type": ["epc"],
        "aliases": [],
        "metadata": {
            "spw_rank": 3,
            "spw_kw_installed": 5200000,
            "spw_markets": ["utility", "C&I"],
            "spw_service_type": "EPC",
        },
    }

    with patch("src.knowledge_base.resolve_entity", return_value=entity):
        result = await execute({"epc_name": "McCarthy Building Companies"})

    assert result["found"] is True
    assert result["spw_rank"] == 3
    assert result["spw_service_type"] == "EPC"
    assert "utility" in result["spw_markets"]
    assert result["source_type"] == "spw_ranking"


@pytest.mark.asyncio
async def test_spw_entity_not_found():
    from src.tools.search_spw import execute

    with patch("src.knowledge_base.resolve_entity", return_value=None):
        result = await execute({"epc_name": "Unknown"})

    assert result["found"] is False


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

def test_tools_registered():
    from src.tools import get_tool_names

    names = get_tool_names()
    assert "search_wiki_solar" in names
    assert "search_spw" in names
