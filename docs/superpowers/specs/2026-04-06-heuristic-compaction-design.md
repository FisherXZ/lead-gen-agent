# Heuristic Context Compaction Design

**Date:** 2026-04-06  
**Status:** Approved  

## Problem

`agent/src/runtime/compactor.py` calls the Haiku API to summarize older messages when context exceeds a token threshold. This creates three problems:

1. **Latency** — extra API round-trip during the agent loop
2. **Cost** — Haiku call on every compaction event
3. **Silent failure** — on API error the fallback is `messages[-3:]`, which silently destroys most of the conversation history

A separate `agent/src/compaction.py` compresses individual tool results into JSON stubs, but its scope is narrower (tool results only, not full messages) and it is not integrated with the main compaction path.

The reference implementation in `claw-code-2/rust/crates/runtime/src/compact.rs` solves this with pure heuristic string extraction — zero API calls, zero failure modes.

## Decision

Replace both `compaction.py` and `compactor.py` with a single rewritten `compactor.py` that is a Python port of the claw-code-2 heuristic algorithm. Same public interface (`HeuristicCompactor.maybe_compact`), no external dependencies.

## Files Changed

| File | Action |
|------|--------|
| `agent/src/runtime/compactor.py` | Full rewrite — `HeuristicCompactor` replaces `Compactor` |
| `agent/tests/test_runtime_compactor.py` | Full rewrite — tests for new implementation |
| `agent/src/compaction.py` | Deleted |
| `agent/tests/test_compaction.py` | Deleted |
| `agent/src/agents/chat.py` | Remove `api_key=` kwarg from `HeuristicCompactor(...)` call |
| `agent/src/agents/research.py` | Remove `api_key=` kwarg from `HeuristicCompactor(...)` call |

`agent_runtime.py`, `chat.py`, and `research.py` have no changes — they call `compactor.maybe_compact(messages)` which remains the same signature.

## Algorithm

### `maybe_compact(messages: list[dict]) -> list[dict]`

1. **Token estimate:** `sum(len(json.dumps(m)) for m in messages) // 4`. If `<= max_tokens` → return as-is (no copy).
2. If `len(messages) <= preserve_recent` → return as-is.
3. Split: `older = messages[:-preserve_recent]`, `recent = messages[-preserve_recent:]`.
4. Detect existing summary: check if `older[0]` is a prior compaction message (identified by the `CONTINUATION_PREAMBLE` string prefix in its content).
5. Call `_summarize_messages(older)` → produces `<summary>…</summary>` XML block via pure string extraction (see below).
6. If prior summary exists: call `_merge_summaries(prior_summary, new_summary)` → produces merged block with "Previously compacted context" and "Newly compacted context" sections.
7. Build continuation message (role `"user"`, content = preamble + formatted summary + "Recent messages are preserved verbatim." + direct-resume instruction).
8. Return `[continuation_message] + recent`.

### `_summarize_messages(messages: list[dict]) -> str`

Builds a `<summary>` block containing:

- **Scope line:** count of messages by role (user / assistant / tool)
- **Tool names:** deduplicated list of all `tool_use` block names called
- **Recent user requests:** last 3 user messages' first text content, truncated to 160 chars each
- **Pending work:** last 3 messages whose lowercased text contains any of: `todo`, `next`, `pending`, `follow up`, `remaining`, `epc`, `contractor` — truncated to 160 chars
- **Key files:** token-split across all content, extract tokens containing `/` with extensions `.py`, `.sql`, `.json`, `.md`, `.ts`, `.tsx` — deduplicated, up to 8
- **Current work:** most recent non-empty text block, truncated to 200 chars
- **Key timeline:** one line per message — role + summarized content (tool_use shown as `tool_use name(input[:80])`, tool_result as `tool_result name: output[:80]`, text truncated to 160 chars)

### `_merge_summaries(existing: str, new: str) -> str`

When compaction runs a second time on an already-compacted session:

- Extract "highlights" from the existing summary (all non-timeline bullet lines)
- Extract "highlights" and "timeline" from the new summary
- Produce merged `<summary>` with three sections: "Previously compacted context", "Newly compacted context", "Key timeline"

### Constants

```python
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
```

### Helper: `_extract_text_content(message: dict) -> str`

Normalizes a message dict into a plain string for text extraction. Handles:
- `content` as a plain string
- `content` as a list of blocks — extracts `text` from `{"type": "text"}` blocks, `name` from `{"type": "tool_use"}` blocks, first 80 chars of `content` from `{"type": "tool_result"}` blocks

### Helper: `_extract_file_candidates(text: str) -> list[str]`

Splits on whitespace, strips trailing punctuation (`,.:;)('"`` ), keeps tokens that contain `/` and have one of the target extensions.

### Helper: `_truncate(text: str, max_chars: int) -> str`

Returns `text` if `len(text) <= max_chars`, else `text[:max_chars] + "…"`.

## Constructor

```python
class HeuristicCompactor:
    def __init__(
        self,
        max_tokens: int = 80_000,
        preserve_recent: int = 6,
    ): ...
```

`api_key` and `summary_model` parameters are removed (no longer needed). Callers in `chat.py` and `research.py` currently pass `api_key=api_key` — this parameter is dropped, those call sites need updating.

## Test Coverage

Replace `test_runtime_compactor.py` with tests covering:

1. Under-threshold messages → returned as-is
2. At-threshold, fewer messages than `preserve_recent` → returned as-is
3. Basic compaction: summary message injected, recent messages preserved verbatim
4. Summary contains expected fields (scope line, tool names, recent requests, pending work, key files)
5. Repeat compaction: merged summary contains "Previously compacted context" and "Newly compacted context"
6. Existing summary message excluded from `should_compact` token count
7. File extraction: `.py` and `.sql` paths detected, `.txt` paths ignored
8. Pending work: `epc`/`contractor` keywords trigger extraction

## What Does Not Change

- `agent_runtime.py` — no changes
- `AgentRuntime` constructor signature — no changes
- The `maybe_compact` async interface — kept async (sync body, async signature) to avoid changing all callers
- Compaction behavior from the agent's perspective — same trigger threshold, same preserve-recent window
