"""Tests for search_osha tool module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_empty_employer_returns_error():
    from src.tools.search_osha import execute

    result = await execute({"employer_name": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_parse_snapshot_fixture():
    """Parse the OSHA HTML snapshot fixture — the core correctness test."""
    from src.tools.search_osha import execute

    html = (FIXTURES / "osha_response.html").read_text()

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.text = html
    mock_client.post.return_value = mock_response

    with patch("src.tools.search_osha.httpx.AsyncClient") as mock_cls, \
         patch("src.tools.search_osha.cache_get", return_value=None), \
         patch("src.tools.search_osha.cache_set"):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await execute({"employer_name": "SOLV Energy"})

    assert "results" in result
    results = result["results"]
    assert len(results) == 3

    # First result: Pecos TX
    assert results[0]["employer_name"] == "SOLV Energy LLC"
    assert results[0]["inspection_number"] == "1696087"
    assert results[0]["naics_code"] == "238210"
    assert results[0]["city"] == "Pecos"
    assert results[0]["state"] == "TX"
    assert results[0]["inspection_date"] == "06/15/2025"
    assert results[0]["source_type"] == "osha_inspection"
    assert "osha.gov" in results[0]["detail_url"]

    # Third result: Wharton TX with different NAICS
    assert results[2]["naics_code"] == "237130"
    assert results[2]["city"] == "Wharton"


@pytest.mark.asyncio
async def test_no_results_returns_empty_list():
    from src.tools.search_osha import execute

    html = "<html><body>No matching records found</body></html>"

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = html
    mock_client.post.return_value = mock_response

    with patch("src.tools.search_osha.httpx.AsyncClient") as mock_cls, \
         patch("src.tools.search_osha.cache_get", return_value=None), \
         patch("src.tools.search_osha.cache_set"):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await execute({"employer_name": "Nonexistent Corp"})

    assert result["results"] == []


@pytest.mark.asyncio
async def test_html_structure_change_returns_error():
    """If OSHA redesigns their site, the parser should return an error, not garbage."""
    from src.tools.search_osha import execute

    # Large HTML with tables but completely different structure (>5000 chars)
    html = "<html><body>" + "<table><tr><td>totally different structure with lots of content padding</td></tr></table>\n" * 100 + "</body></html>"

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = html
    mock_client.post.return_value = mock_response

    with patch("src.tools.search_osha.httpx.AsyncClient") as mock_cls, \
         patch("src.tools.search_osha.cache_get", return_value=None):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await execute({"employer_name": "SOLV Energy"})

    assert "error" in result
    assert "structure" in result["error"].lower()


@pytest.mark.asyncio
async def test_cache_hit():
    from src.tools.search_osha import execute

    cached = [{"employer_name": "Test", "state": "TX"}]

    with patch("src.tools.search_osha.cache_get", return_value=cached):
        result = await execute({"employer_name": "Test Corp"})

    assert result["cached"] is True
    assert result["results"] == cached


@pytest.mark.asyncio
async def test_timeout_returns_error():
    from src.tools.search_osha import execute
    import httpx

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ReadTimeout("timeout")

    with patch("src.tools.search_osha.httpx.AsyncClient") as mock_cls, \
         patch("src.tools.search_osha.cache_get", return_value=None):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await execute({"employer_name": "SOLV Energy"})

    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_tool_registered():
    from src.tools import get_tool_names

    assert "search_osha" in get_tool_names()
