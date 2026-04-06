"""Tests for contact_discovery module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_parse_contacts_json_array():
    """Parse a clean JSON array response."""
    from src.contact_discovery import _parse_contacts

    text = json.dumps(
        [
            {
                "full_name": "John Smith",
                "title": "VP Procurement",
                "linkedin_url": "https://linkedin.com/in/jsmith",
            },
            {
                "full_name": "Jane Doe",
                "title": "Director Solar",
                "source_url": "https://epc.com/team",
            },
        ]
    )
    contacts = _parse_contacts(text)
    assert len(contacts) == 2
    assert contacts[0]["full_name"] == "John Smith"
    assert contacts[1]["title"] == "Director Solar"


@pytest.mark.asyncio
async def test_parse_contacts_markdown_fenced():
    """Parse JSON wrapped in markdown code fences."""
    from src.contact_discovery import _parse_contacts

    text = '```json\n[{"full_name": "Alice Brown", "title": "CTO"}]\n```'
    contacts = _parse_contacts(text)
    assert len(contacts) == 1
    assert contacts[0]["full_name"] == "Alice Brown"


@pytest.mark.asyncio
async def test_parse_contacts_embedded_in_text():
    """Parse JSON array embedded within surrounding text."""
    from src.contact_discovery import _parse_contacts

    text = 'Here are the contacts I found:\n[{"full_name": "Bob Lee", "title": "VP"}]\nThat is all.'
    contacts = _parse_contacts(text)
    assert len(contacts) == 1
    assert contacts[0]["full_name"] == "Bob Lee"


@pytest.mark.asyncio
async def test_parse_contacts_empty_response():
    """Empty string returns empty list."""
    from src.contact_discovery import _parse_contacts

    assert _parse_contacts("") == []
    assert _parse_contacts("[]") == []


@pytest.mark.asyncio
async def test_parse_contacts_invalid_json():
    """Invalid JSON returns empty list."""
    from src.contact_discovery import _parse_contacts

    assert _parse_contacts("not json at all") == []


@pytest.mark.asyncio
async def test_validate_contacts_filters_bad_entries():
    """Contacts without full_name are filtered out."""
    from src.contact_discovery import _validate_contacts

    contacts = [
        {"full_name": "Good Name", "title": "VP"},
        {"title": "No Name"},  # missing full_name
        {"full_name": "", "title": "Empty Name"},  # empty full_name
        {"full_name": "Also Good", "title": "Director"},
    ]
    valid = _validate_contacts(contacts)
    assert len(valid) == 2
    assert valid[0]["full_name"] == "Good Name"
    assert valid[1]["full_name"] == "Also Good"


@pytest.mark.asyncio
async def test_discover_contacts_sets_status():
    """Verify status tracking: pending → completed."""
    from src.contact_discovery import discover_contacts

    MagicMock()
    mock_table = MagicMock()
    mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    with (
        patch("src.contact_discovery.get_client", return_value=mock_client),
        patch(
            "src.contact_discovery._run_contact_agent",
            return_value=[{"full_name": "Test Person", "title": "VP"}],
        ),
        patch(
            "src.db.store_contacts",
            return_value=[{"id": "123", "full_name": "Test Person", "title": "VP"}],
        ),
    ):
        result = await discover_contacts("entity-123", "Test Corp")

    assert len(result) == 1

    # Verify status was set to pending then completed
    update_calls = mock_table.update.call_args_list
    assert len(update_calls) >= 2
    # First call sets pending
    assert update_calls[0][0][0]["contact_discovery_status"] == "pending"
    # Last call sets completed
    assert update_calls[-1][0][0]["contact_discovery_status"] == "completed"


@pytest.mark.asyncio
async def test_discover_contacts_sets_failed_on_error():
    """On agent error, status should be 'failed'."""
    from src.contact_discovery import discover_contacts

    mock_table = MagicMock()
    mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    with (
        patch("src.contact_discovery.get_client", return_value=mock_client),
        patch("src.contact_discovery._run_contact_agent", side_effect=RuntimeError("API crash")),
    ):
        result = await discover_contacts("entity-123", "Test Corp")

    assert result == []

    # Verify status was set to failed
    update_calls = mock_table.update.call_args_list
    failed_call = [c for c in update_calls if c[0][0].get("contact_discovery_status") == "failed"]
    assert len(failed_call) >= 1


@pytest.mark.asyncio
async def test_generate_outreach_context_success():
    """Outreach context generation returns text."""
    from src.contact_discovery import generate_outreach_context

    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "McCarthy just won a 400MW project in Texas."
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with patch("src.contact_discovery.get_anthropic_client", return_value=mock_client):
        result = await generate_outreach_context(
            project={
                "project_name": "Samson Solar",
                "mw_capacity": 400,
                "state": "TX",
                "expected_cod": "2026-Q3",
            },
            entity={"name": "McCarthy", "profile": "Top 10 EPC"},
            contact={"full_name": "John Smith", "title": "VP Procurement"},
        )

    assert result is not None
    assert "McCarthy" in result


@pytest.mark.asyncio
async def test_generate_outreach_context_failure():
    """On LLM failure, returns None instead of crashing."""
    from src.contact_discovery import generate_outreach_context

    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = RuntimeError("API error")

    with patch("src.contact_discovery.get_anthropic_client", return_value=mock_client):
        result = await generate_outreach_context(
            project={"project_name": "Test"},
            entity={"name": "Test EPC"},
            contact={"full_name": "Test Person"},
        )

    assert result is None
