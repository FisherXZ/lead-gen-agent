"""Tests for search_sec_edgar tool module (data.sec.gov API)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_tickers():
    """Clear the module-level tickers cache between tests."""
    from src.tools.search_sec_edgar import _clear_tickers_cache
    _clear_tickers_cache()
    yield
    _clear_tickers_cache()


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _mock_tickers():
    return _load_fixture("company_tickers_sample.json")


def _mock_submissions():
    return _load_fixture("sec_edgar_response.json")


@pytest.mark.asyncio
async def test_empty_company_name_returns_error():
    from src.tools.search_sec_edgar import execute

    result = await execute({"company_name": ""})
    assert "error" in result
    assert "company_name" in result["error"].lower()


@pytest.mark.asyncio
async def test_cik_direct_input():
    """Digits passed as company_name are used as CIK directly."""
    from src.tools.search_sec_edgar import execute

    submissions = _mock_submissions()

    with patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"), \
         patch("src.tools.search_sec_edgar._fetch_submissions", return_value=submissions):
        result = await execute({"company_name": "3153"})

    assert "results" in result
    assert len(result["results"]) > 0
    assert result["results"][0]["cik"] == "0000003153"


@pytest.mark.asyncio
async def test_fuzzy_match():
    """'First Solar' should match 'FIRST SOLAR, INC' in tickers."""
    from src.tools.search_sec_edgar import _resolve_cik

    tickers_data = _mock_tickers()

    with patch("src.tools.search_sec_edgar._fetch_tickers_with_retry", return_value=tickers_data), \
         patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"):
        cik, matched_name = await _resolve_cik("First Solar")

    assert cik == "1274494"
    assert "FIRST SOLAR" in matched_name.upper()


@pytest.mark.asyncio
async def test_submissions_parsing():
    """Mock submissions JSON, verify output format."""
    from src.tools.search_sec_edgar import execute

    tickers_data = _mock_tickers()
    submissions = _mock_submissions()

    with patch("src.tools.search_sec_edgar._fetch_tickers_with_retry", return_value=tickers_data), \
         patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"), \
         patch("src.tools.search_sec_edgar._fetch_submissions", return_value=submissions):
        result = await execute({"company_name": "SolarMax Technology"})

    assert "results" in result
    filings = result["results"]
    assert len(filings) > 0

    first = filings[0]
    assert first["company_name"] == "SolarMax Technology, Inc"
    assert first["form_type"] == "8-K"
    assert first["filing_date"] == "2025-08-05"
    assert first["accession_number"] == "0001564590-25-012345"
    assert first["primary_document"] == "smxt-20250805.htm"
    assert first["source_type"] == "sec_edgar"
    assert "Archives/edgar/data/" in first["url"]
    assert "cik" in first


@pytest.mark.asyncio
async def test_form_type_filter():
    """Only 8-K filings returned when filtered."""
    from src.tools.search_sec_edgar import execute

    tickers_data = _mock_tickers()
    submissions = _mock_submissions()

    with patch("src.tools.search_sec_edgar._fetch_tickers_with_retry", return_value=tickers_data), \
         patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"), \
         patch("src.tools.search_sec_edgar._fetch_submissions", return_value=submissions):
        result = await execute({"company_name": "SolarMax Technology", "form_type": "8-K"})

    assert "results" in result
    for filing in result["results"]:
        assert filing["form_type"] == "8-K"


@pytest.mark.asyncio
async def test_company_not_found():
    """Helpful error message for unknown companies."""
    from src.tools.search_sec_edgar import execute

    tickers_data = _mock_tickers()

    with patch("src.tools.search_sec_edgar._fetch_tickers_with_retry", return_value=tickers_data), \
         patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"):
        result = await execute({"company_name": "Completely Fake Company XYZ123"})

    assert "error" in result
    assert "not found" in result["error"].lower()
    assert "publicly-traded" in result["error"].lower()


@pytest.mark.asyncio
async def test_cache_hit_skips_http():
    from src.tools.search_sec_edgar import execute

    cached_data = [{"company_name": "Test Corp", "form_type": "8-K"}]

    with patch("src.tools.search_sec_edgar.cache_get", return_value=cached_data):
        result = await execute({"company_name": "Test Corp"})

    assert result["cached"] is True
    assert result["results"] == cached_data


@pytest.mark.asyncio
async def test_timeout_returns_error():
    from src.tools.search_sec_edgar import execute
    import httpx

    tickers_data = _mock_tickers()

    with patch("src.tools.search_sec_edgar._fetch_tickers_with_retry", return_value=tickers_data), \
         patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"), \
         patch("src.tools.search_sec_edgar._fetch_submissions", side_effect=httpx.ReadTimeout("timeout")):
        result = await execute({"company_name": "SolarMax Technology"})

    assert "error" in result
    assert "timed out" in result["error"].lower()


@pytest.mark.asyncio
async def test_rate_limit_returns_error():
    from src.tools.search_sec_edgar import execute
    import httpx

    tickers_data = _mock_tickers()
    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch("src.tools.search_sec_edgar._fetch_tickers_with_retry", return_value=tickers_data), \
         patch("src.tools.search_sec_edgar.cache_get", return_value=None), \
         patch("src.tools.search_sec_edgar.cache_set"), \
         patch("src.tools.search_sec_edgar._fetch_submissions",
               side_effect=httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)):
        result = await execute({"company_name": "SolarMax Technology"})

    assert "error" in result
    assert "rate limit" in result["error"].lower()


def test_tool_registered():
    from src.tools import get_tool_names

    assert "search_sec_edgar" in get_tool_names()


def test_tool_definition():
    from src.tools.search_sec_edgar import DEFINITION

    assert DEFINITION["name"] == "search_sec_edgar"
    assert "company_name" in DEFINITION["input_schema"]["required"]
