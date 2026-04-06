"""Tests for brave_search tool module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Missing API key returns helpful error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_returns_error():
    """When BRAVE_SEARCH_API_KEY is not set, return an error dict (no crash)."""
    from src.tools.brave_search import execute

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BRAVE_SEARCH_API_KEY", None)
        result = await execute({"query": "test query"})

    assert "error" in result
    assert "BRAVE_SEARCH_API_KEY" in result["error"]


# ---------------------------------------------------------------------------
# Empty query returns error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_query_returns_error():
    from src.tools.brave_search import execute

    result = await execute({"query": ""})
    assert "error" in result


# ---------------------------------------------------------------------------
# Successful search parses response correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test-brave-key"})
async def test_successful_search():
    from src.tools.brave_search import _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "web": {
            "results": [
                {
                    "title": "McCarthy Building EPC",
                    "url": "https://example.com/article",
                    "description": "McCarthy awarded solar contract",
                    "relevancy_score": 0.95,
                },
                {
                    "title": "Solar Project News",
                    "url": "https://example.com/news",
                    "description": "Industry update on solar EPCs",
                },
            ]
        }
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("src.tools.brave_search.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await execute({"query": "McCarthy solar EPC", "max_results": 5})

    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "McCarthy Building EPC"
    assert result["results"][0]["content"] == "McCarthy awarded solar contract"
    assert result["results"][0]["score"] == 0.95
    assert result["results"][1]["score"] == 0

    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["headers"]["X-Subscription-Token"] == "test-brave-key"


# ---------------------------------------------------------------------------
# Caching works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test-brave-key"})
async def test_cache_avoids_duplicate_calls():
    from src.tools.brave_search import _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"web": {"results": []}}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("src.tools.brave_search.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await execute({"query": "cached query"})
        result = await execute({"query": "cached query"})  # should hit cache

    assert mock_client.get.call_count == 1
    assert result.get("cached") is True


# ---------------------------------------------------------------------------
# Tool is registered in the tool registry
# ---------------------------------------------------------------------------


def test_tool_registered():
    from src.tools import get_tool_names

    assert "web_search_broad" in get_tool_names()


def test_tool_definition():
    from src.tools.brave_search import DEFINITION

    assert DEFINITION["name"] == "web_search_broad"
    assert "query" in DEFINITION["input_schema"]["required"]
