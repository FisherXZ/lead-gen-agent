"""Tests for search_exa_people tool module."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Missing API key returns structured error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_returns_structured_error():
    """When EXA_API_KEY is not set, return structured error with correct category."""
    from src.tools.search_exa_people import execute

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXA_API_KEY", None)
        result = await execute({"query": "Signal Energy solar project manager Texas"})

    assert result["status"] == "error"
    assert result.get("error_category") == "api_key_missing"
    assert "EXA_API_KEY" in result["error"]


# ---------------------------------------------------------------------------
# Valid search returns correct envelope structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"EXA_API_KEY": "test-exa-key"})
async def test_successful_search_returns_correct_structure():
    """Valid search with mocked Exa API returns correct output envelope."""
    from src.tools.search_exa_people import _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Signal Energy | Leadership Team",
                "url": "https://signalenergy.com/team",
                "text": (
                    "John Doe, Senior Project Manager at Signal Energy, "
                    "oversees solar construction in Texas."
                ),
                "score": 0.95,
            },
            {
                "title": "LinkedIn: Jane Smith - Signal Energy",
                "url": "https://linkedin.com/in/janesmith",
                "text": "Jane Smith leads EPC coordination at Signal Energy.",
                "score": 0.88,
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("src.tools.search_exa_people.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await execute(
            {
                "query": "Signal Energy solar project manager Texas",
                "max_results": 10,
            }
        )

    assert result["status"] == "success"
    assert result["source"] == "exa"
    assert "data" in result
    assert "results" in result["data"]

    results = result["data"]["results"]
    assert len(results) == 2

    first = results[0]
    assert first["title"] == "Signal Energy | Leadership Team"
    assert first["url"] == "https://signalenergy.com/team"
    assert "John Doe" in first["text"]
    assert first["score"] == 0.95


@pytest.mark.asyncio
@patch.dict(os.environ, {"EXA_API_KEY": "test-exa-key"})
async def test_api_called_with_correct_payload():
    """Exa API is called with correct request body."""
    from src.tools.search_exa_people import _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("src.tools.search_exa_people.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await execute({"query": "Mortenson solar VP Texas", "max_results": 5})

    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args

    # Check auth header
    assert call_kwargs.kwargs["headers"]["x-api-key"] == "test-exa-key"

    # Check request body
    body = call_kwargs.kwargs["json"]
    assert body["query"] == "Mortenson solar VP Texas"
    assert body["type"] == "auto"
    assert body["numResults"] == 5
    assert "contents" in body
    assert body["contents"]["text"]["maxCharacters"] == 500


# ---------------------------------------------------------------------------
# Pydantic Input validation
# ---------------------------------------------------------------------------


def test_pydantic_input_valid():
    """Input model accepts valid inputs and applies defaults."""
    from src.tools.search_exa_people import Input

    inp = Input(query="McCarthy solar project manager")
    assert inp.query == "McCarthy solar project manager"
    assert inp.max_results == 10  # default


def test_pydantic_input_custom_max_results():
    """Input model accepts custom max_results within bounds."""
    from src.tools.search_exa_people import Input

    inp = Input(query="test query", max_results=5)
    assert inp.max_results == 5


def test_pydantic_input_rejects_out_of_range_max_results():
    """Input model rejects max_results outside [1, 20]."""
    from pydantic import ValidationError

    from src.tools.search_exa_people import Input

    with pytest.raises(ValidationError):
        Input(query="test", max_results=0)

    with pytest.raises(ValidationError):
        Input(query="test", max_results=21)


def test_pydantic_input_requires_query():
    """Input model requires query field."""
    from pydantic import ValidationError

    from src.tools.search_exa_people import Input

    with pytest.raises(ValidationError):
        Input()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Caching works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"EXA_API_KEY": "test-exa-key"})
async def test_cache_avoids_duplicate_calls():
    """Second identical call hits in-memory cache and skips HTTP request."""
    from src.tools.search_exa_people import _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch("src.tools.search_exa_people.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await execute({"query": "Blattner solar contacts"})
        result = await execute({"query": "Blattner solar contacts"})  # should hit cache

    assert mock_client.post.call_count == 1
    assert result.get("cached") is True
    assert result["status"] == "success"


@pytest.mark.asyncio
@patch.dict(os.environ, {"EXA_API_KEY": "test-exa-key"})
async def test_cache_respects_ttl():
    """Expired cache entries trigger a fresh API call."""
    import time

    from src.tools.search_exa_people import _CACHE_TTL, _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    # Manually inject an expired entry
    cache_key = ("blattner solar contacts", 10)
    _cache[cache_key] = (time.monotonic() - _CACHE_TTL - 1, [])

    with patch("src.tools.search_exa_people.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await execute({"query": "Blattner solar contacts"})

    # Should have made a fresh call despite cache entry existing
    assert mock_client.post.call_count == 1


# ---------------------------------------------------------------------------
# DEFINITION dict
# ---------------------------------------------------------------------------


def test_definition_name():
    from src.tools.search_exa_people import DEFINITION

    assert DEFINITION["name"] == "search_exa_people"


def test_definition_describes_people_search():
    from src.tools.search_exa_people import DEFINITION

    desc = DEFINITION["description"].lower()
    assert "people" in desc or "contact" in desc or "person" in desc


def test_definition_has_required_query():
    from src.tools.search_exa_people import DEFINITION

    assert "query" in DEFINITION["input_schema"]["required"]


# ---------------------------------------------------------------------------
# Tool registered in registry
# ---------------------------------------------------------------------------


def test_tool_registered():
    from src.tools import get_tool_names

    assert "search_exa_people" in get_tool_names()


# ---------------------------------------------------------------------------
# Blank query rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blank_query_returns_validation_error():
    """Whitespace-only query is rejected with validation_error category."""
    from src.tools.search_exa_people import execute

    result = await execute({"query": "   "})

    assert result["status"] == "error"
    assert result["error_category"] == "validation_error"
    assert "blank" in result["error"].lower()


# ---------------------------------------------------------------------------
# Cache size bounded to _MAX_CACHE_SIZE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, {"EXA_API_KEY": "test-exa-key"})
async def test_cache_does_not_exceed_max_size():
    """Cache evicts oldest entries when it exceeds _MAX_CACHE_SIZE."""
    from src.tools.search_exa_people import _MAX_CACHE_SIZE, _cache, execute

    _cache.clear()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    # Use a counter to give each call a unique, increasing monotonic time
    call_counter = [0]

    def monotonic_side_effect():
        call_counter[0] += 1
        return float(call_counter[0])

    with (
        patch("src.tools.search_exa_people.httpx.AsyncClient") as mock_cls,
        patch("src.tools.search_exa_people.time.monotonic", side_effect=monotonic_side_effect),
    ):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        for i in range(_MAX_CACHE_SIZE + 50):
            await execute({"query": f"unique query number {i}"})

    assert len(_cache) <= _MAX_CACHE_SIZE
