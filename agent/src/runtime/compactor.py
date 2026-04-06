"""Context compaction — zero-dependency heuristic port of claw-code-2/compact.rs.

Replaces messages older than the preserve_recent window with a single synthetic
summary message built from pure string extraction. No API calls, no failure modes.
"""
from __future__ import annotations

import json
import os.path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTINUATION_PREAMBLE = (
    "This session is being continued from a previous conversation that ran out "
    "of context. The summary below covers the earlier portion of the conversation.\n\n"
)
RECENT_MESSAGES_NOTE = "Recent messages are preserved verbatim."
DIRECT_RESUME_INSTRUCTION = (
    "Continue the conversation from where it left off without asking the user any "
    "further questions. Resume directly — do not acknowledge the summary, do not "
    "recap what was happening, and do not preface with continuation text."
)

_FILE_EXTENSIONS = {".py", ".sql", ".json", ".md", ".ts", ".tsx", ".js"}
_PENDING_KEYWORDS = {"todo", "next", "pending", "follow up", "remaining", "epc", "contractor"}

# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_chars: int) -> str:
    """Return text truncated to max_chars with a trailing ellipsis if shortened."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: one token per 4 characters of JSON-serialized message."""
    return sum(len(json.dumps(m, default=str)) for m in messages) // 4


def _extract_file_candidates(text: str) -> list[str]:
    """Extract unique file paths with known extensions from a block of text.

    Strips surrounding punctuation from each token, keeps tokens that contain
    a '/' and have one of the target extensions. Returns up to 8 unique paths.
    """
    seen: set[str] = set()
    result: list[str] = []
    for token in text.split():
        candidate = token.strip(",.;:)(\"'`")
        if "/" in candidate:
            _, ext = os.path.splitext(candidate)
            if ext.lower() in _FILE_EXTENSIONS and candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
                if len(result) >= 8:
                    break
    return result


# ---------------------------------------------------------------------------
# Message text extraction
# ---------------------------------------------------------------------------


def _extract_first_text(message: dict) -> str | None:
    """Return the first non-empty text string from a message, or None.

    Handles both plain-string content and list-of-blocks content.
    Skips tool_use and tool_result blocks.
    """
    content = message.get("content", "")
    if isinstance(content, str):
        stripped = content.strip()
        return stripped if stripped else None
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    return text
    return None


def _extract_all_text(message: dict) -> str:
    """Return all text content from a message concatenated for file scanning."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                parts.append(block.get("text", ""))
            elif t == "tool_use":
                inp = block.get("input", {})
                parts.append(json.dumps(inp) if isinstance(inp, dict) else str(inp))
            elif t == "tool_result":
                c = block.get("content", "")
                parts.append(c if isinstance(c, str) else json.dumps(c, default=str))
        return " ".join(parts)
    return ""


def _summarize_message_content(message: dict) -> str:
    """Produce a short one-line summary of a message for the timeline section."""
    content = message.get("content", "")
    if isinstance(content, str):
        return _truncate(content, 160)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                parts.append(_truncate(block.get("text", ""), 160))
            elif t == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                inp_str = json.dumps(inp) if isinstance(inp, dict) else str(inp)
                parts.append(f"tool_use {name}({_truncate(inp_str, 80)})")
            elif t == "tool_result":
                c = block.get("content", "")
                c_str = c if isinstance(c, str) else json.dumps(c, default=str)
                parts.append(f"tool_result: {_truncate(c_str, 80)}")
        return " | ".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Summary formatting and detection
# ---------------------------------------------------------------------------


def _format_summary(summary: str) -> str:
    """Convert <summary>...</summary> XML to plain readable text.

    Strips the XML tags and prepends 'Summary:\\n'.
    Falls back to returning the string as-is if tags aren't present.
    """
    if "<summary>" in summary and "</summary>" in summary:
        start = summary.find("<summary>") + len("<summary>")
        end = summary.find("</summary>")
        inner = summary[start:end].strip()
        return "Summary:\n" + inner
    return summary.strip()


def _detect_existing_summary(message: dict) -> str | None:
    """Return the raw summary string if message is a prior compaction message, else None.

    A prior compaction message starts with CONTINUATION_PREAMBLE. The raw summary
    is extracted by stripping the preamble and trailing instruction text.
    """
    if message.get("role") != "user":
        return None
    content = message.get("content", "")
    if not isinstance(content, str) or not content.startswith(CONTINUATION_PREAMBLE):
        return None
    summary = content[len(CONTINUATION_PREAMBLE):]
    split_note = f"\n\n{RECENT_MESSAGES_NOTE}"
    if split_note in summary:
        summary = summary.split(split_note)[0]
    split_resume = f"\n{DIRECT_RESUME_INSTRUCTION}"
    if split_resume in summary:
        summary = summary.split(split_resume)[0]
    return summary.strip()


# ---------------------------------------------------------------------------
# Core summarization
# ---------------------------------------------------------------------------


def _summarize_messages(messages: list[dict]) -> str:
    """Build a <summary> XML block from a list of messages via pure heuristics.

    Extracts: scope counts, tool names, recent user requests, pending-work text,
    key file paths, current work, and a per-message timeline.
    Single pass over messages — all fields accumulated together.
    """
    user_count = 0
    assistant_count = 0
    tool_names: set[str] = set()
    all_text_parts: list[str] = []
    user_texts: list[str] = []    # all non-summary user messages
    keyword_texts: list[str] = []  # all messages matching pending-work keywords
    current_work: str | None = None
    timeline: list[str] = []

    for m in messages:
        role = m.get("role", "unknown")
        if role == "user":
            user_count += 1
        elif role == "assistant":
            assistant_count += 1

        # Tool names
        content = m.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_names.add(block.get("name", "unknown"))

        all_text_parts.append(_extract_all_text(m))
        timeline.append(f"  - {role}: {_summarize_message_content(m)}")

        text = _extract_first_text(m)
        if text and not text.startswith(CONTINUATION_PREAMBLE):
            if role == "user":
                user_texts.append(_truncate(text, 160))
            if any(kw in text.lower() for kw in _PENDING_KEYWORDS):
                keyword_texts.append(_truncate(text, 160))
            current_work = _truncate(text, 200)

    recent_user = user_texts[-3:]
    pending_work = keyword_texts[-3:]
    key_files = _extract_file_candidates(" ".join(all_text_parts))

    # Build XML block
    lines: list[str] = [
        "<summary>",
        "Conversation summary:",
        (
            f"- Scope: {len(messages)} earlier messages compacted "
            f"(user={user_count}, assistant={assistant_count})."
        ),
    ]
    if tool_names:
        lines.append(f"- Tools mentioned: {', '.join(sorted(tool_names))}.")
    if recent_user:
        lines.append("- Recent user requests:")
        lines.extend(f"  - {r}" for r in recent_user)
    if pending_work:
        lines.append("- Pending work:")
        lines.extend(f"  - {p}" for p in pending_work)
    if key_files:
        lines.append(f"- Key files referenced: {', '.join(key_files)}.")
    if current_work:
        lines.append(f"- Current work: {current_work}")
    lines.append("- Key timeline:")
    lines.extend(timeline)
    lines.append("</summary>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary merging (for repeat compactions)
# ---------------------------------------------------------------------------


def _parse_summary_sections(summary: str) -> tuple[list[str], list[str]]:
    """Split a formatted summary into (highlights, timeline) in a single pass.

    Returns a 2-tuple: (non-timeline bullet lines, timeline lines).
    Calls _format_summary once so callers don't have to.
    """
    formatted = _format_summary(summary)
    highlights: list[str] = []
    timeline: list[str] = []
    in_timeline = False
    for line in formatted.splitlines():
        stripped = line.rstrip()
        if stripped == "- Key timeline:":
            in_timeline = True
            continue
        if in_timeline:
            if not stripped:
                break
            timeline.append(stripped)
        else:
            if not stripped or stripped in ("Summary:", "Conversation summary:"):
                continue
            highlights.append(stripped)
    return highlights, timeline


def _extract_highlights(summary: str) -> list[str]:
    """Return all non-timeline bullet lines from a summary string."""
    highlights, _ = _parse_summary_sections(summary)
    return highlights


def _extract_timeline(summary: str) -> list[str]:
    """Return the timeline lines from a summary string."""
    _, timeline = _parse_summary_sections(summary)
    return timeline


def _merge_summaries(existing: str, new_summary: str) -> str:
    """Merge a prior compaction summary with a new one.

    Produces a <summary> block with:
    - "Previously compacted context" (highlights from existing, no timeline)
    - "Newly compacted context" (highlights from new_summary)
    - "Key timeline" (timeline from new_summary only)
    """
    prev_highlights, _ = _parse_summary_sections(existing)
    new_highlights, new_timeline = _parse_summary_sections(new_summary)

    lines: list[str] = ["<summary>", "Conversation summary:"]
    if prev_highlights:
        lines.append("- Previously compacted context:")
        lines.extend(f"  {line}" for line in prev_highlights)
    if new_highlights:
        lines.append("- Newly compacted context:")
        lines.extend(f"  {line}" for line in new_highlights)
    if new_timeline:
        lines.append("- Key timeline:")
        lines.extend(new_timeline)
    lines.append("</summary>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Continuation message
# ---------------------------------------------------------------------------


def _build_continuation_message(summary: str) -> dict:
    """Wrap a summary in a user message for injection as the new conversation head."""
    formatted = _format_summary(summary)
    content = (
        f"{CONTINUATION_PREAMBLE}{formatted}"
        f"\n\n{RECENT_MESSAGES_NOTE}"
        f"\n{DIRECT_RESUME_INSTRUCTION}"
    )
    return {"role": "user", "content": content}


# ---------------------------------------------------------------------------
# Public compactor
# ---------------------------------------------------------------------------


class HeuristicCompactor:
    """Zero-dependency context compactor.

    Replaces messages older than preserve_recent with a single synthetic
    summary message built from pure string extraction. No API calls.

    Usage (same as the old Compactor):
        compactor = HeuristicCompactor(max_tokens=80_000, preserve_recent=6)
        messages = await compactor.maybe_compact(messages)
    """

    def __init__(
        self,
        max_tokens: int = 80_000,
        preserve_recent: int = 6,
    ) -> None:
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent

    async def maybe_compact(self, messages: list[dict]) -> list[dict]:
        """Compact messages if context exceeds threshold.

        Returns the original list unchanged (same object) if under threshold
        or if there are not enough messages to compact.
        """
        if _estimate_tokens(messages) <= self.max_tokens:
            return messages
        if len(messages) <= self.preserve_recent:
            return messages

        older = messages[: -self.preserve_recent]
        recent = messages[-self.preserve_recent :]

        existing_summary = _detect_existing_summary(older[0]) if older else None
        new_summary = _summarize_messages(older)

        if existing_summary:
            merged = _merge_summaries(existing_summary, new_summary)
        else:
            merged = new_summary

        return [_build_continuation_message(merged)] + recent


# Backward-compatible alias so existing callers (e.g. agent_runtime.py) keep working.
Compactor = HeuristicCompactor
