"""Chat agent: unified Claude agent with all tools.

Streams responses as SSE events using the Vercel AI SDK protocol so
the React frontend can render text + interactive tool-result components.

The chat agent has direct access to ALL tools — web search, page fetching,
project DB queries, knowledge base, and EPC reporting. When a user asks
to research a project, the agent searches the web itself (no delegation
to a sub-agent). User hints and conversation context flow naturally into
the research.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator

import anthropic

from . import db
from .batch_progress import create_batch, get_cancel_event, mark_done, update_project
from .parsing import parse_report_findings
from .prompts import CHAT_SYSTEM_PROMPT
from .sse import StreamWriter
from .tools import execute_tool, get_all_tools

MODEL = os.environ.get("CHAT_MODEL", "claude-sonnet-4-6")
MAX_TOOL_ROUNDS = 15
TOOL_TIMEOUT_SECONDS = 60  # Per-tool execution timeout

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool result post-processing
# ---------------------------------------------------------------------------


async def _handle_report_findings(tool_input: dict, total_tokens: int = 0) -> dict:
    """When the chat agent calls report_findings, store the discovery.

    The tool_input must include a _project_id injected by the agent's
    earlier search_projects call. If missing, we just record the finding
    without DB storage.
    """
    result = parse_report_findings(tool_input)

    # Try to find the project this is about from the tool input
    # The agent should include the project_id in report_findings context
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


# ---------------------------------------------------------------------------
# Batch progress formatting
# ---------------------------------------------------------------------------


def _format_batch_progress(update: dict) -> str | None:
    """Format a batch progress update as a text line for SSE streaming."""
    status = update.get("status", "")
    name = update.get("project_name", update.get("project_id", ""))

    if status == "started":
        return f"\n- Researching {name}..."
    elif status == "completed":
        disc = update.get("discovery", {})
        epc = disc.get("epc_contractor", "Unknown")
        conf = disc.get("confidence", "unknown")
        return f"\n- {name} — {epc} ({conf})"
    elif status == "skipped":
        return f"\n- {name} — skipped (already researched)"
    elif status == "error":
        return f"\n- {name} — error"
    return None


# ---------------------------------------------------------------------------
# Streaming chat agent
# ---------------------------------------------------------------------------


async def run_chat_agent(
    messages: list[dict],
    conversation_id: str,
    stream_writer: StreamWriter,
    api_key: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run the chat agent, yielding SSE events.

    Args:
        messages: Conversation history as [{role, content}, ...].
        conversation_id: For DB persistence.
        stream_writer: SSE protocol encoder.
        api_key: Optional user-provided Anthropic API key.

    Yields:
        SSE-formatted strings for the frontend.
    """
    from .db import get_anthropic_client

    client = get_anthropic_client(api_key)

    # Get all tools from the shared registry
    all_tools = get_all_tools()

    # Cache system prompt + tools to reduce input token costs (~90% savings)
    cached_system = [
        {
            "type": "text",
            "text": CHAT_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    cached_tools = [*all_tools[:-1], {**all_tools[-1], "cache_control": {"type": "ephemeral"}}]

    message_id = str(uuid.uuid4())
    yield stream_writer.start(message_id)
    yield stream_writer.start_step()

    # Convert messages to Anthropic format
    # Content may be a string (text-only) or list of content blocks (multimodal)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    # Strip file data from older messages to save context (keep only the last user message's files)
    for i, msg in enumerate(api_messages[:-1]):
        content = msg.get("content")
        if isinstance(content, list):
            api_messages[i] = {
                "role": msg["role"],
                "content": [
                    b
                    if b.get("type") == "text"
                    else {"type": "text", "text": f"[Attached {b.get('type', 'file')}]"}
                    for b in content
                ],
            }

    full_text = ""
    all_parts: list[dict] = []

    # Compact old tool outputs if conversation history is large
    from .compaction import compact_messages

    api_messages = compact_messages(api_messages)

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
        asyncio.create_task(asyncio.to_thread(
            db.log_chat_event,
            conversation_id,
            iteration,
            "turn_started",
            {"turn_number": iteration, "model": MODEL},
        ))
        # Stream the response
        tool_calls: list[dict] = []
        current_tool_input = ""
        current_text_part_id: str | None = None
        # In rounds after a tool round, text is "thinking" (reasoning between tools)
        is_thinking_round = had_tool_rounds

        async with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=cached_system,
            tools=cached_tools,
            messages=api_messages,
        ) as stream:
            async for event in stream:
                # --- Text streaming ---
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        current_text_part_id = str(len(all_parts))
                        if is_thinking_round:
                            yield stream_writer.thinking_start(current_text_part_id)
                        else:
                            yield stream_writer.text_start(current_text_part_id)

                    elif event.content_block.type == "tool_use":
                        tool_calls.append(
                            {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input": {},
                            }
                        )
                        current_tool_input = ""
                        yield stream_writer.tool_input_start(
                            event.content_block.id,
                            event.content_block.name,
                        )

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta" and current_text_part_id is not None:
                        full_text += event.delta.text
                        if is_thinking_round:
                            yield stream_writer.thinking_delta(
                                current_text_part_id, event.delta.text
                            )
                        else:
                            yield stream_writer.text_delta(current_text_part_id, event.delta.text)

                    elif event.delta.type == "input_json_delta":
                        current_tool_input += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if current_text_part_id is not None:
                        if is_thinking_round:
                            yield stream_writer.thinking_end(current_text_part_id)
                        else:
                            yield stream_writer.text_end(current_text_part_id)
                        all_parts.append({"type": "text", "text": full_text})
                        current_text_part_id = None

                    elif tool_calls:
                        # Parse accumulated JSON input
                        tc = tool_calls[-1]
                        try:
                            tc["input"] = (
                                json.loads(current_tool_input) if current_tool_input else {}
                            )
                        except json.JSONDecodeError:
                            tc["input"] = {}

                        yield stream_writer.tool_input_available(tc["id"], tc["name"], tc["input"])

            # Get the final message for stop_reason
            response = await stream.get_final_message()

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
                "turn_number":        iteration,
                "input_tokens":       getattr(response.usage, "input_tokens", 0) if response.usage else 0,
                "output_tokens":      getattr(response.usage, "output_tokens", 0) if response.usage else 0,
                "cache_read_tokens":  getattr(response.usage, "cache_read_input_tokens", 0) if response.usage else 0,
                "cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) if response.usage else 0,
                "stop_reason":        response.stop_reason,
            },
        ))

        # Execute any tool calls
        if response.stop_reason == "tool_use" and tool_calls:
            had_tool_rounds = True
            tool_results = []
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
                    output = await _handle_report_findings(
                        tc["input"],
                        total_tokens=total_usage["input_tokens"] + total_usage["output_tokens"],
                    )
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

                    # Inject batch_id into tool input so frontend knows
                    # which progress endpoint to connect to
                    tc["input"]["_batch_id"] = batch_id
                    tc["input"]["_project_names"] = {
                        p["id"]: p.get("project_name") or p.get("queue_id", p["id"])
                        for p in batch_projects
                    }

                    # Progress callback updates the in-memory store
                    # Default arg captures batch_id by value (not reference)
                    async def _on_progress(update: dict, _bid: str = batch_id):
                        update_project(_bid, update)

                    tc["input"]["_progress_callback"] = _on_progress
                    tc["input"]["_cancel_event"] = get_cancel_event(batch_id)

                    # Re-emit tool-input-available with enriched input
                    # (so frontend gets _batch_id before tool completes)
                    # Strip non-serializable internal objects before SSE emission
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
                        # If cancelled, build partial results from batch state
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

                # Strip non-serializable internal objects from persisted input
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

            # Feed results back and loop
            api_messages.append({"role": "assistant", "content": response.content})
            api_messages.append({"role": "user", "content": tool_results})

            # Start a new step for the next round
            yield stream_writer.finish_step()
            yield stream_writer.start_step()

            # Reset for next round
            tool_calls = []
            full_text = ""
            continue

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
