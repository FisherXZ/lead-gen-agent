"""Tests for firecrawl_scrape tool module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.tools.firecrawl_scrape import _MAX_CHARS, _validate_url, execute

# ---------------------------------------------------------------------------
# TestValidateUrl
# ---------------------------------------------------------------------------


class TestValidateUrl:
    def test_valid_https_url(self):
        assert _validate_url("https://example.com/page") is None

    def test_valid_http_url(self):
        assert _validate_url("http://example.com/page") is None

    def test_valid_url_with_path_and_query(self):
        assert _validate_url("https://example.com/path?q=1&r=2") is None

    def test_rejects_empty_string(self):
        result = _validate_url("")
        assert result is not None
        assert isinstance(result, str)

    def test_rejects_non_http_scheme_ftp(self):
        result = _validate_url("ftp://example.com/file.txt")
        assert result is not None

    def test_rejects_non_http_scheme_file(self):
        result = _validate_url("file:///etc/passwd")
        assert result is not None

    def test_rejects_url_with_credentials(self):
        result = _validate_url("https://user:pass@example.com/page")
        assert result is not None

    def test_rejects_url_with_username_only(self):
        result = _validate_url("https://user@example.com/page")
        assert result is not None

    def test_rejects_url_over_2000_chars(self):
        long_url = "https://example.com/" + "a" * 2000
        result = _validate_url(long_url)
        assert result is not None

    def test_accepts_url_at_exactly_2000_chars(self):
        # Build URL that is exactly 2000 chars
        base = "https://example.com/"
        path = "a" * (2000 - len(base))
        url = base + path
        assert len(url) == 2000
        assert _validate_url(url) is None

    def test_rejects_url_without_dot_in_hostname(self):
        result = _validate_url("http://localhost/page")
        assert result is not None


# ---------------------------------------------------------------------------
# TestExecute
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        """When FIRECRAWL_API_KEY is not set, return error with key name in message."""
        env = {k: v for k, v in os.environ.items() if k != "FIRECRAWL_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = await execute({"url": "https://example.com"})

        assert "error" in result
        assert "FIRECRAWL_API_KEY" in result["error"]

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_invalid_url_returns_error(self):
        result = await execute({"url": "ftp://example.com/file"})
        assert "error" in result

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_successful_scrape_returns_expected_fields(self):
        """Successful scrape returns url, text, length, source, status_code."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        mock_doc = MagicMock()
        mock_doc.markdown = "# Hello World\n\nThis is content."
        mock_doc.metadata = MagicMock()
        mock_doc.metadata.status_code = 200
        mock_doc.metadata.source_url = "https://example.com"

        mock_app = MagicMock()
        mock_app.scrape.return_value = mock_doc

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            result = await execute({"url": "https://example.com"})

        assert "error" not in result
        assert result["url"] == "https://example.com"
        assert result["text"] == "# Hello World\n\nThis is content."
        assert result["length"] == len("# Hello World\n\nThis is content.")
        assert result["source"] == "firecrawl"
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_content_over_max_chars_is_truncated(self):
        """Content exceeding _MAX_CHARS is truncated with '[... truncated]' suffix."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        long_content = "x" * (_MAX_CHARS + 5000)

        mock_doc = MagicMock()
        mock_doc.markdown = long_content
        mock_doc.metadata = MagicMock()
        mock_doc.metadata.status_code = 200
        mock_doc.metadata.source_url = "https://example.com/long"

        mock_app = MagicMock()
        mock_app.scrape.return_value = mock_doc

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            result = await execute({"url": "https://example.com/long"})

        assert "error" not in result
        assert result["text"].endswith("[... truncated]")
        assert len(result["text"]) == _MAX_CHARS

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_empty_markdown_returns_error(self):
        """When SDK returns empty/None markdown, return error with 'empty' or 'extract'."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        mock_doc = MagicMock()
        mock_doc.markdown = None
        mock_doc.metadata = MagicMock()
        mock_doc.metadata.status_code = 200
        mock_doc.metadata.source_url = "https://example.com/empty"

        mock_app = MagicMock()
        mock_app.scrape.return_value = mock_doc

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            result = await execute({"url": "https://example.com/empty"})

        assert "error" in result
        msg = result["error"].lower()
        assert "empty" in msg or "extract" in msg

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_empty_string_markdown_returns_error(self):
        """When SDK returns empty string markdown, return error."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        mock_doc = MagicMock()
        mock_doc.markdown = "   "  # whitespace only
        mock_doc.metadata = MagicMock()
        mock_doc.metadata.status_code = 200
        mock_doc.metadata.source_url = "https://example.com/ws"

        mock_app = MagicMock()
        mock_app.scrape.return_value = mock_doc

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            result = await execute({"url": "https://example.com/ws"})

        assert "error" in result
        msg = result["error"].lower()
        assert "empty" in msg or "extract" in msg

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_wall_clock_timeout_returns_error(self):
        """When the threaded call exceeds the wall-clock timeout, return a timeout error."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        def hang_briefly(url, api_key):
            import time

            time.sleep(2)  # simulate a hung SDK call (short so test suite stays fast)

        with (
            patch("src.tools.firecrawl_scrape._scrape_sync", side_effect=hang_briefly),
            patch("src.tools.firecrawl_scrape._SCRAPE_TIMEOUT_MS", 100),  # 0.1s timeout
        ):
            result = await execute({"url": "https://example.com/timeout"})

        assert "error" in result
        assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_sdk_exception_returns_error(self):
        """When SDK raises, return error dict with exception message."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        mock_app = MagicMock()
        mock_app.scrape.side_effect = RuntimeError("connection refused")

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            result = await execute({"url": "https://example.com/fail"})

        assert "error" in result
        assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# TestCache
# ---------------------------------------------------------------------------


class TestCache:
    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_second_call_hits_cache(self):
        """Second call for same URL hits cache; SDK called only once, result has cached=True."""
        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        mock_doc = MagicMock()
        mock_doc.markdown = "# Cached Content"
        mock_doc.metadata = MagicMock()
        mock_doc.metadata.status_code = 200
        mock_doc.metadata.source_url = "https://example.com/cached"

        mock_app = MagicMock()
        mock_app.scrape.return_value = mock_doc

        url = "https://example.com/cached"

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            first = await execute({"url": url})
            second = await execute({"url": url})

        # SDK must have been called exactly once across both execute() calls
        assert mock_app.scrape.call_count == 1
        assert "error" not in first
        assert second.get("cached") is True

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"})
    async def test_expired_cache_calls_sdk_again(self):
        """When cached entry is past TTL, SDK is called again."""
        import time

        from src.tools import firecrawl_scrape

        firecrawl_scrape._cache.clear()

        mock_doc = MagicMock()
        mock_doc.markdown = "# Fresh Content"
        mock_doc.metadata = MagicMock()
        mock_doc.metadata.status_code = 200
        mock_doc.metadata.source_url = "https://example.com/ttl"

        mock_app = MagicMock()
        mock_app.scrape.return_value = mock_doc

        url = "https://example.com/ttl"

        with patch("src.tools.firecrawl_scrape.firecrawl.FirecrawlApp", return_value=mock_app):
            await execute({"url": url})

            # Manually expire the cache entry
            old_time = time.monotonic() - firecrawl_scrape._CACHE_TTL - 1
            firecrawl_scrape._cache[url] = (old_time, firecrawl_scrape._cache[url][1])

            result = await execute({"url": url})

        assert mock_app.scrape.call_count == 2
        assert result.get("cached") is not True
