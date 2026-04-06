"""Tests for the CachedTool helper in _base.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


def test_make_cache_key_deterministic():
    from src.tools._base import _make_cache_key

    key1 = _make_cache_key("search_osha", {"employer": "SOLV", "state": "TX"})
    key2 = _make_cache_key("search_osha", {"employer": "SOLV", "state": "TX"})
    key3 = _make_cache_key("search_osha", {"employer": "SOLV", "state": "CA"})

    assert key1 == key2  # Same input → same key
    assert key1 != key3  # Different input → different key
    assert key1.startswith("search_osha:")


def test_make_cache_key_different_tools():
    from src.tools._base import _make_cache_key

    key1 = _make_cache_key("search_osha", {"query": "test"})
    key2 = _make_cache_key("search_sec_edgar", {"query": "test"})

    assert key1 != key2  # Different tools → different keys


def test_cache_get_returns_none_on_miss():
    """When no cache entry exists, return None."""
    from src.tools._base import cache_get

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = []
    sel = mock_client.table.return_value.select.return_value
    sel.eq.return_value.limit.return_value.execute.return_value = mock_resp

    with patch("src.db.get_client", return_value=mock_client):
        result = cache_get("test_tool", {"key": "value"})

    assert result is None


def test_cache_get_returns_data_on_hit():
    """When cache entry exists and not expired, return data."""
    from src.tools._base import cache_get

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [{"data": {"results": ["cached"]}, "expires_at": future}]
    sel = mock_client.table.return_value.select.return_value
    sel.eq.return_value.limit.return_value.execute.return_value = mock_resp

    with patch("src.db.get_client", return_value=mock_client):
        result = cache_get("test_tool", {"key": "value"})

    assert result == {"results": ["cached"]}


def test_cache_get_returns_none_on_expired():
    """When cache entry exists but is expired, return None and clean up."""
    from src.tools._base import cache_get

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [{"data": {"results": ["old"]}, "expires_at": past}]
    sel = mock_client.table.return_value.select.return_value
    sel.eq.return_value.limit.return_value.execute.return_value = mock_resp

    with patch("src.db.get_client", return_value=mock_client):
        result = cache_get("test_tool", {"key": "value"})

    assert result is None
    # Should have called delete for cleanup
    mock_client.table.return_value.delete.assert_called()


def test_cache_get_falls_back_to_memory_on_db_error():
    """When DB is unreachable, fall back to in-memory cache."""
    import time

    from src.tools._base import _make_cache_key, _memory_cache, cache_get

    # Seed memory cache
    key = _make_cache_key("test_tool", {"key": "fallback"})
    _memory_cache[key] = (time.time(), {"results": ["in-memory"]})

    with patch("src.db.get_client", side_effect=Exception("DB down")):
        result = cache_get("test_tool", {"key": "fallback"})

    assert result == {"results": ["in-memory"]}

    # Clean up
    _memory_cache.pop(key, None)


def test_cache_set_writes_to_db():
    from src.tools._base import cache_set

    mock_client = MagicMock()

    with patch("src.db.get_client", return_value=mock_client):
        cache_set("test_tool", {"key": "value"}, {"results": ["new"]}, ttl_hours=24)

    mock_client.table.return_value.upsert.assert_called_once()
    upsert_data = mock_client.table.return_value.upsert.call_args[0][0]
    assert upsert_data["tool_name"] == "test_tool"
    assert upsert_data["data"] == {"results": ["new"]}


def test_cache_set_falls_back_to_memory_on_db_error():
    from src.tools._base import _make_cache_key, _memory_cache, cache_set

    key = _make_cache_key("test_tool", {"key": "error-test"})
    _memory_cache.pop(key, None)

    with patch("src.db.get_client", side_effect=Exception("DB down")):
        cache_set("test_tool", {"key": "error-test"}, {"results": ["fallback"]})

    assert key in _memory_cache
    assert _memory_cache[key][1] == {"results": ["fallback"]}

    # Clean up
    _memory_cache.pop(key, None)
