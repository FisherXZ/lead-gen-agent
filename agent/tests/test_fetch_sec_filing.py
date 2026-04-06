"""Tests for fetch_sec_filing tool module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_no_input_returns_error():
    from src.tools.fetch_sec_filing import execute

    result = await execute({})
    assert "error" in result
    assert "accession_number" in result["error"].lower() or "url" in result["error"].lower()


@pytest.mark.asyncio
async def test_missing_cik_returns_error():
    """Accession without CIK gives helpful error."""
    from src.tools.fetch_sec_filing import execute

    result = await execute({"accession_number": "0001564590-25-012345"})
    assert "error" in result
    assert "cik" in result["error"].lower()


@pytest.mark.asyncio
async def test_invalid_accession_format():
    from src.tools.fetch_sec_filing import execute

    result = await execute({"accession_number": "invalid-format", "cik": "3153"})
    assert "error" in result
    assert "format" in result["error"].lower()


@pytest.mark.asyncio
async def test_cik_plus_accession_builds_correct_url():
    """CIK + accession + primary_document builds correct Archives URL."""
    from src.tools.fetch_sec_filing import _build_archives_url

    url = _build_archives_url("3153", "0001564590-25-012345", "smxt-20250805.htm")
    assert (
        url
        == "https://www.sec.gov/Archives/edgar/data/0000003153/000156459025012345/smxt-20250805.htm"
    )


@pytest.mark.asyncio
async def test_cik_plus_accession_no_primary_doc():
    """Without primary_document, URL points to index page."""
    from src.tools.fetch_sec_filing import _build_archives_url

    url = _build_archives_url("3153", "0001564590-25-012345")
    assert url == "https://www.sec.gov/Archives/edgar/data/0000003153/000156459025012345/"


@pytest.mark.asyncio
async def test_html_filing_extraction():
    from src.tools.fetch_sec_filing import execute

    html = """<html><body>
    <p>This is a press release about solar energy.</p>
    <p>SolarMax Technology awarded $127.3 million EPC contractor agreement
    for 430 MWh battery storage project in Texas. The EPC contractor will
    handle all engineering, procurement, and construction activities.</p>
    <p>About SolarMax Technology Inc.</p>
    </body></html>"""

    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    with (
        patch("src.tools.fetch_sec_filing.cache_get", return_value=None),
        patch("src.tools.fetch_sec_filing.cache_set"),
        patch("src.tools.fetch_sec_filing._fetch_with_retry", return_value=mock_response),
        patch(
            "trafilatura.extract",
            return_value=(
                "SolarMax Technology awarded $127.3 million EPC contractor "
                "agreement for 430 MWh battery storage project in Texas."
            ),
        ),
    ):
        result = await execute({"url": "https://sec.gov/test.htm"})

    assert "text" in result
    assert "EPC contractor" in result["text"]
    assert result["source_type"] == "sec_filing"


@pytest.mark.asyncio
async def test_cache_hit():
    from src.tools.fetch_sec_filing import execute

    cached = {
        "url": "https://sec.gov/test.htm",
        "text": "cached content",
        "source_type": "sec_filing",
    }

    with patch("src.tools.fetch_sec_filing.cache_get", return_value=cached):
        result = await execute({"url": "https://sec.gov/test.htm"})

    assert result["cached"] is True
    assert result["text"] == "cached content"


@pytest.mark.asyncio
async def test_404_returns_error():
    import httpx

    from src.tools.fetch_sec_filing import execute

    mock_response = MagicMock()
    mock_response.status_code = 404

    with (
        patch("src.tools.fetch_sec_filing.cache_get", return_value=None),
        patch(
            "src.tools.fetch_sec_filing._fetch_with_retry",
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response),
        ),
    ):
        result = await execute({"url": "https://sec.gov/missing.htm"})

    assert "error" in result
    assert "404" in result["error"]


def test_tool_registered():
    from src.tools import get_tool_names

    assert "fetch_sec_filing" in get_tool_names()
