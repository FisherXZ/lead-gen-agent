"""Tests for context compaction — replacing old large tool outputs with stubs."""

from __future__ import annotations

import copy
import json

from src.compaction import (
    KEEP_RECENT_TURNS,
    MAX_CONTEXT_CHARS,
    _compact_tool_result,
    compact_messages,
    estimate_context_size,
)

# ---------------------------------------------------------------------------
# Helpers to build api_messages
# ---------------------------------------------------------------------------


def _big_json(n_items: int = 50) -> str:
    """Return a large JSON string with a list of items."""
    items = [{"id": f"proj-{i}", "name": f"Project {i}", "data": "x" * 200} for i in range(n_items)]
    return json.dumps({"projects": items, "count": n_items})


def _small_json() -> str:
    """Return a small JSON string well under the threshold."""
    return json.dumps({"result": "ok", "count": 1})


def _make_assistant_msg(tool_calls: list[tuple[str, str]]) -> dict:
    """Build an assistant message with tool_use content blocks (as dicts).

    tool_calls: list of (tool_use_id, tool_name)
    """
    content = []
    for tid, tname in tool_calls:
        content.append(
            {
                "type": "tool_use",
                "id": tid,
                "name": tname,
                "input": {},
            }
        )
    return {"role": "assistant", "content": content}


def _make_user_tool_result_msg(results: list[tuple[str, str]]) -> dict:
    """Build a user message with tool_result blocks.

    results: list of (tool_use_id, content_json_string)
    """
    content = []
    for tid, content_str in results:
        content.append(
            {
                "type": "tool_result",
                "tool_use_id": tid,
                "content": content_str,
            }
        )
    return {"role": "user", "content": content}


def _make_text_msg(role: str, text: str) -> dict:
    return {"role": role, "content": text}


def _build_conversation(n_tool_turns: int, big: bool = True) -> list[dict]:
    """Build a conversation with an initial user text, then n_tool_turns of
    (assistant tool_use + user tool_result) pairs, then a final assistant text.
    """
    msgs = [_make_text_msg("user", "Research solar EPC contractors in Texas")]
    content_fn = _big_json if big else _small_json
    for i in range(n_tool_turns):
        tid = f"tc-{i}"
        msgs.append(_make_assistant_msg([(tid, "search_projects")]))
        msgs.append(_make_user_tool_result_msg([(tid, content_fn())]))
    msgs.append(_make_text_msg("assistant", "Here are my findings."))
    return msgs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEstimateContextSize:
    def test_sums_json_lengths(self):
        msgs = [{"role": "user", "content": "hello"}]
        size = estimate_context_size(msgs)
        assert size == len(json.dumps(msgs[0]))

    def test_empty_list(self):
        assert estimate_context_size([]) == 0


class TestNoCompactionUnderLimit:
    def test_short_messages_unchanged(self):
        """Messages under max_context_chars are returned as-is (same object)."""
        msgs = [
            _make_text_msg("user", "hello"),
            _make_text_msg("assistant", "hi there"),
        ]
        result = compact_messages(msgs, max_context_chars=MAX_CONTEXT_CHARS)
        # Should be the same object since no compaction needed
        assert result is msgs

    def test_small_tool_results_under_limit(self):
        """Even with tool results, if total size < max, no compaction."""
        msgs = _build_conversation(3, big=False)
        result = compact_messages(msgs, max_context_chars=MAX_CONTEXT_CHARS)
        assert result is msgs


class TestCompactsOldToolResults:
    def test_old_turns_get_compacted(self):
        """With 10 tool turns and big outputs, old ones should be compacted."""
        msgs = _build_conversation(10, big=True)
        result = compact_messages(
            msgs,
            max_context_chars=1,  # Force compaction
            keep_recent_turns=KEEP_RECENT_TURNS,
        )

        # Count compacted vs non-compacted tool results
        compacted_count = 0
        non_compacted_count = 0
        for msg in result:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if item.get("type") == "tool_result":
                        try:
                            parsed = json.loads(item["content"])
                            if parsed.get("_compacted"):
                                compacted_count += 1
                            else:
                                non_compacted_count += 1
                        except (json.JSONDecodeError, TypeError):
                            non_compacted_count += 1

        # 10 turns total, KEEP_RECENT_TURNS (6) protected => 4 compacted
        assert compacted_count == 4
        assert non_compacted_count == 6


class TestPreservesRecent3Turns:
    def test_last_3_turns_byte_identical(self):
        """The last 3 tool turn pairs should be byte-identical to input."""
        msgs = _build_conversation(10, big=True)
        original = copy.deepcopy(msgs)
        result = compact_messages(
            msgs,
            max_context_chars=1,
            keep_recent_turns=3,
        )

        # Find all user tool_result messages
        original_tool_user_msgs = [
            (i, m)
            for i, m in enumerate(original)
            if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        result_tool_user_msgs = [
            (i, m)
            for i, m in enumerate(result)
            if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]

        # Last 3 should be identical
        for orig, res in zip(
            original_tool_user_msgs[-3:], result_tool_user_msgs[-3:], strict=False
        ):
            assert json.dumps(orig[1]) == json.dumps(res[1])


class TestPreservesTextMessages:
    def test_text_messages_never_modified(self):
        """Plain text user and assistant messages should never be changed."""
        msgs = _build_conversation(10, big=True)
        original = copy.deepcopy(msgs)
        result = compact_messages(msgs, max_context_chars=1)

        # Check text messages are identical
        for orig, res in zip(original, result, strict=False):
            if isinstance(orig.get("content"), str):
                assert orig["content"] == res["content"]
                assert orig["role"] == res["role"]


class TestStubFormat:
    def test_stub_has_required_keys(self):
        """Compacted stub should have _compacted, tool, summary, result_count."""
        big_content = _big_json(50)
        stub_str = _compact_tool_result(big_content, "search_projects")
        stub = json.loads(stub_str)

        assert stub["_compacted"] is True
        assert stub["tool"] == "search_projects"
        assert "summary" in stub
        assert len(stub["summary"]) <= 124  # 120 + "..."
        assert isinstance(stub["result_count"], int)

    def test_result_count_from_list(self):
        """result_count should reflect list length in the JSON."""
        content = json.dumps({"projects": [{"id": i} for i in range(25)]})
        stub = json.loads(_compact_tool_result(content, "search_projects"))
        assert stub["result_count"] == 25

    def test_result_count_no_list(self):
        """result_count should be 1 when no list values exist."""
        content = json.dumps({"status": "ok", "message": "done" * 200})
        stub = json.loads(_compact_tool_result(content, "get_status"))
        assert stub["result_count"] == 1


class TestSmallOutputsUntouched:
    def test_under_threshold_not_compacted(self):
        """Tool results under 500 chars should not be compacted even in old turns."""
        msgs = _build_conversation(10, big=False)
        result = compact_messages(
            msgs,
            max_context_chars=1,  # Force compaction logic to run
            keep_recent_turns=3,
        )

        # All tool results should still be the original small JSON
        for msg in result:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if item.get("type") == "tool_result":
                        parsed = json.loads(item["content"])
                        assert "_compacted" not in parsed


class TestDoesNotMutateInput:
    def test_original_list_unchanged(self):
        """The original api_messages list should not be mutated."""
        msgs = _build_conversation(10, big=True)
        original_json = json.dumps(msgs, default=str)

        compact_messages(msgs, max_context_chars=1)

        assert json.dumps(msgs, default=str) == original_json


class TestAlreadyCompactedIdempotent:
    def test_running_twice_produces_same_result(self):
        """Compacting an already-compacted conversation should be idempotent."""
        msgs = _build_conversation(10, big=True)

        result1 = compact_messages(msgs, max_context_chars=1)
        result2 = compact_messages(result1, max_context_chars=1)

        assert json.dumps(result1, default=str) == json.dumps(result2, default=str)


class TestNonJsonContent:
    def test_non_json_tool_result_large(self):
        """Non-JSON content over threshold should be truncated with _compacted flag."""
        large_text = "This is plain text output from a tool. " * 50  # ~2000 chars
        msgs = [
            _make_text_msg("user", "do something"),
            _make_assistant_msg([("tc-0", "fetch_page")]),
            _make_user_tool_result_msg([("tc-0", large_text)]),
            # Add a recent turn so the old one is unprotected
            _make_assistant_msg([("tc-1", "fetch_page")]),
            _make_user_tool_result_msg([("tc-1", large_text)]),
            _make_assistant_msg([("tc-2", "fetch_page")]),
            _make_user_tool_result_msg([("tc-2", large_text)]),
            _make_assistant_msg([("tc-3", "fetch_page")]),
            _make_user_tool_result_msg([("tc-3", large_text)]),
        ]
        result = compact_messages(msgs, max_context_chars=1, keep_recent_turns=3)

        # First tool result (oldest) should be compacted
        first_tool_msg = result[2]
        content_str = first_tool_msg["content"][0]["content"]
        parsed = json.loads(content_str)
        assert parsed["_compacted"] is True
        assert parsed["tool"] == "fetch_page"
        assert len(parsed["summary"]) <= 204  # 200 + "..."

    def test_non_json_tool_result_small(self):
        """Non-JSON content under threshold should be left as-is."""
        small_text = "OK done"
        msgs = [
            _make_text_msg("user", "do something"),
            _make_assistant_msg([("tc-0", "fetch_page")]),
            _make_user_tool_result_msg([("tc-0", small_text)]),
        ]
        result = compact_messages(msgs, max_context_chars=1, keep_recent_turns=0)

        # Small content should be unchanged
        content_str = result[2]["content"][0]["content"]
        assert content_str == small_text


class TestContentBlockObjects:
    def test_handles_anthropic_content_block_objects(self):
        """Tool name lookup works with object-style content blocks (not dicts)."""
        from unittest.mock import MagicMock

        # Build an assistant message with MagicMock content blocks (like Anthropic SDK)
        block = MagicMock()
        block.type = "tool_use"
        block.id = "tc-0"
        block.name = "web_search"

        msgs = [
            _make_text_msg("user", "search for something"),
            {"role": "assistant", "content": [block]},
            _make_user_tool_result_msg([("tc-0", _big_json(20))]),
            # Add recent turns to leave oldest unprotected
            _make_assistant_msg([("tc-1", "search_projects")]),
            _make_user_tool_result_msg([("tc-1", _big_json(20))]),
            _make_assistant_msg([("tc-2", "search_projects")]),
            _make_user_tool_result_msg([("tc-2", _big_json(20))]),
            _make_assistant_msg([("tc-3", "search_projects")]),
            _make_user_tool_result_msg([("tc-3", _big_json(20))]),
        ]
        result = compact_messages(msgs, max_context_chars=1, keep_recent_turns=3)

        # Oldest turn should be compacted with correct tool name
        compacted_content = result[2]["content"][0]["content"]
        parsed = json.loads(compacted_content)
        assert parsed["_compacted"] is True
        assert parsed["tool"] == "web_search"


class TestEdgeCases:
    def test_empty_messages(self):
        """Empty message list returns as-is."""
        result = compact_messages([])
        assert result == []

    def test_no_tool_turns(self):
        """Conversation with no tool turns returns as-is when over limit."""
        msgs = [_make_text_msg("user", "x" * 200_000)]
        result = compact_messages(msgs, max_context_chars=1)
        # No tool turns to compact, so messages returned unchanged (deep copy)
        assert result[0]["content"] == msgs[0]["content"]

    def test_initial_user_message_preserved(self):
        """The first user text message is never modified."""
        msgs = _build_conversation(10, big=True)
        result = compact_messages(msgs, max_context_chars=1)
        assert result[0] == msgs[0]
