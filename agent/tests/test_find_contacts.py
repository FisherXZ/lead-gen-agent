"""Tests for find_contacts tool module."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_missing_entity_id():
    from src.tools.find_contacts import execute

    result = await execute({"entity_id": "", "entity_name": "McCarthy"})
    assert "error" in result


@pytest.mark.asyncio
async def test_missing_entity_name():
    from src.tools.find_contacts import execute

    result = await execute({"entity_id": "123e4567-e89b-12d3-a456-426614174000", "entity_name": ""})
    assert "error" in result


@pytest.mark.asyncio
async def test_invalid_uuid():
    from src.tools.find_contacts import execute

    result = await execute({"entity_id": "not-a-uuid", "entity_name": "McCarthy"})
    assert "error" in result
    assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_cache_hit_returns_fast():
    from src.tools.find_contacts import execute

    cached = [{"full_name": "Cached Person", "title": "VP"}]

    with patch("src.tools.find_contacts.cache_get", return_value=cached):
        result = await execute(
            {
                "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "entity_name": "McCarthy",
            }
        )

    assert result["cached"] is True
    assert result["contacts"] == cached


@pytest.mark.asyncio
async def test_db_cache_hit():
    """If contacts exist in DB but not in tool cache, return them."""
    from src.tools.find_contacts import execute

    db_contacts = [{"full_name": "DB Person", "title": "Director"}]

    with (
        patch("src.tools.find_contacts.cache_get", return_value=None),
        patch("src.tools.find_contacts.cache_set"),
        patch("src.db.get_contacts_for_entity", return_value=db_contacts),
    ):
        result = await execute(
            {
                "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "entity_name": "Test EPC",
            }
        )

    assert result["cached"] is True
    assert result["contacts"] == db_contacts


@pytest.mark.asyncio
async def test_runs_discovery_on_cache_miss():
    """On full cache miss, runs discover_contacts."""
    from src.tools.find_contacts import execute

    discovered = [{"full_name": "New Person", "title": "VP Solar"}]

    with (
        patch("src.tools.find_contacts.cache_get", return_value=None),
        patch("src.tools.find_contacts.cache_set"),
        patch("src.db.get_contacts_for_entity", return_value=[]),
        patch("src.contact_discovery.discover_contacts", return_value=discovered),
    ):
        result = await execute(
            {
                "entity_id": "123e4567-e89b-12d3-a456-426614174000",
                "entity_name": "Test EPC",
            }
        )

    assert result["cached"] is False
    assert result["count"] == 1
    assert result["contacts"] == discovered


def test_tool_registered():
    from src.tools import get_tool_names

    assert "find_contacts" in get_tool_names()


def test_tool_definition():
    from src.tools.find_contacts import DEFINITION

    assert DEFINITION["name"] == "find_contacts"
    assert "entity_id" in DEFINITION["input_schema"]["required"]
    assert "entity_name" in DEFINITION["input_schema"]["required"]
