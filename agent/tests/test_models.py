"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import (
    AgentResult,
    BatchDiscoverRequest,
    ChatMessage,
    ChatMessagePart,
    DiscoverRequest,
    EpcSource,
    ReviewRequest,
    build_anthropic_messages,
)

# -- DiscoverRequest ----------------------------------------------------------


class TestDiscoverRequest:
    def test_valid(self):
        req = DiscoverRequest(project_id="proj-001")
        assert req.project_id == "proj-001"

    def test_missing_project_id(self):
        with pytest.raises(ValidationError):
            DiscoverRequest()


# -- BatchDiscoverRequest -----------------------------------------------------


class TestBatchDiscoverRequest:
    def test_valid_single(self):
        req = BatchDiscoverRequest(project_ids=["proj-001"])
        assert req.project_ids == ["proj-001"]

    def test_valid_multiple(self):
        ids = ["proj-001", "proj-002", "proj-003"]
        req = BatchDiscoverRequest(project_ids=ids)
        assert len(req.project_ids) == 3

    def test_empty_list_is_valid_schema(self):
        # Schema allows it; endpoint validates non-empty
        req = BatchDiscoverRequest(project_ids=[])
        assert req.project_ids == []

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            BatchDiscoverRequest()


# -- ReviewRequest ------------------------------------------------------------


class TestReviewRequest:
    def test_accepted(self):
        req = ReviewRequest(action="accepted")
        assert req.action == "accepted"

    def test_rejected(self):
        req = ReviewRequest(action="rejected")
        assert req.action == "rejected"

    def test_arbitrary_string_allowed_by_schema(self):
        # The model is a plain str; endpoint validates valid values
        req = ReviewRequest(action="invalid")
        assert req.action == "invalid"


# -- EpcSource ----------------------------------------------------------------


class TestEpcSource:
    def test_required_fields(self):
        src = EpcSource(channel="trade_publication", excerpt="Some text")
        assert src.channel == "trade_publication"
        assert src.excerpt == "Some text"
        assert src.reliability == "medium"
        assert src.publication is None
        assert src.date is None
        assert src.url is None

    def test_all_fields(self):
        src = EpcSource(
            channel="news_article",
            publication="Reuters",
            date="2025-06-01",
            url="https://example.com",
            excerpt="EPC contract awarded",
            reliability="high",
        )
        assert src.publication == "Reuters"
        assert src.reliability == "high"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            EpcSource(channel="news_article")  # missing excerpt


# -- AgentResult --------------------------------------------------------------


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult()
        assert r.epc_contractor is None
        assert r.confidence == "unknown"
        assert r.sources == []
        assert r.reasoning == ""
        assert r.related_leads == []
        assert r.searches_performed == []

    def test_full(self):
        src = EpcSource(channel="web_search", excerpt="found it")
        r = AgentResult(
            epc_contractor="Blattner Energy",
            confidence="confirmed",
            sources=[src],
            reasoning="Two independent sources",
            related_leads=[{"developer": "X", "epc": "Y"}],
            searches_performed=["query 1", "query 2"],
        )
        assert r.epc_contractor == "Blattner Energy"
        assert len(r.sources) == 1
        assert r.sources[0].channel == "web_search"

    def test_model_dump_sources(self):
        src = EpcSource(channel="permit_filing", excerpt="permit text")
        r = AgentResult(sources=[src])
        dumped = r.sources[0].model_dump()
        assert dumped["channel"] == "permit_filing"
        assert dumped["reliability"] == "medium"


# -- build_anthropic_messages ------------------------------------------------
#
# Regression guard for the turn-to-turn memory bug documented in
# docs/superpowers/specs/2026-04-06-agent-memory-persistence-issues.md.
# Without proper tool_use/tool_result pairing, Claude forgets tool calls
# across chat turns and re-runs searches from scratch.


def _user(text: str) -> ChatMessage:
    return ChatMessage(
        role="user",
        parts=[ChatMessagePart(type="text", text=text)],
    )


def _assistant_text(text: str) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        parts=[ChatMessagePart(type="text", text=text)],
    )


class TestBuildAnthropicMessages:
    def test_plain_text_roundtrip(self):
        """User → assistant text → user: no tools, pure text."""
        msgs = [
            _user("hi"),
            _assistant_text("hello"),
            _user("what's up"),
        ]
        out = build_anthropic_messages(msgs)

        assert len(out) == 3
        assert out[0] == {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        assert out[1] == {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
        }
        assert out[2] == {
            "role": "user",
            "content": [{"type": "text", "text": "what's up"}],
        }

    def test_single_tool_invocation_pairs_tool_use_and_tool_result(self):
        """Assistant with one tool-invocation splits into tool_use + next-user tool_result."""
        assistant = ChatMessage(
            role="assistant",
            parts=[
                ChatMessagePart(type="text", text="Looking it up."),
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_01",
                    toolName="search_projects",
                    input={"state": "TX"},
                    output={"count": 3},
                    state="result",
                ),
            ],
        )
        msgs = [_user("find projects"), assistant, _user("thanks")]

        out = build_anthropic_messages(msgs)

        # user → assistant (text + tool_use) → user (tool_result + new text)
        assert len(out) == 3

        assert out[1] == {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Looking it up."},
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "search_projects",
                    "input": {"state": "TX"},
                },
            ],
        }

        # tool_result is prepended to the next user message
        assert out[2]["role"] == "user"
        assert out[2]["content"][0] == {
            "type": "tool_result",
            "tool_use_id": "toolu_01",
            "content": '{"count": 3}',
        }
        assert out[2]["content"][1] == {"type": "text", "text": "thanks"}

    def test_multiple_tool_invocations_in_one_turn(self):
        """All tool_use blocks emitted in order; all tool_results prepended to next user."""
        assistant = ChatMessage(
            role="assistant",
            parts=[
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_A",
                    toolName="search_exa_people",
                    input={"query": "Rosendin EPC"},
                    output="exa result text",
                    state="result",
                ),
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_B",
                    toolName="search_linkedin",
                    input={"company": "Rosendin"},
                    output={"results": []},
                    state="result",
                ),
                ChatMessagePart(type="text", text="Here are the candidates."),
            ],
        )
        msgs = [_user("find contacts"), assistant, _user("now enrich them")]

        out = build_anthropic_messages(msgs)

        # Assistant carries tool_use A + tool_use B + trailing text, in order
        assistant_content = out[1]["content"]
        assert [b["type"] for b in assistant_content] == ["tool_use", "tool_use", "text"]
        assert assistant_content[0]["id"] == "toolu_A"
        assert assistant_content[1]["id"] == "toolu_B"

        # Next user message starts with both tool_results in order, then the new text
        next_user = out[2]["content"]
        assert next_user[0] == {
            "type": "tool_result",
            "tool_use_id": "toolu_A",
            "content": "exa result text",
        }
        assert next_user[1] == {
            "type": "tool_result",
            "tool_use_id": "toolu_B",
            "content": '{"results": []}',
        }
        assert next_user[2] == {"type": "text", "text": "now enrich them"}

    def test_partial_tool_invocation_is_dropped(self):
        """state=partial-call with no output: omit entirely (no orphan tool_use)."""
        assistant = ChatMessage(
            role="assistant",
            parts=[
                ChatMessagePart(type="text", text="Searching…"),
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_partial",
                    toolName="search_projects",
                    input={"state": "TX"},
                    output=None,
                    state="partial-call",
                ),
            ],
        )
        msgs = [_user("q"), assistant, _user("follow up")]

        out = build_anthropic_messages(msgs)

        # Assistant has only the text block, no tool_use
        assert out[1]["content"] == [{"type": "text", "text": "Searching…"}]
        # Next user message has no tool_result, just the new text
        assert out[2] == {
            "role": "user",
            "content": [{"type": "text", "text": "follow up"}],
        }

    def test_dict_output_is_json_stringified(self):
        """tool_result.content must be a string — dict outputs get json.dumps'd."""
        assistant = ChatMessage(
            role="assistant",
            parts=[
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_x",
                    toolName="find_contacts",
                    input={},
                    output={"contacts": [{"name": "Duncan Frederick"}]},
                    state="result",
                ),
            ],
        )
        msgs = [_user("q"), assistant, _user("next")]

        out = build_anthropic_messages(msgs)

        tr = out[2]["content"][0]
        assert tr["type"] == "tool_result"
        assert isinstance(tr["content"], str)
        assert "Duncan Frederick" in tr["content"]

    def test_string_output_passes_through_unmodified(self):
        """Tool outputs that are already strings must not be double-encoded."""
        assistant = ChatMessage(
            role="assistant",
            parts=[
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_s",
                    toolName="think",
                    input={"thought": "…"},
                    output="plain string output",
                    state="result",
                ),
            ],
        )
        msgs = [_user("q"), assistant, _user("next")]

        out = build_anthropic_messages(msgs)

        assert out[2]["content"][0]["content"] == "plain string output"

    def test_trailing_assistant_emits_synthetic_user_tool_results(self):
        """History ending on an assistant with tool-invocations must still be API-valid."""
        assistant = ChatMessage(
            role="assistant",
            parts=[
                ChatMessagePart(
                    type="tool-invocation",
                    toolCallId="toolu_last",
                    toolName="search_projects",
                    input={},
                    output={"ok": True},
                    state="result",
                ),
            ],
        )
        msgs = [_user("q"), assistant]

        out = build_anthropic_messages(msgs)

        # user, assistant (tool_use), synthetic user (tool_result)
        assert len(out) == 3
        assert out[1]["role"] == "assistant"
        assert out[1]["content"][0]["type"] == "tool_use"
        assert out[2]["role"] == "user"
        assert out[2]["content"][0]["type"] == "tool_result"
        assert out[2]["content"][0]["tool_use_id"] == "toolu_last"

    def test_legacy_content_only_assistant_message(self):
        """Messages saved before parts existed use .content — must still be emitted as text."""
        assistant = ChatMessage(role="assistant", content="pre-parts-era response")
        msgs = [_user("q"), assistant, _user("next")]

        out = build_anthropic_messages(msgs)

        assert out[1] == {
            "role": "assistant",
            "content": [{"type": "text", "text": "pre-parts-era response"}],
        }

    def test_user_file_part_preserved(self):
        """User file parts still become image/document blocks.

        Guards against regressing the existing ``get_content_blocks()`` path
        while adding tool-invocation handling.
        """
        # 1x1 transparent PNG base64 (split to satisfy line-length lint)
        png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        user_with_image = ChatMessage(
            role="user",
            parts=[
                ChatMessagePart(type="text", text="what's in this?"),
                ChatMessagePart(
                    type="file",
                    mediaType="image/png",
                    filename="pixel.png",
                    url=f"data:image/png;base64,{png_b64}",
                ),
            ],
        )
        msgs = [user_with_image]

        out = build_anthropic_messages(msgs)

        assert len(out) == 1
        types = [b["type"] for b in out[0]["content"]]
        assert "text" in types
        assert "image" in types
