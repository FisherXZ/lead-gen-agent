"""Tests for agent/src/share_sanitizer.py.

The sanitizer is the bouncer at the door of the public share page. It uses
an allow-list so unknown tools fail closed. These tests verify both that
safe content passes through and that unsafe content is stripped.
"""

from __future__ import annotations

from src.share_sanitizer import (
    SHAREABLE_TOOLS,
    _strip_internal_fields,
    _tool_name,
    sanitize_messages,
    sanitize_parts,
)

# ---------------------------------------------------------------------------
# sanitize_parts — allow-list behavior
# ---------------------------------------------------------------------------


class TestSanitizeAllowList:
    def test_text_parts_pass_through(self):
        parts = [{"type": "text", "text": "hello world"}]
        assert sanitize_parts(parts) == parts

    def test_each_shareable_tool_survives(self):
        for tool in SHAREABLE_TOOLS:
            parts = [
                {
                    "type": f"tool-{tool}",
                    "toolName": tool,
                    "input": {"x": 1},
                    "output": {"ok": True},
                }
            ]
            clean = sanitize_parts(parts)
            assert len(clean) == 1, f"{tool} was dropped"
            assert _tool_name(clean[0]) == tool

    def test_unknown_tool_is_dropped(self):
        # Fails closed — new tools added to the system must be explicitly
        # listed in SHAREABLE_TOOLS to appear in shared views.
        parts = [
            {
                "type": "tool-future_mystery_tool",
                "toolName": "future_mystery_tool",
                "input": {},
                "output": {},
            }
        ]
        assert sanitize_parts(parts) == []

    def test_internal_tools_are_dropped(self):
        for internal in [
            "research_scratchpad",
            "remember",
            "recall",
            "query_knowledge_base",
            "approve_discovery",
        ]:
            parts = [
                {
                    "type": f"tool-{internal}",
                    "toolName": internal,
                    "input": {},
                    "output": {"ok": True},
                }
            ]
            assert sanitize_parts(parts) == [], f"{internal} leaked"

    def test_non_tool_non_text_parts_dropped(self):
        parts = [
            {"type": "file", "mediaType": "image/png", "url": "data:image/png;base64,..."},
            {"type": "reasoning", "text": "internal chain of thought"},
            {"type": "step-start"},
            {"type": "source-url", "url": "https://x.com"},
        ]
        assert sanitize_parts(parts) == []

    def test_handles_none_and_empty(self):
        assert sanitize_parts(None) == []
        assert sanitize_parts([]) == []

    def test_skips_non_dict_entries(self):
        parts = [None, "junk", {"type": "text", "text": "ok"}]
        assert sanitize_parts(parts) == [{"type": "text", "text": "ok"}]

    def test_tool_name_inferred_from_type_prefix(self):
        """Some UI messages carry tool name in `type: tool-X` instead of toolName."""
        parts = [
            {
                "type": "tool-web_search",
                "input": {"query": "solar"},
                "output": {"results": []},
            }
        ]
        clean = sanitize_parts(parts)
        assert len(clean) == 1


# ---------------------------------------------------------------------------
# sanitize_parts — field-level stripping
# ---------------------------------------------------------------------------


class TestFieldStripping:
    def test_strips_underscore_prefixed_input_keys(self):
        parts = [
            {
                "type": "tool-web_search",
                "toolName": "web_search",
                "input": {"query": "solar", "_batch_id": "abc", "_internal": 42},
                "output": {"results": []},
            }
        ]
        clean = sanitize_parts(parts)
        assert clean[0]["input"] == {"query": "solar"}

    def test_truncates_error_tracebacks(self):
        traceback_text = (
            "Traceback (most recent call last):\n"
            '  File "tool.py", line 10, in run\n'
            "    raise ValueError('oh no')\n"
            "ValueError: oh no"
        )
        parts = [
            {
                "type": "tool-fetch_page",
                "toolName": "fetch_page",
                "input": {"url": "https://x.com"},
                "output": {"error": traceback_text},
            }
        ]
        clean = sanitize_parts(parts)
        assert clean[0]["output"]["error"] == "An error occurred"

    def test_preserves_short_error_messages(self):
        parts = [
            {
                "type": "tool-fetch_page",
                "toolName": "fetch_page",
                "input": {"url": "https://x.com"},
                "output": {"error": "404 Not Found"},
            }
        ]
        clean = sanitize_parts(parts)
        assert clean[0]["output"]["error"] == "404 Not Found"

    def test_leaves_outputs_without_error_alone(self):
        parts = [
            {
                "type": "tool-search_projects",
                "toolName": "search_projects",
                "input": {"state": "TX"},
                "output": {"projects": [{"id": "p1"}]},
            }
        ]
        clean = sanitize_parts(parts)
        assert clean[0]["output"] == {"projects": [{"id": "p1"}]}

    def test_strip_does_not_mutate_original(self):
        """The sanitizer must not mutate the caller's parts in place."""
        original_input = {"query": "solar", "_batch_id": "abc"}
        parts = [
            {
                "type": "tool-web_search",
                "toolName": "web_search",
                "input": original_input,
                "output": {"results": []},
            }
        ]
        sanitize_parts(parts)
        assert original_input == {"query": "solar", "_batch_id": "abc"}


# ---------------------------------------------------------------------------
# sanitize_messages — envelope shape
# ---------------------------------------------------------------------------


class TestSanitizeMessages:
    def test_preserves_message_envelope(self):
        msgs = [
            {
                "id": "m1",
                "role": "user",
                "content": "find TX solar",
                "parts": [{"type": "text", "text": "find TX solar"}],
                "created_at": "2026-04-15T00:00:00Z",
            }
        ]
        out = sanitize_messages(msgs)
        assert out[0]["id"] == "m1"
        assert out[0]["role"] == "user"
        assert out[0]["content"] == "find TX solar"
        assert out[0]["created_at"] == "2026-04-15T00:00:00Z"

    def test_filters_parts_per_message(self):
        msgs = [
            {
                "id": "m1",
                "role": "assistant",
                "content": "",
                "parts": [
                    {"type": "text", "text": "Here's what I found"},
                    {
                        "type": "tool-research_scratchpad",
                        "toolName": "research_scratchpad",
                        "input": {"key": "notes"},
                        "output": {"ok": True},
                    },
                    {
                        "type": "tool-web_search",
                        "toolName": "web_search",
                        "input": {"query": "x"},
                        "output": {"results": []},
                    },
                ],
                "created_at": "2026-04-15T00:00:01Z",
            }
        ]
        out = sanitize_messages(msgs)
        assert len(out[0]["parts"]) == 2
        kept_types = [p.get("type") for p in out[0]["parts"]]
        assert "text" in kept_types
        assert "tool-web_search" in kept_types

    def test_missing_parts_becomes_empty(self):
        msgs = [{"id": "m1", "role": "user", "content": "hi"}]
        out = sanitize_messages(msgs)
        assert out[0]["parts"] == []

    def test_skips_non_dict_messages(self):
        msgs = [None, "junk", {"id": "m1", "role": "user", "content": "hi", "parts": []}]
        out = sanitize_messages(msgs)
        assert len(out) == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestToolName:
    def test_from_tool_name_field(self):
        assert _tool_name({"toolName": "web_search"}) == "web_search"

    def test_from_type_prefix(self):
        assert _tool_name({"type": "tool-web_search"}) == "web_search"

    def test_tool_name_takes_precedence(self):
        assert _tool_name({"toolName": "web_search", "type": "tool-other"}) == "web_search"

    def test_returns_none_for_non_tool(self):
        assert _tool_name({"type": "text"}) is None


class TestStripInternalFields:
    def test_preserves_non_underscore_keys(self):
        part = {"input": {"query": "x", "limit": 10}}
        out = _strip_internal_fields(part)
        assert out["input"] == {"query": "x", "limit": 10}

    def test_handles_missing_input(self):
        part = {"toolName": "foo"}
        out = _strip_internal_fields(part)
        assert out == {"toolName": "foo"}

    def test_handles_non_dict_input(self):
        part = {"input": "not a dict"}
        out = _strip_internal_fields(part)
        assert out["input"] == "not a dict"
