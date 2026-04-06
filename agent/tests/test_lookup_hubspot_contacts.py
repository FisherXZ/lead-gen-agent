"""Tests for lookup_hubspot_contacts tool — TDD (written before implementation).

Coverage:
  1. Missing API key returns graceful error
  2. Valid input with mocked HubSpot API returns correct structure
  3. Caching works (second call uses cache, no HTTP)
  4. Pydantic Input validation rejects invalid input via execute_tool
  5. Company not found in HubSpot returns company_found=False
  6. Domain-based search is included in search payload when provided
  7. DEFINITION matches expected tool contract
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hs_company_search_response(company_id: str | None):
    """Simulate a HubSpot company search response."""
    if company_id:
        return {
            "results": [
                {
                    "id": company_id,
                    "properties": {"name": "Acme Solar EPC", "domain": "acmesolar.com"},
                }
            ],
            "total": 1,
        }
    return {"results": [], "total": 0}


def _make_hs_contacts_response(contacts: list[dict]):
    """Simulate a HubSpot contacts association response."""
    return {
        "results": contacts,
    }


def _make_hs_contact_detail(contact_id: str):
    return {
        "id": contact_id,
        "properties": {
            "firstname": "Jane",
            "lastname": "Smith",
            "jobtitle": "VP of Construction",
            "email": "jane@acmesolar.com",
            "phone": "555-0100",
            "hs_last_activity_date": "2026-03-15T00:00:00Z",
        },
    }


def _make_hs_deals_response(deals: list[dict]):
    return {"results": deals}


# ---------------------------------------------------------------------------
# DEFINITION tests
# ---------------------------------------------------------------------------


def test_definition_shape():
    from src.tools.lookup_hubspot_contacts import DEFINITION

    assert DEFINITION["name"] == "lookup_hubspot_contacts"
    assert "company_name" in DEFINITION["input_schema"]["properties"]
    assert "company_name" in DEFINITION["input_schema"]["required"]
    assert "company_domain" in DEFINITION["input_schema"]["properties"]


def test_tool_registered():
    from src.tools import get_tool_names

    assert "lookup_hubspot_contacts" in get_tool_names()


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_input_missing_company_name():
    """Omitting company_name should yield a validation_error via execute_tool."""
    from src.tools import execute_tool

    result = await execute_tool("lookup_hubspot_contacts", {})  # company_name required

    assert result.get("error_category") == "validation_error"
    assert "Invalid input" in result.get("error", "")


@pytest.mark.asyncio
async def test_valid_input_no_domain():
    """company_name alone should pass Pydantic validation (domain is optional)."""
    from src.tools.lookup_hubspot_contacts import Input

    obj = Input(company_name="Acme Solar EPC")
    assert obj.company_name == "Acme Solar EPC"
    assert obj.company_domain is None


@pytest.mark.asyncio
async def test_valid_input_with_domain():
    """Both fields are accepted."""
    from src.tools.lookup_hubspot_contacts import Input

    obj = Input(company_name="Acme Solar EPC", company_domain="acmesolar.com")
    assert obj.company_domain == "acmesolar.com"


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_returns_error():
    """When HubSpot is not configured, execute returns a graceful error."""
    from src.tools.lookup_hubspot_contacts import execute

    with patch("src.hubspot.get_settings", return_value=None):
        result = await execute({"company_name": "Acme Solar EPC", "company_domain": None})

    assert result["status"] == "error"
    assert "error" in result
    assert result.get("error_category") == "api_error"


@pytest.mark.asyncio
async def test_missing_token_in_settings_returns_error():
    """Settings row exists but decryption fails (api_key is None)."""
    from src.tools.lookup_hubspot_contacts import execute

    with patch("src.hubspot.get_settings", return_value={"api_key": None}):
        result = await execute({"company_name": "Acme Solar EPC", "company_domain": None})

    assert result["status"] == "error"
    assert result.get("error_category") == "api_error"


# ---------------------------------------------------------------------------
# Company not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_not_found():
    """When HubSpot has no matching company, return company_found=False."""
    from src.tools.lookup_hubspot_contacts import execute

    mock_settings = {"api_key": "pat-na-test-token"}

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _make_hs_company_search_response(None)
    mock_resp.raise_for_status = MagicMock()

    mock_cache_get = MagicMock(return_value=None)
    mock_cache_set = MagicMock()

    with (
        patch("src.hubspot.get_settings", return_value=mock_settings),
        patch("src.tools.lookup_hubspot_contacts.cache_get", mock_cache_get),
        patch("src.tools.lookup_hubspot_contacts.cache_set", mock_cache_set),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_async_client = AsyncMock()
        mock_async_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_async_client

        result = await execute({"company_name": "Unknown Corp", "company_domain": None})

    assert result["status"] == "success"
    assert result["data"]["company_found"] is False
    assert result["data"]["contacts"] == []
    assert result["source"] == "hubspot"


# ---------------------------------------------------------------------------
# Valid result with contacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_result_with_contacts():
    """Full happy path: company found + contacts returned with correct structure."""
    from src.tools.lookup_hubspot_contacts import execute

    mock_settings = {"api_key": "pat-na-test-token"}

    # HubSpot API responses
    company_search_resp = MagicMock()
    company_search_resp.status_code = 200
    company_search_resp.json.return_value = _make_hs_company_search_response("hs-co-123")
    company_search_resp.raise_for_status = MagicMock()

    # Contacts associated with company
    contacts_assoc_resp = MagicMock()
    contacts_assoc_resp.status_code = 200
    contacts_assoc_resp.json.return_value = _make_hs_contacts_response([{"id": "con-1"}])
    contacts_assoc_resp.raise_for_status = MagicMock()

    # Individual contact detail
    contact_detail_resp = MagicMock()
    contact_detail_resp.status_code = 200
    contact_detail_resp.json.return_value = _make_hs_contact_detail("con-1")
    contact_detail_resp.raise_for_status = MagicMock()

    # Deals for contact
    deals_resp = MagicMock()
    deals_resp.status_code = 200
    deals_resp.json.return_value = _make_hs_deals_response(
        [
            {
                "id": "deal-1",
                "properties": {
                    "dealname": "Solar Farm TX",
                    "dealstage": "closedwon",
                    "amount": "500000",
                },
            }
        ]
    )
    deals_resp.raise_for_status = MagicMock()

    mock_cache_get = MagicMock(return_value=None)
    mock_cache_set = MagicMock()

    # post → company search, get calls → contacts assoc, contact detail, deals
    async def mock_post(*args, **kwargs):
        return company_search_resp

    async def mock_get(url, *args, **kwargs):
        if "/associations/contacts" in url:
            return contacts_assoc_resp
        if "/associations/deals" in url:
            return deals_resp
        # contact detail
        return contact_detail_resp

    with (
        patch("src.hubspot.get_settings", return_value=mock_settings),
        patch("src.tools.lookup_hubspot_contacts.cache_get", mock_cache_get),
        patch("src.tools.lookup_hubspot_contacts.cache_set", mock_cache_set),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(side_effect=mock_post)
        mock_async_client.get = AsyncMock(side_effect=mock_get)
        mock_client_cls.return_value.__aenter__.return_value = mock_async_client

        result = await execute({"company_name": "Acme Solar EPC", "company_domain": None})

    assert result["status"] == "success"
    data = result["data"]
    assert data["company_found"] is True
    assert data["hubspot_company_id"] == "hs-co-123"
    assert len(data["contacts"]) == 1

    contact = data["contacts"][0]
    assert contact["full_name"] == "Jane Smith"
    assert contact["title"] == "VP of Construction"
    assert contact["email"] == "jane@acmesolar.com"
    assert contact["phone"] == "555-0100"
    assert contact["hubspot_contact_id"] == "con-1"
    assert "last_activity" in contact
    assert isinstance(contact["deals"], list)
    assert result["source"] == "hubspot"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_caching_hit_skips_http():
    """When cache_get returns data, no HTTP call is made."""
    from src.tools.lookup_hubspot_contacts import execute

    cached_data = {
        "status": "success",
        "data": {"company_found": True, "hubspot_company_id": "hs-123", "contacts": []},
        "source": "hubspot",
    }

    mock_settings = {"api_key": "pat-na-test-token"}
    mock_cache_get = MagicMock(return_value=cached_data)

    with (
        patch("src.hubspot.get_settings", return_value=mock_settings),
        patch("src.tools.lookup_hubspot_contacts.cache_get", mock_cache_get),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        result = await execute({"company_name": "Acme Solar EPC", "company_domain": None})

    # No HTTP requests made
    mock_client_cls.assert_not_called()
    assert result == cached_data


@pytest.mark.asyncio
async def test_caching_miss_writes_cache():
    """On a cache miss, cache_set is called after a successful HubSpot query."""
    from src.tools.lookup_hubspot_contacts import execute

    mock_settings = {"api_key": "pat-na-test-token"}

    company_search_resp = MagicMock()
    company_search_resp.status_code = 200
    company_search_resp.json.return_value = _make_hs_company_search_response(None)
    company_search_resp.raise_for_status = MagicMock()

    mock_cache_get = MagicMock(return_value=None)
    mock_cache_set = MagicMock()

    with (
        patch("src.hubspot.get_settings", return_value=mock_settings),
        patch("src.tools.lookup_hubspot_contacts.cache_get", mock_cache_get),
        patch("src.tools.lookup_hubspot_contacts.cache_set", mock_cache_set),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(return_value=company_search_resp)
        mock_client_cls.return_value.__aenter__.return_value = mock_async_client

        await execute({"company_name": "Unknown Corp", "company_domain": None})

    mock_cache_set.assert_called_once()
    call_args = mock_cache_set.call_args
    # First positional arg is tool name, second is query params, third is data
    assert call_args[0][0] == "lookup_hubspot_contacts"


# ---------------------------------------------------------------------------
# Domain-based search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_included_in_search_when_provided():
    """When company_domain is given, the search payload includes a domain filter."""
    from src.tools.lookup_hubspot_contacts import execute

    mock_settings = {"api_key": "pat-na-test-token"}

    company_search_resp = MagicMock()
    company_search_resp.status_code = 200
    company_search_resp.json.return_value = _make_hs_company_search_response(None)
    company_search_resp.raise_for_status = MagicMock()

    mock_cache_get = MagicMock(return_value=None)
    mock_cache_set = MagicMock()

    captured_payloads = []

    async def capture_post(url, *args, **kwargs):
        captured_payloads.append(kwargs.get("json", {}))
        return company_search_resp

    with (
        patch("src.hubspot.get_settings", return_value=mock_settings),
        patch("src.tools.lookup_hubspot_contacts.cache_get", mock_cache_get),
        patch("src.tools.lookup_hubspot_contacts.cache_set", mock_cache_set),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(side_effect=capture_post)
        mock_client_cls.return_value.__aenter__.return_value = mock_async_client

        await execute({"company_name": "Acme Solar EPC", "company_domain": "acmesolar.com"})

    assert len(captured_payloads) > 0
    # The search payload's filterGroups should reference domain
    payload_str = str(captured_payloads)
    assert "domain" in payload_str or "acmesolar.com" in payload_str
