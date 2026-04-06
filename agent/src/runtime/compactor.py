"""Summarization-based context compaction.

When conversation context exceeds a token threshold, older messages are
summarized by a cheap model (Haiku) while recent messages are preserved
verbatim. This keeps long sessions coherent without context overflow.
"""

from __future__ import annotations

import json
import logging
import os

import anthropic

_logger = logging.getLogger(__name__)

SUMMARY_MODEL = "claude-haiku-4-5-20251001"

SUMMARY_PROMPT = """You are summarizing a conversation for context continuity.
The conversation is between a user and an AI research assistant that investigates
solar energy projects and EPC (Engineering, Procurement, Construction) contractors.

Extract from the messages below:
- What the user asked for
- Tools called and their key results (not raw output)
- Discoveries made (EPC findings, confidence levels, sources)
- Dead ends (searches that returned nothing useful)
- Current state of work (what's been done, what's pending)
- Key entities referenced (project names, company names, locations)

Be concise. This summary replaces the original messages."""

MERGE_PREFIX = """A prior summary exists from an earlier compaction.
Merge it with the new messages into a single coherent summary.

Prior summary:
{existing_summary}

New messages to incorporate:
"""


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: ~4 characters per token."""
    total_chars = sum(len(json.dumps(m, default=str)) for m in messages)
    return total_chars // 4


def _build_summary_message(summary: str) -> dict:
    """Wrap a summary string in a user message for injection."""
    return {
        "role": "user",
        "content": (
            "[This conversation was compacted for context management.]\n\n"
            "Summary of earlier messages:\n"
            f"{summary}\n\n"
            "Recent messages are preserved verbatim below. "
            "Continue from where you left off."
        ),
    }


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Format messages into a readable string for the summarizer."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text from content blocks
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", "")[:500])
                    elif block.get("type") == "tool_use":
                        texts.append(f"[tool_use: {block.get('name', '?')}]")
                    elif block.get("type") == "tool_result":
                        result_str = block.get("content", "")
                        texts.append(f"[tool_result: {result_str[:200]}]")
            content = "\n".join(texts)
        elif isinstance(content, str):
            content = content[:1000]
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _detect_existing_summary(messages: list[dict]) -> str | None:
    """Check if the first message is a compaction summary."""
    if not messages:
        return None
    first = messages[0]
    content = first.get("content", "")
    if isinstance(content, str) and "[This conversation was compacted" in content:
        return content
    return None


class Compactor:
    """Summarization-based context compaction."""

    def __init__(
        self,
        max_tokens: int = 80_000,
        preserve_recent: int = 6,
        summary_model: str = SUMMARY_MODEL,
        api_key: str | None = None,
    ):
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent
        self.summary_model = summary_model
        self._api_key = api_key

    async def maybe_compact(self, messages: list[dict]) -> list[dict]:
        """If context exceeds threshold, summarize older messages.

        Returns the original list if under threshold (no copy).
        Returns [summary_message] + recent_messages if compacted.
        """
        if estimate_tokens(messages) <= self.max_tokens:
            return messages

        if len(messages) <= self.preserve_recent:
            return messages  # nothing to compact

        older = messages[:-self.preserve_recent]
        recent = messages[-self.preserve_recent:]

        existing_summary = _detect_existing_summary(older)
        summary = await self._summarize(older, existing_summary=existing_summary)

        return [_build_summary_message(summary)] + recent

    async def _summarize(
        self,
        messages: list[dict],
        existing_summary: str | None = None,
    ) -> str:
        """Call Haiku to summarize messages."""
        formatted = _format_messages_for_summary(messages)

        if existing_summary:
            user_content = MERGE_PREFIX.format(existing_summary=existing_summary) + formatted
        else:
            user_content = formatted

        try:
            api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=self.summary_model,
                max_tokens=1024,
                system=SUMMARY_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            return response.content[0].text
        except Exception as exc:
            _logger.warning("Compaction summarization failed: %s", exc)
            # Fallback: truncate older messages to a simple list
            return _format_messages_for_summary(messages[-3:])
