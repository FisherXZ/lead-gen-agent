"""SSE encoder implementing the Vercel AI SDK UI Message Stream Protocol.

Each method returns a formatted SSE data line: `data: {json}\n\n`
The frontend (@ai-sdk/react useChat) parses these via EventSourceParser
and validates against a strict Zod schema — no extra fields allowed.
"""

from __future__ import annotations

import json


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class StreamWriter:
    """Builds SSE events for the Vercel AI SDK UI Message Stream Protocol."""

    def __init__(self) -> None:
        self._part_counter = 0

    def _next_id(self) -> str:
        pid = str(self._part_counter)
        self._part_counter += 1
        return pid

    # -- Message lifecycle --------------------------------------------------

    def start(self, message_id: str | None = None) -> str:
        payload: dict = {"type": "start"}
        if message_id:
            payload["messageId"] = message_id
        return _event(payload)

    def start_step(self) -> str:
        return _event({"type": "start-step"})

    def finish_step(self) -> str:
        return _event({"type": "finish-step"})

    def finish(self, finish_reason: str = "stop") -> str:
        return _event({"type": "finish", "finishReason": finish_reason})

    def done(self) -> str:
        return "data: [DONE]\n\n"

    # -- Text streaming -----------------------------------------------------

    def text_start(self, part_id: str | None = None) -> str:
        return _event({"type": "text-start", "id": part_id or self._next_id()})

    def text_delta(self, part_id: str, delta: str) -> str:
        return _event({"type": "text-delta", "id": part_id, "delta": delta})

    def text_end(self, part_id: str) -> str:
        return _event({"type": "text-end", "id": part_id})

    # -- Thinking (reasoning before tool calls) --------------------------------

    def thinking_start(self, part_id: str | None = None) -> str:
        return _event({"type": "thinking-start", "id": part_id or self._next_id()})

    def thinking_delta(self, part_id: str, delta: str) -> str:
        return _event({"type": "thinking-delta", "id": part_id, "delta": delta})

    def thinking_end(self, part_id: str) -> str:
        return _event({"type": "thinking-end", "id": part_id})

    # -- Tool invocations ---------------------------------------------------

    def tool_input_start(self, tool_call_id: str, tool_name: str) -> str:
        return _event(
            {
                "type": "tool-input-start",
                "toolCallId": tool_call_id,
                "toolName": tool_name,
            }
        )

    def tool_input_available(self, tool_call_id: str, tool_name: str, input_data: dict) -> str:
        return _event(
            {
                "type": "tool-input-available",
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "input": input_data,
            }
        )

    def tool_output_available(self, tool_call_id: str, output: dict | list | str) -> str:
        return _event(
            {
                "type": "tool-output-available",
                "toolCallId": tool_call_id,
                "output": output,
            }
        )

    # -- Convenience helpers -----------------------------------------------

    def text(self, content: str) -> str:
        """Emit a complete text block (start + delta + end) as a single string."""
        part_id = self._next_id()
        return (
            self.text_start(part_id)
            + self.text_delta(part_id, content)
            + self.text_end(part_id)
        )

    def error(self, message: str) -> str:
        """Emit an error event."""
        return _event({"type": "error", "error": message})
