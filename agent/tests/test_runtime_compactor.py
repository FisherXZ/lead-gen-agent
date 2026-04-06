"""Tests for HeuristicCompactor and its private helpers."""
from __future__ import annotations

import json

import pytest

from runtime.compactor import (
    CONTINUATION_PREAMBLE,
    RECENT_MESSAGES_NOTE,
    HeuristicCompactor,
    _build_continuation_message,
    _detect_existing_summary,
    _estimate_tokens,
    _extract_file_candidates,
    _extract_first_text,
    _format_summary,
    _merge_summaries,
    _summarize_messages,
    _truncate,
)

# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------

def test_truncate_short_string_unchanged():
    assert _truncate("hello", 10) == "hello"


def test_truncate_exact_length_unchanged():
    assert _truncate("hello", 5) == "hello"


def test_truncate_long_string_adds_ellipsis():
    result = _truncate("abcdef", 4)
    assert result == "abcd…"
    assert len(result) == 5  # 4 chars + ellipsis


# ---------------------------------------------------------------------------
# _estimate_tokens
# ---------------------------------------------------------------------------

def test_estimate_tokens_empty():
    assert _estimate_tokens([]) == 0


def test_estimate_tokens_rough_quarter():
    msg = {"role": "user", "content": "x" * 400}
    tokens = _estimate_tokens([msg])
    # json overhead is small; 400 chars content → ~100 tokens
    assert 90 <= tokens <= 130


# ---------------------------------------------------------------------------
# _extract_file_candidates
# ---------------------------------------------------------------------------

def test_extract_file_candidates_python_and_sql():
    text = "Updated agent/src/runtime/compactor.py and migrations/005_init.sql today."
    files = _extract_file_candidates(text)
    assert "agent/src/runtime/compactor.py" in files
    assert "migrations/005_init.sql" in files


def test_extract_file_candidates_ignores_txt():
    files = _extract_file_candidates("see notes/readme.txt for details")
    assert not any(".txt" in f for f in files)


def test_extract_file_candidates_deduplicates():
    text = "agent/src/foo.py agent/src/foo.py agent/src/bar.py"
    files = _extract_file_candidates(text)
    assert files.count("agent/src/foo.py") == 1


def test_extract_file_candidates_strips_punctuation():
    files = _extract_file_candidates("see (agent/src/foo.py) for details.")
    assert "agent/src/foo.py" in files


def test_extract_file_candidates_capped_at_eight():
    parts = [f"a/b/f{i}.py" for i in range(20)]
    files = _extract_file_candidates(" ".join(parts))
    assert len(files) <= 8


# ---------------------------------------------------------------------------
# _extract_first_text
# ---------------------------------------------------------------------------

def test_extract_first_text_string_content():
    msg = {"role": "user", "content": "hello world"}
    assert _extract_first_text(msg) == "hello world"


def test_extract_first_text_list_content():
    msg = {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "name": "search", "id": "1", "input": {}},
            {"type": "text", "text": "found it"},
        ],
    }
    assert _extract_first_text(msg) == "found it"


def test_extract_first_text_empty_returns_none():
    assert _extract_first_text({"role": "user", "content": "  "}) is None
    assert _extract_first_text({"role": "user", "content": []}) is None


# ---------------------------------------------------------------------------
# _detect_existing_summary
# ---------------------------------------------------------------------------

def _make_continuation_msg(summary: str) -> dict:
    return _build_continuation_message(summary)


def test_detect_existing_summary_returns_none_for_regular_message():
    msg = {"role": "user", "content": "hello"}
    assert _detect_existing_summary(msg) is None


def test_detect_existing_summary_returns_none_for_assistant():
    msg = _make_continuation_msg("<summary>stuff</summary>")
    msg["role"] = "assistant"
    assert _detect_existing_summary(msg) is None


def test_detect_existing_summary_roundtrip():
    raw_summary = "<summary>\nConversation summary:\n- Scope: 4 messages.\n</summary>"
    msg = _make_continuation_msg(raw_summary)
    result = _detect_existing_summary(msg)
    assert result is not None
    assert "Scope: 4 messages." in result


# ---------------------------------------------------------------------------
# _summarize_messages
# ---------------------------------------------------------------------------

def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant_text(text: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def _assistant_tool_use(name: str) -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "1", "name": name, "input": {"q": "test"}}],
    }


def _tool_result(content: str) -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "1", "content": content}],
    }


def test_summarize_messages_scope_line():
    messages = [_user("find EPCs for ERCOT"), _assistant_text("searching now")]
    summary = _summarize_messages(messages)
    assert "Scope: 2 earlier messages compacted" in summary
    assert "user=1" in summary
    assert "assistant=1" in summary


def test_summarize_messages_includes_tool_names():
    messages = [_assistant_tool_use("web_search"), _tool_result("some results")]
    summary = _summarize_messages(messages)
    assert "web_search" in summary


def test_summarize_messages_recent_user_requests():
    messages = [
        _user("first request"),
        _assistant_text("ok"),
        _user("second request"),
        _assistant_text("done"),
    ]
    summary = _summarize_messages(messages)
    assert "second request" in summary


def test_summarize_messages_pending_work_keywords():
    messages = [
        _user("research EPCs"),
        _assistant_text("Next: push accepted projects to CRM and follow up on remaining queue."),
    ]
    summary = _summarize_messages(messages)
    assert "Pending work" in summary


def test_summarize_messages_epc_keyword_triggers_pending():
    messages = [
        _assistant_text("Found epc contractor SunPower for this project."),
    ]
    summary = _summarize_messages(messages)
    assert "Pending work" in summary


def test_summarize_messages_key_files():
    messages = [_user("update agent/src/runtime/compactor.py and migrations/007.sql")]
    summary = _summarize_messages(messages)
    assert "agent/src/runtime/compactor.py" in summary
    assert "migrations/007.sql" in summary


def test_summarize_messages_timeline_present():
    messages = [_user("hello"), _assistant_text("world")]
    summary = _summarize_messages(messages)
    assert "Key timeline" in summary
    assert "user:" in summary
    assert "assistant:" in summary


def test_summarize_messages_wrapped_in_xml():
    summary = _summarize_messages([_user("test")])
    assert summary.startswith("<summary>")
    assert summary.endswith("</summary>")


# ---------------------------------------------------------------------------
# _merge_summaries
# ---------------------------------------------------------------------------

def test_merge_summaries_contains_both_sections():
    first = _summarize_messages([_user("first request"), _assistant_text("first response")])
    second = _summarize_messages([_user("second request"), _assistant_text("second response")])
    merged = _merge_summaries(first, second)
    assert "Previously compacted context" in merged
    assert "Newly compacted context" in merged


def test_merge_summaries_drops_timeline_from_prior():
    first = _summarize_messages([_user("step one"), _assistant_text("done one")])
    second = _summarize_messages([_user("step two"), _assistant_text("done two")])
    merged = _merge_summaries(first, second)
    # Timeline should come from new only (not duplicated from prior highlights)
    assert "Key timeline" in merged
    timeline_count = merged.count("Key timeline")
    assert timeline_count == 1


# ---------------------------------------------------------------------------
# _format_summary
# ---------------------------------------------------------------------------

def test_format_summary_strips_xml_tags():
    result = _format_summary("<summary>\nConversation summary:\n- Scope: 2.\n</summary>")
    assert "<summary>" not in result
    assert "</summary>" not in result
    assert "Summary:" in result
    assert "Scope: 2." in result


def test_format_summary_passthrough_if_no_tags():
    result = _format_summary("plain text summary")
    assert result == "plain text summary"


# ---------------------------------------------------------------------------
# _build_continuation_message
# ---------------------------------------------------------------------------

def test_build_continuation_message_structure():
    msg = _build_continuation_message("<summary>test summary</summary>")
    assert msg["role"] == "user"
    assert CONTINUATION_PREAMBLE in msg["content"]
    assert RECENT_MESSAGES_NOTE in msg["content"]
    assert "Resume directly" in msg["content"]
    assert "test summary" in msg["content"]


# ---------------------------------------------------------------------------
# HeuristicCompactor — end-to-end
# ---------------------------------------------------------------------------

def _make_messages(n: int) -> list[dict]:
    """Make n alternating user/assistant messages with enough content to exceed threshold."""
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"message {i} " + ("x" * 500)})
    return msgs


@pytest.mark.asyncio
async def test_maybe_compact_under_threshold_returns_same_list():
    compactor = HeuristicCompactor(max_tokens=10_000_000, preserve_recent=4)
    msgs = _make_messages(6)
    result = await compactor.maybe_compact(msgs)
    assert result is msgs  # same object, no copy


@pytest.mark.asyncio
async def test_maybe_compact_too_few_messages_returns_same_list():
    compactor = HeuristicCompactor(max_tokens=1, preserve_recent=10)
    msgs = _make_messages(4)
    result = await compactor.maybe_compact(msgs)
    assert result is msgs


@pytest.mark.asyncio
async def test_maybe_compact_injects_summary_and_preserves_recent():
    compactor = HeuristicCompactor(max_tokens=1, preserve_recent=2)
    msgs = _make_messages(6)
    result = await compactor.maybe_compact(msgs)
    # First message is synthetic summary
    assert result[0]["role"] == "user"
    assert CONTINUATION_PREAMBLE in result[0]["content"]
    # Last 2 messages are preserved verbatim
    assert result[1] == msgs[-2]
    assert result[2] == msgs[-1]
    assert len(result) == 3


@pytest.mark.asyncio
async def test_maybe_compact_total_shorter_than_original():
    compactor = HeuristicCompactor(max_tokens=1, preserve_recent=2)
    msgs = _make_messages(10)
    result = await compactor.maybe_compact(msgs)
    original_size = sum(len(json.dumps(m)) for m in msgs)
    result_size = sum(len(json.dumps(m)) for m in result)
    assert result_size < original_size


@pytest.mark.asyncio
async def test_maybe_compact_repeat_compaction_merges():
    compactor = HeuristicCompactor(max_tokens=1, preserve_recent=2)
    msgs = _make_messages(6)
    # First compaction
    first = await compactor.maybe_compact(msgs)
    # Add more messages and compact again
    extended = first + _make_messages(4)
    second = await compactor.maybe_compact(extended)
    assert "Previously compacted context" in second[0]["content"]
    assert "Newly compacted context" in second[0]["content"]
