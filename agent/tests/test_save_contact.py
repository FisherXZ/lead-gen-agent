"""Tests for save_contact tool.

TDD — written before implementation was finalised.

Coverage:
  1. Invalid entity_id returns an error dict (no DB call).
  2. Valid input calls supabase upsert with correct data.
  3. project_id triggers project_contacts insert.
  4. No project_id → project_contacts NOT called.
  5. Pydantic Input validation rejects bad input.
  6. DB error on contacts upsert returns error dict.
  7. project_contacts failure is non-fatal (contact still saved).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"
VALID_INPUT = {
    "entity_id": VALID_UUID,
    "full_name": "Jane Smith",
    "source_method": "linkedin",
}

_CONTACT_ID = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"


def _make_client(contact_id: str = _CONTACT_ID):
    """Return a MagicMock mimicking the Supabase client.table() chain.

    Returns (client, contacts_table_mock, project_contacts_table_mock).
    """
    client = MagicMock()

    # contacts upsert response
    contact_resp = MagicMock()
    contact_resp.data = [{"id": contact_id, "full_name": "Jane Smith"}]

    # project_contacts upsert response
    pc_resp = MagicMock()
    pc_resp.data = [{"id": "pc-uuid"}]

    contacts_tbl = MagicMock()
    contacts_tbl.upsert.return_value.execute.return_value = contact_resp

    pc_tbl = MagicMock()
    pc_tbl.upsert.return_value.execute.return_value = pc_resp

    def table_side_effect(table_name):
        if table_name == "contacts":
            return contacts_tbl
        elif table_name == "project_contacts":
            return pc_tbl
        return MagicMock()

    client.table.side_effect = table_side_effect
    return client, contacts_tbl, pc_tbl


# ---------------------------------------------------------------------------
# 1. Invalid UUID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_uuid_returns_error():
    from src.tools.save_contact import execute

    result = await execute({"entity_id": "not-a-uuid", "full_name": "Bob", "source_method": "linkedin"})

    assert "error" in result
    assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_empty_entity_id_returns_error():
    from src.tools.save_contact import execute

    result = await execute({"entity_id": "", "full_name": "Bob", "source_method": "exa"})

    assert "error" in result


# ---------------------------------------------------------------------------
# 2. Valid input — correct upsert payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_input_upserts_contact():
    from src.tools.save_contact import execute

    client, contacts_tbl, _pc_tbl = _make_client()

    with patch("src.tools.save_contact.get_client", return_value=client):
        result = await execute(VALID_INPUT)

    assert result["status"] == "success"
    assert result["source"] == "database"
    assert result["data"]["contact_id"] == _CONTACT_ID
    assert result["data"]["created"] is True

    # Verify upsert was called on "contacts" table
    contacts_tbl.upsert.assert_called_once()
    upserted_data = contacts_tbl.upsert.call_args[0][0]
    assert upserted_data["entity_id"] == VALID_UUID
    assert upserted_data["full_name"] == "Jane Smith"
    assert upserted_data["source_method"] == "linkedin"


@pytest.mark.asyncio
async def test_optional_fields_included_in_upsert():
    from src.tools.save_contact import execute

    client, contacts_tbl, _pc_tbl = _make_client()
    inp = {
        **VALID_INPUT,
        "title": "VP Solar Construction",
        "linkedin_url": "https://linkedin.com/in/janesmith",
        "linkedin_headline": "Solar EPC leader",
        "linkedin_location": "Austin, TX",
        "source_url": "https://example.com/profile",
        "hubspot_contact_id": "hs-123",
    }

    with patch("src.tools.save_contact.get_client", return_value=client):
        result = await execute(inp)

    assert result["status"] == "success"

    upserted_data = contacts_tbl.upsert.call_args[0][0]
    assert upserted_data["title"] == "VP Solar Construction"
    assert upserted_data["linkedin_url"] == "https://linkedin.com/in/janesmith"
    assert upserted_data["hubspot_contact_id"] == "hs-123"


# ---------------------------------------------------------------------------
# 3. project_id triggers project_contacts insert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_id_links_contact_to_project():
    from src.tools.save_contact import execute

    client, _contacts_tbl, pc_tbl = _make_client()
    inp = {**VALID_INPUT, "project_id": 42, "relevance_note": "Key buyer for TX project"}

    with patch("src.tools.save_contact.get_client", return_value=client):
        result = await execute(inp)

    assert result["status"] == "success"
    assert result["data"]["project_linked"] is True

    # Verify project_contacts upsert was called
    pc_tbl.upsert.assert_called_once()
    pc_data = pc_tbl.upsert.call_args[0][0]
    assert pc_data["project_id"] == 42
    assert pc_data["contact_id"] == _CONTACT_ID
    assert pc_data["relevance_note"] == "Key buyer for TX project"


# ---------------------------------------------------------------------------
# 4. No project_id → project_contacts NOT touched
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_project_id_skips_project_contacts():
    from src.tools.save_contact import execute

    client, _contacts_tbl, pc_tbl = _make_client()

    with patch("src.tools.save_contact.get_client", return_value=client):
        result = await execute(VALID_INPUT)

    assert result["data"]["project_linked"] is False

    # project_contacts upsert must not have been called
    pc_tbl.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Pydantic Input validation
# ---------------------------------------------------------------------------

def test_input_model_valid():
    from src.tools.save_contact import Input

    inp = Input(entity_id=VALID_UUID, full_name="Jane Smith", source_method="linkedin")
    assert inp.entity_id == VALID_UUID
    assert inp.project_id is None


def test_input_model_missing_full_name():
    from src.tools.save_contact import Input

    with pytest.raises(ValidationError):
        Input(entity_id=VALID_UUID, source_method="exa")  # full_name missing


def test_input_model_missing_source_method():
    from src.tools.save_contact import Input

    with pytest.raises(ValidationError):
        Input(entity_id=VALID_UUID, full_name="Jane Smith")  # source_method missing


def test_input_model_with_all_fields():
    from src.tools.save_contact import Input

    inp = Input(
        entity_id=VALID_UUID,
        project_id=99,
        full_name="John Doe",
        title="Director",
        linkedin_url="https://linkedin.com/in/johndoe",
        linkedin_headline="Solar construction",
        linkedin_location="Phoenix, AZ",
        linkedin_experience=[{"company": "Acme", "title": "VP"}],
        source_method="exa",
        source_url="https://exa.ai/result",
        hubspot_contact_id="hs-999",
        relevance_note="Decision maker",
    )
    assert inp.project_id == 99
    assert inp.linkedin_experience == [{"company": "Acme", "title": "VP"}]


# ---------------------------------------------------------------------------
# 6. DB error on contacts upsert returns error dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_error_returns_error_dict():
    from src.tools.save_contact import execute

    client = MagicMock()
    tbl = MagicMock()
    tbl.upsert.return_value.execute.side_effect = Exception("connection refused")
    client.table.return_value = tbl

    with patch("src.tools.save_contact.get_client", return_value=client):
        result = await execute(VALID_INPUT)

    assert "error" in result
    assert "database" in result["error"].lower()


# ---------------------------------------------------------------------------
# 7. project_contacts failure is non-fatal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_link_failure_is_non_fatal():
    """Contact is saved successfully even if project_contacts upsert fails."""
    from src.tools.save_contact import execute

    client = MagicMock()

    contact_resp = MagicMock()
    contact_resp.data = [{"id": _CONTACT_ID}]

    def table_side_effect(table_name):
        tbl = MagicMock()
        if table_name == "contacts":
            tbl.upsert.return_value.execute.return_value = contact_resp
        elif table_name == "project_contacts":
            tbl.upsert.return_value.execute.side_effect = Exception("FK violation")
        return tbl

    client.table.side_effect = table_side_effect

    inp = {**VALID_INPUT, "project_id": 10}

    with patch("src.tools.save_contact.get_client", return_value=client):
        result = await execute(inp)

    # Contact was saved
    assert result["status"] == "success"
    assert result["data"]["contact_id"] == _CONTACT_ID
    # Project link failed but we don't crash
    assert result["data"]["project_linked"] is False


# ---------------------------------------------------------------------------
# 8. Tool registration and DEFINITION
# ---------------------------------------------------------------------------

def test_tool_definition():
    from src.tools.save_contact import DEFINITION

    assert DEFINITION["name"] == "save_contact"
    required = DEFINITION["input_schema"]["required"]
    assert "entity_id" in required
    assert "full_name" in required
    assert "source_method" in required
