"""Tests for Compactor."""

from unittest.mock import AsyncMock, patch

import pytest
from agent.src.runtime.compactor import Compactor, _build_summary_message, estimate_tokens


def _make_messages(count, content_size=100):
    msgs = []
    for i in range(count):
        if i % 2 == 0:
            msgs.append({"role": "user", "content": "x" * content_size})
        else:
            msgs.append(
                {"role": "assistant", "content": [{"type": "text", "text": "y" * content_size}]}
            )
    return msgs


def test_estimate_tokens():
    assert estimate_tokens([{"role": "user", "content": "hello"}]) > 0


@pytest.mark.asyncio
async def test_no_compaction_under_threshold():
    c = Compactor(max_tokens=100_000, preserve_recent=4)
    msgs = _make_messages(4, 50)
    assert await c.maybe_compact(msgs) == msgs


@pytest.mark.asyncio
async def test_compaction_preserves_recent():
    c = Compactor(max_tokens=100, preserve_recent=4)
    msgs = _make_messages(10, 200)
    with patch.object(c, "_summarize", new_callable=AsyncMock) as mock:
        mock.return_value = "Summary of earlier conversation."
        result = await c.maybe_compact(msgs)
    assert len(result) == 5
    assert result[0]["role"] == "user"
    assert "Summary" in result[0]["content"]
    assert result[1:] == msgs[-4:]


@pytest.mark.asyncio
async def test_compaction_calls_summarize():
    c = Compactor(max_tokens=100, preserve_recent=2)
    msgs = _make_messages(6, 200)
    with patch.object(c, "_summarize", new_callable=AsyncMock) as mock:
        mock.return_value = "Summarized."
        await c.maybe_compact(msgs)
    older = mock.call_args[0][0]
    assert len(older) == 4


def test_summary_message_format():
    msg = _build_summary_message("User researched EPC for Sunrise Solar.")
    assert msg["role"] == "user"
    assert "Summary of earlier messages" in msg["content"]
    assert "Sunrise Solar" in msg["content"]
