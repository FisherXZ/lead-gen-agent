"""Tests for push_to_hubspot tool module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_missing_project_id():
    from src.tools.push_to_hubspot import execute

    result = await execute({"project_id": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_invalid_uuid():
    from src.tools.push_to_hubspot import execute

    result = await execute({"project_id": "not-a-uuid"})
    assert "error" in result


@pytest.mark.asyncio
async def test_no_settings_error():
    from src.tools.push_to_hubspot import execute

    with patch("src.hubspot.get_settings", return_value=None):
        result = await execute({"project_id": "123e4567-e89b-12d3-a456-426614174000"})

    assert "error" in result
    assert "not connected" in result["error"].lower()


@pytest.mark.asyncio
async def test_no_accepted_discovery():
    from src.tools.push_to_hubspot import execute

    mock_settings = {"api_key": "test-token", "pipeline_id": None, "deal_stage_id": None}
    mock_project = {"id": "proj-1", "project_name": "Test"}

    mock_table = MagicMock()
    eq_chain = mock_table.select.return_value.eq.return_value
    eq_chain.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    with (
        patch("src.hubspot.get_settings", return_value=mock_settings),
        patch("src.db.get_project", return_value=mock_project),
        patch("src.db.get_client", return_value=mock_client),
    ):
        result = await execute({"project_id": "123e4567-e89b-12d3-a456-426614174000"})

    assert "error" in result
    assert "accepted" in result["error"].lower()


def test_tool_registered():
    from src.tools import get_tool_names

    assert "push_to_hubspot" in get_tool_names()


def test_tool_definition():
    from src.tools.push_to_hubspot import DEFINITION

    assert DEFINITION["name"] == "push_to_hubspot"
    assert "project_id" in DEFINITION["input_schema"]["required"]
