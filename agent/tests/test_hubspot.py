"""Tests for hubspot module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_fernet_roundtrip():
    """Encrypt + decrypt produces original text."""
    from src.hubspot import _decrypt, _encrypt

    with patch.dict(
        "os.environ", {"HUBSPOT_ENCRYPTION_KEY": "VGVzdEtleUZvckhCU1BvdEZlcm5ldDMyYg=="}
    ):
        # Generate a real Fernet key for testing
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()

        with patch.dict("os.environ", {"HUBSPOT_ENCRYPTION_KEY": key}):
            original = "pat-na1-test-token-12345"
            encrypted = _encrypt(original)
            assert encrypted != original
            decrypted = _decrypt(encrypted)
            assert decrypted == original


def test_fernet_missing_key_raises():
    """Missing HUBSPOT_ENCRYPTION_KEY raises clear error."""
    from src.hubspot import _encrypt

    with patch.dict("os.environ", {}, clear=True):
        # Remove the key
        import os

        old = os.environ.pop("HUBSPOT_ENCRYPTION_KEY", None)
        try:
            with pytest.raises(ValueError, match="HUBSPOT_ENCRYPTION_KEY"):
                _encrypt("test")
        finally:
            if old:
                os.environ["HUBSPOT_ENCRYPTION_KEY"] = old


def test_validate_token_success():
    """Valid token returns account info."""
    from src.hubspot import validate_token

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"portalId": 12345, "accountType": "STANDARD"}

    with patch("src.hubspot.httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = validate_token("pat-test-token")

    assert result["portalId"] == 12345


def test_validate_token_401():
    """Invalid token raises ValueError."""
    from src.hubspot import validate_token

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("src.hubspot.httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="Invalid or revoked"):
            validate_token("bad-token")


def test_search_company_found():
    """Search returns existing company ID."""
    from src.hubspot import search_company

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": [{"id": "hs-123"}]}

    with patch("src.hubspot.httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = search_company("McCarthy Building", "token")

    assert result == "hs-123"


def test_search_company_not_found():
    """Search returns None when no results."""
    from src.hubspot import search_company

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    with patch("src.hubspot.httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = search_company("Nonexistent Corp", "token")

    assert result is None


def test_create_company():
    """Create company returns HubSpot ID."""
    from src.hubspot import create_company

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"id": "hs-new-456"}

    with patch("src.hubspot.httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = create_company({"name": "McCarthy", "entity_type": ["epc"]}, "token")

    assert result == "hs-new-456"


def test_push_discovery_full_success():
    """Full push creates company + deal + contacts."""
    from src.hubspot import push_discovery

    mock_table = MagicMock()
    eq_chain = mock_table.select.return_value.eq.return_value.eq.return_value
    eq_chain.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[{}])
    mock_db = MagicMock()
    mock_db.table.return_value = mock_table

    with (
        patch("src.hubspot.get_client", return_value=mock_db),
        patch("src.hubspot.search_company", return_value=None),
        patch("src.hubspot.create_company", return_value="hs-co-1"),
        patch("src.hubspot.create_deal", return_value="hs-deal-1"),
        patch("src.hubspot.create_contact", return_value="hs-ct-1"),
        patch("src.hubspot._associate"),
    ):
        result = push_discovery(
            project={"id": "proj-1", "project_name": "Test Solar", "mw_capacity": 200},
            entity={"id": "ent-1", "name": "McCarthy"},
            contacts=[{"id": "ct-1", "full_name": "John Smith", "title": "VP"}],
            token="test-token",
        )

    assert result["company"]["status"] == "created"
    assert result["deal"]["status"] == "created"
    assert len(result["contacts"]) == 1
    assert result["errors"] == []


def test_push_discovery_partial_failure():
    """Deal failure doesn't prevent contact creation."""
    from src.hubspot import push_discovery

    mock_table = MagicMock()
    eq_chain = mock_table.select.return_value.eq.return_value.eq.return_value
    eq_chain.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[{}])
    mock_db = MagicMock()
    mock_db.table.return_value = mock_table

    with (
        patch("src.hubspot.get_client", return_value=mock_db),
        patch("src.hubspot.search_company", return_value=None),
        patch("src.hubspot.create_company", return_value="hs-co-1"),
        patch("src.hubspot.create_deal", side_effect=RuntimeError("Deal creation failed")),
        patch("src.hubspot.create_contact", return_value="hs-ct-1"),
        patch("src.hubspot._associate"),
    ):
        result = push_discovery(
            project={"id": "proj-1", "project_name": "Test"},
            entity={"id": "ent-1", "name": "EPC Corp"},
            contacts=[{"id": "ct-1", "full_name": "Jane Doe"}],
            token="test-token",
        )

    assert result["company"]["status"] == "created"
    assert result["deal"] is None  # Deal failed
    assert len(result["contacts"]) == 1  # Contact still created
    assert len(result["errors"]) >= 1
    assert "Deal" in result["errors"][0]
