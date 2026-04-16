"""Tests for evidence compression layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.evidence_compression import (
    FALLBACK_TRUNCATE,
    MIN_CONTENT_LENGTH,
    compress_evidence,
    is_compression_enabled,
)


class TestIsCompressionEnabled:
    def test_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            assert is_compression_enabled() is False

    def test_enabled_when_set(self):
        with patch.dict("os.environ", {"EVIDENCE_COMPRESSION": "1"}):
            assert is_compression_enabled() is True

    def test_disabled_when_zero(self):
        with patch.dict("os.environ", {"EVIDENCE_COMPRESSION": "0"}):
            assert is_compression_enabled() is False

    def test_disabled_when_empty(self):
        with patch.dict("os.environ", {"EVIDENCE_COMPRESSION": ""}):
            assert is_compression_enabled() is False


class TestShortContentPassthrough:
    @pytest.mark.asyncio
    async def test_short_content_unchanged(self):
        """Content shorter than MIN_CONTENT_LENGTH passes through unchanged."""
        short = "This is short text."
        result = await compress_evidence(short, query_context="test project")
        assert result == short

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self):
        """Content at exactly MIN_CONTENT_LENGTH passes through."""
        text = "x" * (MIN_CONTENT_LENGTH - 1)
        result = await compress_evidence(text, query_context="test")
        assert result == text


class TestCompression:
    @pytest.mark.asyncio
    async def test_long_content_gets_compressed(self):
        """Long content is sent to Haiku and compressed result returned."""
        long_text = "A" * 2000
        compressed = "McCarthy Building awarded EPC contract."

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=compressed)]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.evidence_compression.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await compress_evidence(long_text, query_context="Sunrise Solar project")

        assert result == compressed
        # Verify the API was called
        mock_client.messages.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prompt_includes_query_context(self):
        """The compression prompt includes the query context."""
        long_text = "B" * 2000

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Relevant content.")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.evidence_compression.anthropic.AsyncAnthropic", return_value=mock_client):
            await compress_evidence(long_text, query_context="Desert Wind solar farm TX")

        call_args = mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Desert Wind solar farm TX" in prompt

    @pytest.mark.asyncio
    async def test_empty_result_falls_back_to_truncation(self):
        """If Haiku returns very short result, fall back to truncation."""
        long_text = "C" * 2000

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="")]  # Empty result

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.evidence_compression.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await compress_evidence(long_text, query_context="test")

        assert len(result) == FALLBACK_TRUNCATE
        assert result == long_text[:FALLBACK_TRUNCATE]


class TestFailureFallback:
    @pytest.mark.asyncio
    async def test_api_error_falls_back_to_truncation(self):
        """If Haiku API call fails, fall back to truncation."""
        long_text = "D" * 3000

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        with patch("src.evidence_compression.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await compress_evidence(long_text, query_context="test")

        assert len(result) == FALLBACK_TRUNCATE
        assert result == long_text[:FALLBACK_TRUNCATE]

    @pytest.mark.asyncio
    async def test_auth_error_falls_back(self):
        """Authentication error falls back gracefully."""
        import anthropic as anthropic_mod

        long_text = "E" * 3000

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic_mod.AuthenticationError(
                message="Invalid key",
                response=MagicMock(status_code=401),
                body=None,
            )
        )

        with patch("src.evidence_compression.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await compress_evidence(long_text, query_context="test")

        assert len(result) == FALLBACK_TRUNCATE
