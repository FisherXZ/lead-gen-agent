"""Tests for search_enr tool module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_empty_name_returns_error():
    from src.tools.search_enr import execute

    result = await execute({"company_name": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_known_epc_found_in_fallback():
    """Known EPCs should match even when live fetch fails."""
    from src.tools.search_enr import execute

    with patch("src.tools.search_enr.cache_get", return_value=None), \
         patch("src.tools.search_enr._fetch_live_rankings", return_value=None):
        result = await execute({"company_name": "SOLV Energy"})

    assert result["matched"] is True
    assert len(result["results"]) >= 1
    assert result["results"][0]["company_name"] == "SOLV Energy"
    assert "enr_rank_power" in result["results"][0]


@pytest.mark.asyncio
async def test_unknown_company_returns_not_found():
    from src.tools.search_enr import execute

    with patch("src.tools.search_enr.cache_get", return_value=None), \
         patch("src.tools.search_enr._fetch_live_rankings", return_value=None):
        result = await execute({"company_name": "Totally Unknown Corp"})

    assert result["matched"] is False
    assert result["results"] == []
    assert "note" in result


@pytest.mark.asyncio
async def test_partial_name_match():
    """'McCarthy' should match 'McCarthy Building Companies'."""
    from src.tools.search_enr import execute

    with patch("src.tools.search_enr.cache_get", return_value=None), \
         patch("src.tools.search_enr._fetch_live_rankings", return_value=None):
        result = await execute({"company_name": "McCarthy"})

    assert result["matched"] is True
    assert any("McCarthy" in r["company_name"] for r in result["results"])


@pytest.mark.asyncio
async def test_cache_hit():
    from src.tools.search_enr import execute

    cached = {"SOLV Energy": {"enr_rank_power": 2, "enr_year": 2024}}

    with patch("src.tools.search_enr.cache_get", return_value=cached):
        result = await execute({"company_name": "SOLV Energy"})

    assert result["matched"] is True


def test_tool_registered():
    from src.tools import get_tool_names

    assert "search_enr" in get_tool_names()
