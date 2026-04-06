"""Tests for classify_contact tool module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"
VALID_CONTACT_UUID = "223e4567-e89b-12d3-a456-426614174001"
VALID_ENTITY_UUID = "323e4567-e89b-12d3-a456-426614174002"


# ---------------------------------------------------------------------------
# Pydantic Input validation
# ---------------------------------------------------------------------------


def test_pydantic_input_valid():
    from src.tools.classify_contact import Input

    inp = Input(contact_id=VALID_UUID)
    assert inp.contact_id == VALID_UUID


def test_pydantic_input_missing_contact_id():
    from pydantic import ValidationError

    from src.tools.classify_contact import Input

    with pytest.raises(ValidationError):
        Input()


# ---------------------------------------------------------------------------
# Validation errors returned from execute()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_uuid_returns_error():
    from src.tools.classify_contact import execute

    result = await execute({"contact_id": "not-a-uuid"})
    assert "error" in result
    assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_contact_not_found_returns_error():
    from src.tools.classify_contact import execute

    mock_client = MagicMock()
    chain = mock_client.table.return_value.select.return_value
    chain.eq.return_value.limit.return_value.execute.return_value.data = []

    with patch("src.tools.classify_contact.get_client", return_value=mock_client):
        result = await execute({"contact_id": VALID_UUID})

    assert "error" in result
    assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# Successful classification
# ---------------------------------------------------------------------------


def _make_anthropic_response(scores: dict) -> MagicMock:
    """Build a mock anthropic response that returns tool_use with score_contact."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "score_contact"
    tool_use_block.input = scores

    response = MagicMock()
    response.content = [tool_use_block]
    return response


@pytest.mark.asyncio
async def test_successful_classification():
    from src.tools.classify_contact import execute

    contact_row = {
        "id": VALID_CONTACT_UUID,
        "entity_id": VALID_ENTITY_UUID,
        "full_name": "Jane Smith",
        "title": "VP of Solar Construction",
        "linkedin_headline": "VP Solar Construction @ Blattner Energy",
        "linkedin_experience": [{"company": "Blattner Energy", "title": "VP Solar Construction"}],
        "source_method": "linkedin",
    }
    entity_row = {
        "id": VALID_ENTITY_UUID,
        "name": "Blattner Energy",
    }
    ai_scores = {
        "role_aligned": True,
        "is_decision_maker": True,
        "project_relevant": True,
        "persona_fit": True,
        "reasoning": {
            "role_reasoning": "Construction role",
            "decision_maker_reasoning": "VP level",
            "project_reasoning": "Solar division",
            "persona_reasoning": "Direct buyer",
        },
    }

    # Mock Supabase: contacts query then entity query then upsert
    mock_client = MagicMock()

    # contacts select
    contacts_resp = MagicMock()
    contacts_resp.data = [contact_row]

    # entities select
    entity_resp = MagicMock()
    entity_resp.data = [entity_row]

    # upsert
    upsert_resp = MagicMock()
    upsert_resp.data = [
        {"id": "score-uuid", **{f"ai_{k}": v for k, v in ai_scores.items() if k != "reasoning"}}
    ]

    def table_side_effect(table_name):
        tbl = MagicMock()
        if table_name == "contacts":
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
                contacts_resp
            )
        elif table_name == "entities":
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
                entity_resp
            )
        elif table_name == "contact_persona_scores":
            tbl.upsert.return_value.execute.return_value = upsert_resp
        return tbl

    mock_client.table.side_effect = table_side_effect

    mock_anthropic_response = _make_anthropic_response(ai_scores)
    mock_anthropic_client = MagicMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_anthropic_response)

    with (
        patch("src.tools.classify_contact.get_client", return_value=mock_client),
        patch(
            "src.tools.classify_contact.get_anthropic_client", return_value=mock_anthropic_client
        ),
    ):
        result = await execute({"contact_id": VALID_UUID})

    assert result["status"] == "success"
    data = result["data"]
    assert data["contact_id"] == VALID_UUID
    assert data["role_aligned"] is True
    assert data["is_decision_maker"] is True
    assert data["project_relevant"] is True
    assert data["persona_fit"] is True
    assert data["match_score"] == 1.0
    assert data["is_match"] is True
    assert "reasoning" in data
    assert result["source"] == "classification"


@pytest.mark.asyncio
async def test_partial_match_score():
    """Two true, two false → match_score 0.5, is_match False."""
    from src.tools.classify_contact import execute

    contact_row = {
        "id": VALID_CONTACT_UUID,
        "entity_id": VALID_ENTITY_UUID,
        "full_name": "Bob Jones",
        "title": "IT Manager",
        "linkedin_headline": "IT Manager @ Some EPC",
        "linkedin_experience": [],
        "source_method": "web",
    }
    entity_row = {"id": VALID_ENTITY_UUID, "name": "Some EPC"}
    ai_scores = {
        "role_aligned": False,
        "is_decision_maker": False,
        "project_relevant": True,
        "persona_fit": True,
        "reasoning": {
            "role_reasoning": "IT role",
            "decision_maker_reasoning": "Manager only",
            "project_reasoning": "Works in energy sector",
            "persona_reasoning": "Partially relevant",
        },
    }

    mock_client = MagicMock()

    def table_side_effect(table_name):
        tbl = MagicMock()
        if table_name == "contacts":
            resp = MagicMock()
            resp.data = [contact_row]
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = resp
        elif table_name == "entities":
            resp = MagicMock()
            resp.data = [entity_row]
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = resp
        elif table_name == "contact_persona_scores":
            resp = MagicMock()
            resp.data = [{"id": "score-uuid"}]
            tbl.upsert.return_value.execute.return_value = resp
        return tbl

    mock_client.table.side_effect = table_side_effect

    mock_anthropic_client = MagicMock()
    mock_anthropic_client.messages.create = AsyncMock(
        return_value=_make_anthropic_response(ai_scores)
    )

    with (
        patch("src.tools.classify_contact.get_client", return_value=mock_client),
        patch(
            "src.tools.classify_contact.get_anthropic_client", return_value=mock_anthropic_client
        ),
    ):
        result = await execute({"contact_id": VALID_UUID})

    assert result["status"] == "success"
    data = result["data"]
    assert data["role_aligned"] is False
    assert data["is_decision_maker"] is False
    assert data["project_relevant"] is True
    assert data["persona_fit"] is True
    assert data["match_score"] == pytest.approx(0.5)
    assert data["is_match"] is False


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_tool_registered():
    from src.tools import get_tool_names

    assert "classify_contact" in get_tool_names()


def test_tool_definition():
    from src.tools.classify_contact import DEFINITION

    assert DEFINITION["name"] == "classify_contact"
    assert "contact_id" in DEFINITION["input_schema"]["required"]
