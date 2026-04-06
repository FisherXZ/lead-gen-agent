"""Tests for scrape_epc_website tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_valid_url_delegates_to_fetch_page_and_wraps_envelope():
    """Valid URL -> delegates to fetch_page.execute and returns success envelope."""
    from src.tools.scrape_epc_website import execute

    fetch_result = {
        "url": "https://example-epc.com/team",
        "text": "John Smith, VP of Construction. Jane Doe, Project Manager.",
        "length": 60,
    }

    with patch("src.tools.scrape_epc_website.fetch_page") as mock_fp:
        mock_fp.execute = AsyncMock(return_value=fetch_result)
        result = await execute({"url": "https://example-epc.com/team"})

    assert result["status"] == "success"
    assert result["source"] == "epc_website"
    assert result["data"]["url"] == "https://example-epc.com/team"
    assert "John Smith" in result["data"]["content"]
    mock_fp.execute.assert_awaited_once_with({"url": "https://example-epc.com/team"})


@pytest.mark.asyncio
async def test_fetch_page_error_wrapped_in_error_envelope():
    """fetch_page returning an error dict -> wrapped in error envelope."""
    from src.tools.scrape_epc_website import execute

    with patch("src.tools.scrape_epc_website.fetch_page") as mock_fp:
        mock_fp.execute = AsyncMock(return_value={"error": "HTTP 404: Not Found"})
        result = await execute({"url": "https://example-epc.com/missing"})

    assert result["status"] == "error"
    assert "HTTP 404" in result["error"]
    assert result["error_category"] == "fetch_error"


@pytest.mark.asyncio
async def test_pydantic_input_validation_empty_url_rejected():
    """Empty URL string fails Pydantic validation."""
    from pydantic import ValidationError

    from src.tools.scrape_epc_website import Input

    with pytest.raises(ValidationError):
        Input(url="")


@pytest.mark.asyncio
async def test_pydantic_input_valid_url_accepted():
    """Valid URL passes Pydantic validation."""
    from src.tools.scrape_epc_website import Input

    inp = Input(url="https://example-epc.com/about")
    assert inp.url == "https://example-epc.com/about"


def test_definition_name_and_description():
    """DEFINITION has correct name and contact-discovery description."""
    from src.tools.scrape_epc_website import DEFINITION

    assert DEFINITION["name"] == "scrape_epc_website"
    assert (
        "contact" in DEFINITION["description"].lower()
        or "personnel" in DEFINITION["description"].lower()
    )
    assert "url" in DEFINITION["input_schema"]["required"]
