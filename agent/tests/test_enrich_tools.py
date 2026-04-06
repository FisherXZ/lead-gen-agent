"""Tests for enrich_contact_email and enrich_contact_phone tools."""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

VALID_UUID = str(uuid.uuid4())
VALID_LINKEDIN = "https://www.linkedin.com/in/john-doe"


# ===========================================================================
# enrich_contact_email
# ===========================================================================


class TestEnrichContactEmailInput:
    """Pydantic Input validation for enrich_contact_email."""

    def test_valid_input(self):
        from src.tools.enrich_contact_email import Input

        inp = Input(contact_id=VALID_UUID, linkedin_url=VALID_LINKEDIN)
        assert inp.contact_id == VALID_UUID
        assert inp.linkedin_url == VALID_LINKEDIN

    def test_missing_contact_id_raises(self):
        from pydantic import ValidationError
        from src.tools.enrich_contact_email import Input

        with pytest.raises(ValidationError):
            Input(linkedin_url=VALID_LINKEDIN)  # type: ignore[call-arg]

    def test_missing_linkedin_url_raises(self):
        from pydantic import ValidationError
        from src.tools.enrich_contact_email import Input

        with pytest.raises(ValidationError):
            Input(contact_id=VALID_UUID)  # type: ignore[call-arg]


class TestEnrichContactEmailNoKeys:
    """No API keys configured → structured error."""

    @pytest.mark.asyncio
    async def test_no_keys_returns_error(self):
        from src.tools.enrich_contact_email import execute

        env = {"ENRICHMENT_API_KEY": "", "APOLLO_API_KEY": ""}
        with patch.dict(os.environ, env):
            os.environ.pop("ENRICHMENT_API_KEY", None)
            os.environ.pop("APOLLO_API_KEY", None)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "error"
        assert result["error_category"] == "api_key_missing"
        assert "No email enrichment API keys" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_validation_error(self):
        from src.tools.enrich_contact_email import execute

        with patch.dict(os.environ, {"ENRICHMENT_API_KEY": "key"}):
            result = await execute(
                {"contact_id": "not-a-uuid", "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "error"
        assert result["error_category"] == "validation_error"


class TestEnrichContactEmailPrimarySucceeds:
    """EnrichmentAPI (primary) returns email → success, DB updated."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ENRICHMENT_API_KEY": "enrich-key"})
    async def test_primary_provider_returns_email(self):
        from src.tools.enrich_contact_email import execute

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"email": "john@company.com"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_email.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_email.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["email"] == "john@company.com"
        assert result["data"]["source"] == "enrichment_api"
        assert result["data"]["contact_id"] == VALID_UUID
        assert result["source"] == "enrichment"

        # DB update was called
        mock_db.table.assert_called_with("contacts")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"ENRICHMENT_API_KEY": "enrich-key"})
    async def test_primary_sends_correct_request(self):
        from src.tools.enrich_contact_email import execute

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"email": "jane@example.com"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_email.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_email.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await execute({"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN})

        call_kwargs = mock_client.post.call_args
        assert "enrichmentapi.io" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"]["linkedin_url"] == VALID_LINKEDIN
        assert "Bearer enrich-key" in call_kwargs.kwargs["headers"]["Authorization"]


class TestEnrichContactEmailFallback:
    """Primary fails → Apollo fallback succeeds."""

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {"ENRICHMENT_API_KEY": "enrich-key", "APOLLO_API_KEY": "apollo-key"},
    )
    async def test_primary_fails_fallback_succeeds(self):
        from src.tools.enrich_contact_email import execute

        # First call (EnrichmentAPI) raises; second call (Apollo) succeeds
        enrich_resp = MagicMock()
        enrich_resp.raise_for_status.side_effect = Exception("EnrichmentAPI down")

        apollo_resp = MagicMock()
        apollo_resp.raise_for_status = MagicMock()
        apollo_resp.json.return_value = {"person": {"email": "fallback@company.com"}}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [enrich_resp, apollo_resp]

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_email.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_email.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["email"] == "fallback@company.com"
        assert result["data"]["source"] == "apollo"


class TestEnrichContactEmailAllFail:
    """All providers return empty → null result (not error)."""

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {"ENRICHMENT_API_KEY": "enrich-key", "APOLLO_API_KEY": "apollo-key"},
    )
    async def test_all_providers_empty_returns_null(self):
        from src.tools.enrich_contact_email import execute

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post.return_value = empty_resp

        with patch("src.tools.enrich_contact_email.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["email"] is None
        assert result["data"]["source"] is None


class TestEnrichContactEmailDefinition:
    def test_definition_name(self):
        from src.tools.enrich_contact_email import DEFINITION

        assert DEFINITION["name"] == "enrich_contact_email"

    def test_definition_required_fields(self):
        from src.tools.enrich_contact_email import DEFINITION

        required = DEFINITION["input_schema"]["required"]
        assert "contact_id" in required
        assert "linkedin_url" in required


# ===========================================================================
# enrich_contact_phone
# ===========================================================================


class TestEnrichContactPhoneInput:
    """Pydantic Input validation for enrich_contact_phone."""

    def test_valid_input(self):
        from src.tools.enrich_contact_phone import Input

        inp = Input(contact_id=VALID_UUID, linkedin_url=VALID_LINKEDIN)
        assert inp.contact_id == VALID_UUID
        assert inp.linkedin_url == VALID_LINKEDIN

    def test_missing_contact_id_raises(self):
        from pydantic import ValidationError
        from src.tools.enrich_contact_phone import Input

        with pytest.raises(ValidationError):
            Input(linkedin_url=VALID_LINKEDIN)  # type: ignore[call-arg]

    def test_missing_linkedin_url_raises(self):
        from pydantic import ValidationError
        from src.tools.enrich_contact_phone import Input

        with pytest.raises(ValidationError):
            Input(contact_id=VALID_UUID)  # type: ignore[call-arg]


class TestEnrichContactPhoneNoKeys:
    """No API keys configured → structured error."""

    @pytest.mark.asyncio
    async def test_no_keys_returns_error(self):
        from src.tools.enrich_contact_phone import execute

        for key in ["LEADMAGIC_API_KEY", "PROSPEO_API_KEY", "CONTACTOUT_API_KEY", "PDL_API_KEY"]:
            os.environ.pop(key, None)

        result = await execute(
            {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
        )

        assert result["status"] == "error"
        assert result["error_category"] == "api_key_missing"
        assert "No phone enrichment API keys" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_validation_error(self):
        from src.tools.enrich_contact_phone import execute

        with patch.dict(os.environ, {"LEADMAGIC_API_KEY": "key"}):
            result = await execute(
                {"contact_id": "not-a-uuid", "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "error"
        assert result["error_category"] == "validation_error"


class TestEnrichContactPhonePrimarySucceeds:
    """LeadMagic (primary) returns phone → success, DB updated."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"LEADMAGIC_API_KEY": "lm-key"})
    async def test_primary_provider_returns_phone(self):
        from src.tools.enrich_contact_phone import execute

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"phone": "+15551234567"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_phone.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_phone.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["phone"] == "+15551234567"
        assert result["data"]["source"] == "leadmagic"
        assert result["data"]["contact_id"] == VALID_UUID
        assert result["source"] == "enrichment"

        mock_db.table.assert_called_with("contacts")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"LEADMAGIC_API_KEY": "lm-key"})
    async def test_primary_sends_correct_request(self):
        from src.tools.enrich_contact_phone import execute

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"phone": "+15559876543"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_phone.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_phone.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await execute({"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN})

        call_kwargs = mock_client.post.call_args
        assert "leadmagic.io" in call_kwargs.args[0]
        assert call_kwargs.kwargs["json"]["linkedin_url"] == VALID_LINKEDIN
        assert call_kwargs.kwargs["headers"]["x-api-key"] == "lm-key"


class TestEnrichContactPhoneFallback:
    """Primary (LeadMagic) fails → Prospeo fallback succeeds."""

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {"LEADMAGIC_API_KEY": "lm-key", "PROSPEO_API_KEY": "prospeo-key"},
    )
    async def test_primary_fails_fallback_succeeds(self):
        from src.tools.enrich_contact_phone import execute

        lm_resp = MagicMock()
        lm_resp.raise_for_status.side_effect = Exception("LeadMagic down")

        prospeo_resp = MagicMock()
        prospeo_resp.raise_for_status = MagicMock()
        prospeo_resp.json.return_value = {"phone": "+15550001111"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [lm_resp, prospeo_resp]

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_phone.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_phone.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["phone"] == "+15550001111"
        assert result["data"]["source"] == "prospeo"

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "LEADMAGIC_API_KEY": "lm-key",
            "PROSPEO_API_KEY": "prospeo-key",
            "CONTACTOUT_API_KEY": "co-key",
            "PDL_API_KEY": "pdl-key",
        },
    )
    async def test_falls_through_to_pdl(self):
        from src.tools.enrich_contact_phone import execute

        # First 3 providers fail, PDL succeeds
        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = Exception("provider down")

        pdl_resp = MagicMock()
        pdl_resp.raise_for_status = MagicMock()
        pdl_resp.json.return_value = {"data": {"phone_numbers": ["+15552223333"]}}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [fail_resp, fail_resp, fail_resp, pdl_resp]

        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.tools.enrich_contact_phone.httpx.AsyncClient") as mock_cls, \
             patch("src.tools.enrich_contact_phone.get_client", return_value=mock_db, create=True):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["phone"] == "+15552223333"
        assert result["data"]["source"] == "pdl"


class TestEnrichContactPhoneAllFail:
    """All providers return empty → null result (not error)."""

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "LEADMAGIC_API_KEY": "lm-key",
            "PROSPEO_API_KEY": "prospeo-key",
            "CONTACTOUT_API_KEY": "co-key",
            "PDL_API_KEY": "pdl-key",
        },
    )
    async def test_all_providers_empty_returns_null(self):
        from src.tools.enrich_contact_phone import execute

        empty_resp = MagicMock()
        empty_resp.raise_for_status = MagicMock()
        empty_resp.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post.return_value = empty_resp

        with patch("src.tools.enrich_contact_phone.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await execute(
                {"contact_id": VALID_UUID, "linkedin_url": VALID_LINKEDIN}
            )

        assert result["status"] == "success"
        assert result["data"]["phone"] is None
        assert result["data"]["source"] is None


class TestEnrichContactPhoneDefinition:
    def test_definition_name(self):
        from src.tools.enrich_contact_phone import DEFINITION

        assert DEFINITION["name"] == "enrich_contact_phone"

    def test_definition_required_fields(self):
        from src.tools.enrich_contact_phone import DEFINITION

        required = DEFINITION["input_schema"]["required"]
        assert "contact_id" in required
        assert "linkedin_url" in required
