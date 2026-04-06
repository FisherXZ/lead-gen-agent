"""Context compaction for long conversations.

Replaces large tool_result content in old turns with compact stubs to keep
the conversation within context limits. Pure module — no external deps.
"""

from __future__ import annotations

import copy
import json

MAX_CONTEXT_CHARS = 100_000
COMPACTION_THRESHOLD_CHARS = 500
KEEP_RECENT_TURNS = 6


def estimate_context_size(api_messages: list[dict]) -> int:
    """Sum of json.dumps(m) lengths across all messages."""
    return sum(len(json.dumps(m, default=str)) for m in api_messages)


def compact_messages(
    api_messages: list[dict],
    *,
    max_context_chars: int = MAX_CONTEXT_CHARS,
    keep_recent_turns: int = KEEP_RECENT_TURNS,
    threshold_chars: int = COMPACTION_THRESHOLD_CHARS,
) -> list[dict]:
    """Return a new list with old large tool outputs replaced by stubs.

    Does NOT mutate the input list.

    Algorithm:
    1. estimate_context_size - if under max, return as-is
    2. Identify turn boundaries (assistant msg + following user tool_result msg = 1 turn)
    3. Mark last keep_recent_turns turns as protected
    4. For unprotected turns, find tool_result items in user messages where
       len(content) > threshold
    5. Replace those content strings with compact stubs
    6. Return new list
    """
    if estimate_context_size(api_messages) <= max_context_chars:
        return api_messages

    # Deep copy to avoid mutating input
    messages = copy.deepcopy(api_messages)

    # Identify tool-use turns: pairs of (assistant_idx, user_idx) where the
    # user message contains tool_result blocks.
    turns: list[tuple[int, int]] = []
    for i, msg in enumerate(messages):
        if (
            msg.get("role") == "user"
            and isinstance(msg.get("content"), list)
            and any(_is_tool_result(item) for item in msg["content"])
        ):
            # Find the preceding assistant message
            assistant_idx = i - 1 if i > 0 and messages[i - 1].get("role") == "assistant" else None
            turns.append((assistant_idx, i))

    if not turns:
        return messages

    # Protect last keep_recent_turns turns
    protected_turn_indices = set(range(max(0, len(turns) - keep_recent_turns), len(turns)))

    for turn_idx, (assistant_idx, user_idx) in enumerate(turns):
        if turn_idx in protected_turn_indices:
            continue

        user_msg = messages[user_idx]
        # Build a tool_use_id -> tool_name map from the preceding assistant message
        tool_name_map = _build_tool_name_map(
            messages[assistant_idx] if assistant_idx is not None else None
        )

        new_content = []
        for item in user_msg["content"]:
            if _is_tool_result(item):
                content_str = item.get("content", "")
                if isinstance(content_str, str) and len(content_str) > threshold_chars:
                    # Skip already-compacted stubs
                    if _is_already_compacted(content_str):
                        new_content.append(item)
                        continue
                    tool_use_id = item.get("tool_use_id", "")
                    tool_name = tool_name_map.get(tool_use_id, "unknown")
                    item["content"] = _compact_tool_result(content_str, tool_name)
                new_content.append(item)
            else:
                new_content.append(item)

        user_msg["content"] = new_content

    return messages


def _compact_tool_result(content_str: str, tool_name: str = "unknown") -> str:
    """If content_str > threshold, return JSON stub. Otherwise return as-is.

    Stub format:
        {"_compacted": true, "tool": "<name>", "summary": "<meaningful summary>",
         "result_count": N}

    Tries to extract meaningful names from list items before falling back to
    raw truncation.
    """
    result_count = 1

    try:
        parsed = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        # Non-JSON content: truncate
        summary = content_str[:200]
        stub = {
            "_compacted": True,
            "tool": tool_name,
            "summary": summary + "..." if len(content_str) > 200 else summary,
            "result_count": 1,
        }
        return json.dumps(stub)

    summary = None

    if isinstance(parsed, dict):
        # Look for a list value and extract item names
        list_key = None
        list_val = None
        for k, v in parsed.items():
            if isinstance(v, list):
                list_key = k
                list_val = v
                result_count = len(v)
                break

        if list_val and result_count > 0:
            # Try to extract meaningful names from list items
            _name_keys = ("project_name", "title", "name", "epc_contractor")
            names = []
            for item in list_val[:3]:
                if isinstance(item, dict):
                    for nk in _name_keys:
                        if nk in item and item[nk]:
                            names.append(str(item[nk]))
                            break
            if names:
                label = list_key or "items"
                names_str = ", ".join(names)
                if result_count > 3:
                    names_str += f"... ({result_count} total)"
                summary = f"{result_count} {label}: {names_str}"
        elif not list_val:
            # Dict without lists — try to extract summary or status
            for sk in ("summary", "status"):
                if sk in parsed and parsed[sk]:
                    summary = str(parsed[sk])[:200]
                    break

    elif isinstance(parsed, list):
        result_count = len(parsed)

    # Fallback to raw truncation
    if not summary:
        raw = content_str[:120]
        summary = raw + "..." if len(content_str) > 120 else raw

    stub = {
        "_compacted": True,
        "tool": tool_name,
        "summary": summary,
        "result_count": result_count,
    }
    return json.dumps(stub)


def _is_tool_result(item: dict) -> bool:
    """Check if a content item is a tool_result block."""
    return isinstance(item, dict) and item.get("type") == "tool_result"


def _is_already_compacted(content_str: str) -> bool:
    """Check if content is already a compacted stub."""
    try:
        parsed = json.loads(content_str)
        return isinstance(parsed, dict) and parsed.get("_compacted") is True
    except (json.JSONDecodeError, TypeError):
        return False


def _build_tool_name_map(assistant_msg: dict | None) -> dict[str, str]:
    """Extract tool_use_id -> tool_name mapping from an assistant message.

    Handles both dict-style content blocks and Anthropic ContentBlock objects
    (which have .type, .id, .name attributes).
    """
    if assistant_msg is None:
        return {}

    content = assistant_msg.get("content")
    if not isinstance(content, list):
        return {}

    name_map: dict[str, str] = {}
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "tool_use":
                name_map[block.get("id", "")] = block.get("name", "unknown")
        else:
            # Anthropic ContentBlock object with attributes
            if getattr(block, "type", None) == "tool_use":
                name_map[getattr(block, "id", "")] = getattr(block, "name", "unknown")

    return name_map
