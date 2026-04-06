"""Tests for summarization-based context compaction."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from agent.src.runtime.compactor import Compactor, estimate_tokens


def _make_messages(count: int, content_size: int = 100) -> list[dict]:
    """Generate synthetic messages with predictable token estimates."""
    messages = []
    for i in range(count):
        if i % 2 == 0:
            messages.append({"role": "user", "content": "x" * content_size})
        else:
            messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": "y" * content_size}],
            })
    return messages


def test_estimate_tokens():
    messages = [{"role": "user", "content": "hello world"}]
    tokens = estimate_tokens(messages)
    # Rough estimate: ~4 chars per token
    assert tokens > 0
    assert isinstance(tokens, int)


@pytest.mark.asyncio
async def test_no_compaction_under_threshold():
    compactor = Compactor(max_tokens=100_000, preserve_recent=4)
    messages = _make_messages(4, content_size=50)  # small
    result = await compactor.maybe_compact(messages)
    assert result == messages  # unchanged


@pytest.mark.asyncio
async def test_compaction_preserves_recent_messages():
    compactor = Compactor(max_tokens=100, preserve_recent=4)  # very low threshold

    messages = _make_messages(10, content_size=200)

    with patch.object(compactor, "_summarize", new_callable=AsyncMock) as mock_summarize:
        mock_summarize.return_value = "Summary of earlier conversation."
        result = await compactor.maybe_compact(messages)

    # Should have: 1 summary message + last 4 messages
    assert len(result) == 5
    assert result[0]["role"] == "user"
    assert "Summary of earlier conversation" in result[0]["content"]
    # Last 4 messages preserved verbatim
    assert result[1:] == messages[-4:]


@pytest.mark.asyncio
async def test_compaction_calls_summarize_with_older_messages():
    compactor = Compactor(max_tokens=100, preserve_recent=2)

    messages = _make_messages(6, content_size=200)

    with patch.object(compactor, "_summarize", new_callable=AsyncMock) as mock_summarize:
        mock_summarize.return_value = "Summarized."
        await compactor.maybe_compact(messages)

    # _summarize should receive the older messages (first 4)
    call_args = mock_summarize.call_args
    older_messages = call_args[0][0]
    assert len(older_messages) == 4


@pytest.mark.asyncio
async def test_summary_merging():
    """When compacting already-compacted messages, merge summaries."""
    compactor = Compactor(max_tokens=100, preserve_recent=2)

    # First message is an existing summary
    messages = [
        {"role": "user", "content": "[Compacted summary]\nPrior summary: User asked about solar projects."},
        {"role": "assistant", "content": [{"type": "text", "text": "y" * 200}]},
        {"role": "user", "content": "x" * 200},
        {"role": "assistant", "content": [{"type": "text", "text": "y" * 200}]},
        {"role": "user", "content": "x" * 200},
        {"role": "assistant", "content": [{"type": "text", "text": "y" * 200}]},
    ]

    with patch.object(compactor, "_summarize", new_callable=AsyncMock) as mock_summarize:
        mock_summarize.return_value = "Merged summary."
        result = await compactor.maybe_compact(messages)

    # The older messages include the summary message
    assert len(result) == 3  # 1 summary + 2 recent


def test_summary_message_format():
    from agent.src.runtime.compactor import _build_summary_message
    msg = _build_summary_message("User researched EPC for Sunrise Solar.")
    assert msg["role"] == "user"
    assert "Summary of earlier messages" in msg["content"]
    assert "Sunrise Solar" in msg["content"]
