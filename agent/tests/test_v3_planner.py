"""Tests for v3 planner module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.v3.planner import (
    _fallback_queries,
    _format_project_summary,
    _parse_query_list,
    llm_plan,
)

PROJECT = {
    "project_name": "Sunbelt Solar",
    "developer": "AES Corporation",
    "mw_capacity": 250,
    "state": "TX",
    "iso_region": "ERCOT",
}


# ---------------------------------------------------------------------------
# test_plan_returns_query_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_returns_query_list():
    """Mock LLM returns JSON array → get list[str] back."""
    queries = [
        "AES Corporation Sunbelt Solar EPC contractor",
        "AES solar construction awarded TX",
        "Sunbelt Solar 250MW OSHA inspection",
    ]
    mock_response = MagicMock()
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_response.content = [MagicMock(text=json.dumps(queries))]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("src.v3.planner.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_plan(PROJECT, api_key="test-key")

    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(q, str) for q in result)
    assert result[0] == queries[0]


# ---------------------------------------------------------------------------
# test_plan_handles_code_block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_handles_code_block():
    """LLM returns ```json [...] ``` fenced block → still parsed correctly."""
    queries = ["query A", "query B"]
    fenced = f"```json\n{json.dumps(queries)}\n```"

    mock_response = MagicMock()
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_response.content = [MagicMock(text=fenced)]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("src.v3.planner.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_plan(PROJECT, api_key="test-key")

    assert result == queries


# ---------------------------------------------------------------------------
# test_plan_fallback_on_failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_fallback_on_failure():
    """LLM raises an exception → returns fallback queries derived from project fields."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

    with patch("src.v3.planner.anthropic.AsyncAnthropic", return_value=mock_client):
        result, _tokens = await llm_plan(PROJECT, api_key="test-key")

    assert isinstance(result, list)
    assert len(result) >= 1
    # Fallback should reference project name or developer
    combined = " ".join(result).lower()
    assert "aes" in combined or "sunbelt" in combined or "epc" in combined


# ---------------------------------------------------------------------------
# test_fallback_queries_from_project
# ---------------------------------------------------------------------------


def test_fallback_queries_from_project():
    """_fallback_queries generates reasonable queries from project fields."""
    queries = _fallback_queries(PROJECT)

    assert isinstance(queries, list)
    assert len(queries) >= 1

    combined = " ".join(queries).lower()
    # Should reference developer name
    assert "aes" in combined
    # Should reference project name or EPC keyword
    assert "epc" in combined or "sunbelt" in combined or "construction" in combined


def test_fallback_queries_minimal_project():
    """_fallback_queries works with a near-empty project dict."""
    queries = _fallback_queries({})
    assert len(queries) >= 1
    assert "epc" in queries[0].lower() or "solar" in queries[0].lower()


def test_parse_query_list_direct():
    """_parse_query_list handles a direct JSON array string."""
    raw = '["query one", "query two"]'
    result = _parse_query_list(raw)
    assert result == ["query one", "query two"]


def test_parse_query_list_garbage():
    """_parse_query_list returns empty list for unparseable input."""
    result = _parse_query_list("not json at all")
    assert result == []


def test_format_project_summary_full():
    """_format_project_summary includes all available fields."""
    summary = _format_project_summary(PROJECT)
    assert "Sunbelt Solar" in summary
    assert "AES Corporation" in summary
    assert "250" in summary
    assert "TX" in summary
    assert "ERCOT" in summary


def test_format_project_summary_empty():
    """_format_project_summary handles empty dict gracefully."""
    summary = _format_project_summary({})
    assert summary == "Unknown project"
