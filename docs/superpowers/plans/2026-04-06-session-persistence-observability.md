# Session Persistence & Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append a `chat_events` row to Postgres for every tool call, turn boundary, and failure during agent execution — giving durability, crash detection, and per-tool observability — while adding token counts to `chat_messages`.

**Architecture:** New append-only `chat_events` table in Supabase receives fire-and-forget INSERTs (via `asyncio.to_thread`) at 6 points in the `chat_agent.py` loop. `save_message()` gains optional token parameters that populate new nullable columns on `chat_messages`. No existing API or frontend behaviour changes.

**Tech Stack:** Python 3.12, supabase-py (sync client), pytest-asyncio, SQL (Postgres/Supabase)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `supabase/migrations/026_chat_events.sql` | Create | New table + index + ALTER chat_messages columns |
| `agent/src/db.py` | Modify | Add `log_chat_event()`, extend `save_message()` signature |
| `agent/src/chat_agent.py` | Modify | Token accumulation dict + 6 fire-and-forget event writes |
| `agent/tests/test_db_chat_events.py` | Create | Unit tests for `log_chat_event()` and updated `save_message()` |
| `agent/tests/test_chat_agent.py` | Modify | Add tests verifying event write calls and token passthrough |

---

## Task 1: SQL Migration

**Files:**
- Create: `supabase/migrations/026_chat_events.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/026_chat_events.sql
-- Append-only event log for agent session durability and observability.
-- Each row is one event in the agent loop (tool call, turn boundary, failure).
-- Writes are fire-and-forget from the Python side; failures are logged, not raised.

CREATE TABLE IF NOT EXISTS chat_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    turn_number     INT         NOT NULL DEFAULT 0,
    event_type      TEXT        NOT NULL,
    data            JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_events_conversation
    ON chat_events (conversation_id, created_at);

-- Service role only — no anon reads
ALTER TABLE chat_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service role full access"
    ON chat_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Token tracking on chat_messages (all nullable for backward compat)
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS input_tokens       INT,
    ADD COLUMN IF NOT EXISTS output_tokens      INT,
    ADD COLUMN IF NOT EXISTS cache_read_tokens  INT,
    ADD COLUMN IF NOT EXISTS cache_write_tokens INT,
    ADD COLUMN IF NOT EXISTS iterations         INT;
```

- [ ] **Step 2: Commit the migration**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
git add supabase/migrations/026_chat_events.sql
git commit -m "feat: add chat_events table and token columns on chat_messages"
```

> **Note:** Apply this migration to Supabase before running the agent in production. In development, run `supabase db push` or apply directly in the Supabase SQL editor.

---

## Task 2: `db.py` — `log_chat_event()` + updated `save_message()`

**Files:**
- Modify: `agent/src/db.py` (after the existing `save_message` function, ~line 619)
- Create: `agent/tests/test_db_chat_events.py`

- [ ] **Step 1: Write the failing tests first**

Create `agent/tests/test_db_chat_events.py`:

```python
"""Tests for log_chat_event() and updated save_message() token params."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

import src.db as db


# ---------------------------------------------------------------------------
# log_chat_event
# ---------------------------------------------------------------------------


class TestLogChatEvent:
    @patch("src.db.get_client")
    def test_inserts_row_with_correct_fields(self, mock_get_client):
        mock_table = MagicMock()
        mock_get_client.return_value.table.return_value = mock_table

        db.log_chat_event("conv-abc", 2, "tool_called", {"tool_name": "web_search"})

        mock_get_client.return_value.table.assert_called_once_with("chat_events")
        mock_table.insert.assert_called_once_with({
            "conversation_id": "conv-abc",
            "turn_number": 2,
            "event_type": "tool_called",
            "data": {"tool_name": "web_search"},
        })
        mock_table.insert.return_value.execute.assert_called_once()

    @patch("src.db.get_client")
    def test_swallows_exception_without_raising(self, mock_get_client):
        mock_get_client.return_value.table.side_effect = RuntimeError("DB down")

        # Must not raise — fire-and-forget semantics
        db.log_chat_event("conv-xyz", 0, "turn_started", {})

    @patch("src.db.get_client")
    def test_empty_data_dict_allowed(self, mock_get_client):
        mock_table = MagicMock()
        mock_get_client.return_value.table.return_value = mock_table

        db.log_chat_event("conv-abc", 0, "agent_finished", {})

        mock_table.insert.assert_called_once_with({
            "conversation_id": "conv-abc",
            "turn_number": 0,
            "event_type": "agent_finished",
            "data": {},
        })


# ---------------------------------------------------------------------------
# save_message — token parameters
# ---------------------------------------------------------------------------


class TestSaveMessageTokens:
    @patch("src.db.get_client")
    def test_token_params_included_in_insert(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "msg-1"}
        ]

        db.save_message(
            conversation_id="conv-abc",
            role="assistant",
            content="Hello",
            input_tokens=500,
            output_tokens=120,
            cache_read_tokens=400,
            cache_write_tokens=10,
            iterations=3,
        )

        inserted_data = mock_client.table.return_value.insert.call_args[0][0]
        assert inserted_data["input_tokens"] == 500
        assert inserted_data["output_tokens"] == 120
        assert inserted_data["cache_read_tokens"] == 400
        assert inserted_data["cache_write_tokens"] == 10
        assert inserted_data["iterations"] == 3

    @patch("src.db.get_client")
    def test_token_params_omitted_when_none(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "msg-1"}
        ]

        db.save_message(
            conversation_id="conv-abc",
            role="assistant",
            content="Hello",
        )

        inserted_data = mock_client.table.return_value.insert.call_args[0][0]
        assert "input_tokens" not in inserted_data
        assert "output_tokens" not in inserted_data
        assert "iterations" not in inserted_data
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest tests/test_db_chat_events.py -v
```

Expected: `AttributeError: module 'src.db' has no attribute 'log_chat_event'`

- [ ] **Step 3: Add `log_chat_event()` to `db.py`**

Open `agent/src/db.py`. After the `save_message` function (around line 619), add:

```python
def log_chat_event(
    conversation_id: str,
    turn_number: int,
    event_type: str,
    data: dict,
) -> None:
    """Write one event row to chat_events.

    Synchronous (uses existing sync Supabase client).
    Always call via asyncio.create_task(asyncio.to_thread(log_chat_event, ...))
    so it runs in a thread pool and never blocks the event loop.
    Failures are logged and swallowed — never raised to the caller.
    """
    try:
        client = get_client()
        client.table("chat_events").insert(
            {
                "conversation_id": conversation_id,
                "turn_number": turn_number,
                "event_type": event_type,
                "data": data,
            }
        ).execute()
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "chat_event write failed: %s conversation=%s",
            event_type,
            conversation_id,
        )
```

- [ ] **Step 4: Update `save_message()` to accept token params**

Replace the existing `save_message` function signature and body in `agent/src/db.py`:

```python
def save_message(
    conversation_id: str,
    role: str,
    content: str,
    parts: list | None = None,
    user_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    iterations: int | None = None,
) -> dict:
    client = get_client()
    # Validate ownership if user_id is provided
    if user_id:
        conv = (
            client.table("chat_conversations")
            .select("user_id")
            .eq("id", conversation_id)
            .maybe_single()
            .execute()
        )
        if not conv.data or conv.data.get("user_id") != user_id:
            raise PermissionError(
                f"Conversation {conversation_id} does not belong to user {user_id}"
            )
    data: dict = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "parts": parts or [],
    }
    if input_tokens is not None:
        data["input_tokens"] = input_tokens
    if output_tokens is not None:
        data["output_tokens"] = output_tokens
    if cache_read_tokens is not None:
        data["cache_read_tokens"] = cache_read_tokens
    if cache_write_tokens is not None:
        data["cache_write_tokens"] = cache_write_tokens
    if iterations is not None:
        data["iterations"] = iterations
    resp = client.table("chat_messages").insert(data).execute()
    return resp.data[0]
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest tests/test_db_chat_events.py -v
```

Expected: 5 tests pass.

- [ ] **Step 6: Run full test suite to confirm nothing broke**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest --tb=short -q
```

Expected: existing tests still pass, no regressions.

- [ ] **Step 7: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
git add agent/src/db.py agent/tests/test_db_chat_events.py
git commit -m "feat: add log_chat_event() and token params on save_message()"
```

---

## Task 3: `chat_agent.py` — token accumulation + 6 event writes

**Files:**
- Modify: `agent/src/chat_agent.py`
- Modify: `agent/tests/test_chat_agent.py`

**Background:** The current loop in `chat_agent.py` uses `for _round in range(MAX_TOOL_ROUNDS)` with `had_tool_rounds` tracking. We are adding to the existing loop — not changing its structure. Token accumulation goes at two points: initialisation (before the loop) and after each `get_final_message()`. Event writes go at six points.

- [ ] **Step 1: Add failing tests for event logging**

In `agent/tests/test_chat_agent.py`, add to the imports at the top:

```python
import asyncio
```

Add this test class at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# Session persistence: event logging + token accumulation
# ---------------------------------------------------------------------------


class TestChatAgentEventLogging:
    """Verify that log_chat_event is called at the right points."""

    def _make_usage(self, input_tokens=100, output_tokens=50,
                    cache_read=20, cache_write=5):
        usage = MagicMock()
        usage.input_tokens = input_tokens
        usage.output_tokens = output_tokens
        usage.cache_read_input_tokens = cache_read
        usage.cache_creation_input_tokens = cache_write
        return usage

    @patch("src.chat_agent.db")
    async def test_agent_finished_event_emitted_on_clean_exit(self, mock_db):
        """agent_finished event is written when the loop exits with no tool calls."""
        mock_db.save_message.return_value = {"id": "msg-1"}

        usage = self._make_usage()
        final_msg = _final_message(stop_reason="end_turn")
        final_msg.usage = usage

        stream = _mock_stream(
            [_text_block_start(), _text_delta("Hello"), _block_stop()],
            final_msg,
        )

        logged_events = []

        async def fake_to_thread(fn, *args, **kwargs):
            if fn is mock_db.log_chat_event:
                logged_events.append(args)  # (conv_id, turn_num, event_type, data)
            return fn(*args, **kwargs) if callable(fn) else None

        with patch("src.chat_agent.asyncio.to_thread", side_effect=fake_to_thread):
            with patch("src.chat_agent.get_anthropic_client") as mock_client_fn:
                mock_client_fn.return_value.messages.stream.return_value = stream
                await _run_chat()

        event_types = [e[2] for e in logged_events]
        assert "turn_started" in event_types
        assert "turn_completed" in event_types
        assert "agent_finished" in event_types
        assert "agent_failed" not in event_types

    @patch("src.chat_agent.db")
    async def test_tool_events_emitted_for_tool_call(self, mock_db):
        """tool_called and tool_completed events fire around each tool execution."""
        mock_db.save_message.return_value = {"id": "msg-1"}

        usage = self._make_usage()

        # Round 1: tool call
        tool_final = _final_message(stop_reason="tool_use")
        tool_final.usage = usage
        tool_final.content = [MagicMock(type="tool_use", id="tc-1", name="remember",
                                        input={})]

        # Round 2: text reply
        end_final = _final_message(stop_reason="end_turn")
        end_final.usage = usage
        end_final.content = []

        streams = [
            _mock_stream(
                [_tool_block_start("tc-1", "remember"),
                 _tool_input_delta('{"key":"x","value":"y"}'),
                 _block_stop()],
                tool_final,
            ),
            _mock_stream(
                [_text_block_start(), _text_delta("Done"), _block_stop()],
                end_final,
            ),
        ]
        stream_iter = iter(streams)

        logged_events = []

        async def fake_to_thread(fn, *args, **kwargs):
            if fn is mock_db.log_chat_event:
                logged_events.append(args)
            return None

        with patch("src.chat_agent.asyncio.to_thread", side_effect=fake_to_thread):
            with patch("src.chat_agent.get_anthropic_client") as mock_client_fn:
                mock_client_fn.return_value.messages.stream.side_effect = \
                    lambda **kw: next(stream_iter)
                with patch("src.chat_agent.execute_tool", new_callable=AsyncMock,
                           return_value={"status": "ok"}):
                    await _run_chat()

        event_types = [e[2] for e in logged_events]
        assert "tool_called" in event_types
        assert "tool_completed" in event_types

    @patch("src.chat_agent.db")
    async def test_save_message_called_with_token_counts(self, mock_db):
        """save_message() receives accumulated token counts at end of turn."""
        mock_db.save_message.return_value = {"id": "msg-1"}

        usage = self._make_usage(input_tokens=300, output_tokens=80,
                                 cache_read=100, cache_write=0)
        final_msg = _final_message(stop_reason="end_turn")
        final_msg.usage = usage

        stream = _mock_stream(
            [_text_block_start(), _text_delta("Hi"), _block_stop()],
            final_msg,
        )

        async def fake_to_thread(fn, *args, **kwargs):
            return None  # swallow event writes

        with patch("src.chat_agent.asyncio.to_thread", side_effect=fake_to_thread):
            with patch("src.chat_agent.get_anthropic_client") as mock_client_fn:
                mock_client_fn.return_value.messages.stream.return_value = stream
                await _run_chat()

        call_kwargs = mock_db.save_message.call_args.kwargs
        assert call_kwargs.get("input_tokens") == 300
        assert call_kwargs.get("output_tokens") == 80
        assert call_kwargs.get("cache_read_tokens") == 100
        assert call_kwargs.get("iterations") == 1
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest tests/test_chat_agent.py::TestChatAgentEventLogging -v
```

Expected: FAIL — `AttributeError` or assertion errors since events aren't logged yet.

- [ ] **Step 3: Add `import time` to `chat_agent.py` imports**

In `agent/src/chat_agent.py`, the imports block currently starts:

```python
from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncGenerator
```

Change to:

```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator

import anthropic
```

Also add near the top (after `MAX_TOOL_ROUNDS = 15`):

```python
_logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Add token accumulation dict before the loop**

In `chat_agent.py`, find this block (around line 165):

```python
    remember_count = 0

    had_tool_rounds = False  # Track if prior rounds used tools

    for _round in range(MAX_TOOL_ROUNDS):
```

Replace with:

```python
    remember_count = 0

    had_tool_rounds = False  # Track if prior rounds used tools

    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    iteration = 0

    for _round in range(MAX_TOOL_ROUNDS):
        iteration += 1
```

- [ ] **Step 5: Emit `turn_started` at the top of each loop iteration**

Find the line immediately after `for _round in range(MAX_TOOL_ROUNDS):` (which is now `iteration += 1`). Add after it:

```python
        asyncio.create_task(asyncio.to_thread(
            db.log_chat_event,
            conversation_id,
            iteration,
            "turn_started",
            {"turn_number": iteration, "model": MODEL},
        ))
```

- [ ] **Step 6: Accumulate tokens + emit `turn_completed` after `get_final_message()`**

Find this line (around line 243):

```python
            # Get the final message for stop_reason
            response = await stream.get_final_message()
```

Add immediately after it:

```python
        # Accumulate token usage across all loop iterations
        if response.usage:
            u = response.usage
            total_usage["input_tokens"]       += getattr(u, "input_tokens", 0)
            total_usage["output_tokens"]      += getattr(u, "output_tokens", 0)
            total_usage["cache_read_tokens"]  += getattr(u, "cache_read_input_tokens", 0)
            total_usage["cache_write_tokens"] += getattr(u, "cache_creation_input_tokens", 0)

        asyncio.create_task(asyncio.to_thread(
            db.log_chat_event,
            conversation_id,
            iteration,
            "turn_completed",
            {
                "turn_number": iteration,
                "input_tokens":       getattr(response.usage, "input_tokens", 0) if response.usage else 0,
                "output_tokens":      getattr(response.usage, "output_tokens", 0) if response.usage else 0,
                "cache_read_tokens":  getattr(response.usage, "cache_read_input_tokens", 0) if response.usage else 0,
                "cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) if response.usage else 0,
                "stop_reason":        response.stop_reason,
            },
        ))
```

- [ ] **Step 7: Emit `tool_called` + `tool_completed` around each tool execution**

In the tool execution loop, find the section where each `tc` (tool call) is processed. The pattern is:

```python
            for tc in tool_calls:
                # Special-case report_findings ...
                if tc["name"] == "report_findings":
                    output = await _handle_report_findings(tc["input"])
                elif tc["name"] == "remember":
                    ...
                elif tc["name"] == "batch_research_epc":
                    ...
                else:
                    try:
                        output = await execute_tool(tc["name"], tc["input"])
                    except Exception as exc:
                        output = {"error": f"{type(exc).__name__}: {exc}"}

                yield stream_writer.tool_output_available(tc["id"], output)
```

Change so that every branch is wrapped with timing and events. Replace the entire `for tc in tool_calls:` loop body with:

```python
            for tc in tool_calls:
                # Emit tool_called event before execution
                serializable_input = {
                    k: v
                    for k, v in tc["input"].items()
                    if not callable(v) and not isinstance(v, asyncio.Event)
                }
                asyncio.create_task(asyncio.to_thread(
                    db.log_chat_event,
                    conversation_id,
                    iteration,
                    "tool_called",
                    {
                        "tool_name":    tc["name"],
                        "tool_call_id": tc["id"],
                        "input":        serializable_input,
                    },
                ))

                _t0 = time.monotonic()
                is_error = False

                # Special-case report_findings to store discoveries in DB
                if tc["name"] == "report_findings":
                    output = await _handle_report_findings(tc["input"])
                elif tc["name"] == "remember":
                    remember_count += 1
                    if remember_count > 5:
                        output = {"error": "Rate limit: max 5 memories per conversation turn."}
                        is_error = True
                    else:
                        tc["input"]["_conversation_id"] = conversation_id
                        output = await execute_tool(tc["name"], tc["input"])
                elif tc["name"] == "batch_research_epc":
                    # Generate batch_id and register with progress store
                    batch_id = str(uuid.uuid4())

                    # Fetch project records to populate the progress store
                    batch_projects = []
                    for pid in tc["input"].get("project_ids", []):
                        p = db.get_project(pid)
                        if p:
                            batch_projects.append(p)

                    batch_state = create_batch(
                        batch_id, batch_projects, conversation_id=conversation_id
                    )

                    tc["input"]["_batch_id"] = batch_id
                    tc["input"]["_project_names"] = {
                        p["id"]: p.get("project_name") or p.get("queue_id", p["id"])
                        for p in batch_projects
                    }

                    async def _on_progress(update: dict, _bid: str = batch_id):
                        update_project(_bid, update)

                    tc["input"]["_progress_callback"] = _on_progress
                    tc["input"]["_cancel_event"] = get_cancel_event(batch_id)

                    sse_input = {
                        k: v
                        for k, v in tc["input"].items()
                        if k not in ("_progress_callback", "_cancel_event")
                    }
                    yield stream_writer.tool_input_available(tc["id"], tc["name"], sse_input)

                    try:
                        output = await execute_tool(tc["name"], tc["input"])
                    except Exception as exc:
                        output = {"error": f"{type(exc).__name__}: {exc}"}
                        is_error = True
                    finally:
                        if batch_state.cancelled:
                            completed_projects = [
                                p
                                for p in batch_state.projects
                                if p.status in ("completed", "skipped", "error")
                            ]
                            output = {
                                "cancelled": True,
                                "message": "Batch stopped by user",
                                "results": [
                                    {
                                        "project_id": p.project_id,
                                        "project_name": p.project_name,
                                        "status": p.status,
                                        **(
                                            {"epc_contractor": p.epc_contractor}
                                            if p.epc_contractor
                                            else {}
                                        ),
                                        **({"confidence": p.confidence} if p.confidence else {}),
                                    }
                                    for p in completed_projects
                                ],
                                "total": batch_state.total,
                                "completed": len(completed_projects),
                            }
                        mark_done(batch_id)
                else:
                    try:
                        output = await execute_tool(tc["name"], tc["input"])
                    except Exception as exc:
                        output = {"error": f"{type(exc).__name__}: {exc}"}
                        is_error = True

                if isinstance(output, dict) and "error" in output:
                    is_error = True

                _duration_ms = int((time.monotonic() - _t0) * 1000)

                # Emit tool_completed event after execution
                asyncio.create_task(asyncio.to_thread(
                    db.log_chat_event,
                    conversation_id,
                    iteration,
                    "tool_completed",
                    {
                        "tool_name":    tc["name"],
                        "tool_call_id": tc["id"],
                        "duration_ms":  _duration_ms,
                        "is_error":     is_error,
                    },
                ))

                yield stream_writer.tool_output_available(tc["id"], output)

                serializable_input = {
                    k: v
                    for k, v in tc["input"].items()
                    if not callable(v) and not isinstance(v, asyncio.Event)
                }
                all_parts.append(
                    {
                        "type": "tool-invocation",
                        "toolCallId": tc["id"],
                        "toolName": tc["name"],
                        "input": serializable_input,
                        "output": output,
                    }
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": json.dumps(output, default=str),
                    }
                )
```

- [ ] **Step 8: Emit `agent_finished` + pass tokens to `save_message()`**

Find the end of the loop where we break and save the message (around line 382):

```python
        # No more tool calls — we're done
        break

    yield stream_writer.finish_step()
    yield stream_writer.finish()
    yield stream_writer.done()

    # Persist the assistant message
    db.save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_text,
        parts=all_parts,
    )
```

Replace with:

```python
        # No more tool calls — we're done
        asyncio.create_task(asyncio.to_thread(
            db.log_chat_event,
            conversation_id,
            iteration,
            "agent_finished",
            {
                "total_input_tokens":  total_usage["input_tokens"],
                "total_output_tokens": total_usage["output_tokens"],
                "iterations":          iteration,
            },
        ))
        break

    yield stream_writer.finish_step()
    yield stream_writer.finish()
    yield stream_writer.done()

    # Persist the assistant message with token summary
    db.save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_text,
        parts=all_parts,
        input_tokens=total_usage["input_tokens"] or None,
        output_tokens=total_usage["output_tokens"] or None,
        cache_read_tokens=total_usage["cache_read_tokens"] or None,
        cache_write_tokens=total_usage["cache_write_tokens"] or None,
        iterations=iteration,
    )
```

- [ ] **Step 9: Run the new tests**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest tests/test_chat_agent.py::TestChatAgentEventLogging -v
```

Expected: 3 tests pass.

- [ ] **Step 10: Run full suite**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
git add agent/src/chat_agent.py agent/tests/test_chat_agent.py
git commit -m "feat: emit chat_events and accumulate token usage in chat_agent loop"
```

---

## Task 4: Fix `_handle_report_findings` token passthrough

**Files:**
- Modify: `agent/src/chat_agent.py` (lines 37-63, the `_handle_report_findings` helper)

The `_handle_report_findings` function currently calls `db.store_discovery(..., total_tokens=0, ...)`. It runs inside the tool loop where we now have `total_usage` available, so we can pass the accumulated count in.

- [ ] **Step 1: Update `_handle_report_findings` to accept total_tokens**

Replace the current function (lines 37–63):

```python
async def _handle_report_findings(tool_input: dict, total_tokens: int = 0) -> dict:
    """When the chat agent calls report_findings, store the discovery.

    The tool_input must include a _project_id injected by the agent's
    earlier search_projects call. If missing, we just record the finding
    without DB storage.
    """
    result = parse_report_findings(tool_input)

    project_id = tool_input.get("_project_id")
    if project_id:
        project = db.get_project(project_id)
        if project:
            discovery = db.store_discovery(
                project_id, result, agent_log=[], total_tokens=total_tokens, project=project
            )
            return {
                "status": "recorded",
                "discovery_id": discovery.get("id") if discovery else None,
            }

    return {
        "status": "recorded",
        "note": "No project_id provided — finding recorded in conversation only.",
    }
```

- [ ] **Step 2: Pass `total_tokens` at the call site**

In the tool loop (Task 3, Step 7), find:

```python
                if tc["name"] == "report_findings":
                    output = await _handle_report_findings(tc["input"])
```

Replace with:

```python
                if tc["name"] == "report_findings":
                    output = await _handle_report_findings(
                        tc["input"],
                        total_tokens=total_usage["input_tokens"] + total_usage["output_tokens"],
                    )
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
git add agent/src/chat_agent.py
git commit -m "fix: pass accumulated token count to store_discovery from report_findings"
```

---

## Task 5: `agent_runtime.py` — extend token accumulation to include cache tokens

**Files:**
- Modify: `agent/src/runtime/agent_runtime.py`

The system-reminder shows `agent_runtime.py` already has a basic `total_usage` dict tracking `input_tokens` and `output_tokens`. It's missing `cache_read_tokens` and `cache_write_tokens`. Extend it to match the full 4-field schema.

- [ ] **Step 1: Find and update the total_usage initialisation**

In `agent/src/runtime/agent_runtime.py`, find:

```python
        total_usage = {"input_tokens": 0, "output_tokens": 0}
```

Replace with:

```python
        total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
```

- [ ] **Step 2: Update the accumulation block**

Find:

```python
            # Track usage
            if response.usage:
                total_usage["input_tokens"] += getattr(response.usage, "input_tokens", 0)
                total_usage["output_tokens"] += getattr(response.usage, "output_tokens", 0)
```

Replace with:

```python
            # Track usage
            if response.usage:
                u = response.usage
                total_usage["input_tokens"]       += getattr(u, "input_tokens", 0)
                total_usage["output_tokens"]      += getattr(u, "output_tokens", 0)
                total_usage["cache_read_tokens"]  += getattr(u, "cache_read_input_tokens", 0)
                total_usage["cache_write_tokens"] += getattr(u, "cache_creation_input_tokens", 0)
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/agent
python -m pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
git add agent/src/runtime/agent_runtime.py
git commit -m "feat: add cache token tracking to agent_runtime total_usage"
```

---

## Verification

After all tasks are complete and the migration is applied to Supabase, do a manual smoke test:

- [ ] Start a chat conversation in the UI and run a tool-heavy query (e.g. "research [some EPC project]")
- [ ] After the response appears, open the Supabase SQL editor and run:

```sql
SELECT event_type, turn_number, data, created_at
FROM chat_events
ORDER BY created_at DESC
LIMIT 20;
```

Expected: rows with `turn_started`, `tool_called`, `tool_completed`, `turn_completed`, `agent_finished` in order.

- [ ] Verify token columns are populated on `chat_messages`:

```sql
SELECT id, role, input_tokens, output_tokens, iterations
FROM chat_messages
WHERE role = 'assistant'
ORDER BY created_at DESC
LIMIT 5;
```

Expected: `input_tokens` and `output_tokens` are non-null integers.
