"""Core agent runtime — the single loop that powers all agent modes.

AgentRuntime takes a configuration (system prompt, tools, hooks, compactor,
escalation policy) and runs a turn: call Claude, execute tools, run hooks,
compact context, evaluate escalation, repeat until done.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import anthropic

from .compactor import Compactor
from .escalation import EscalationPolicy
from .hooks import Hook, run_pre_hooks, run_post_hooks
from .types import Action, HookAction, RunContext, TurnResult

_logger = logging.getLogger(__name__)


class AgentRuntime:
    """Generic agent runtime. Chat and research are configurations of this."""

    def __init__(
        self,
        system_prompt: str,
        tools: list[dict],
        hooks: list[Hook],
        compactor: Compactor,
        escalation: EscalationPolicy,
        api_key: str | None = None,
        model: str | None = None,
        conversation_id: str = "",
        session_id: str = "",
        user_id: str = "",
    ):
        self.system_prompt = system_prompt
        self.tools = tools
        self.hooks = hooks
        self.compactor = compactor
        self.escalation = escalation
        self.model = model or os.environ.get("CHAT_MODEL", "claude-sonnet-4-6")
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.user_id = user_id
        self._client: anthropic.AsyncAnthropic | None = None

    async def run_turn(
        self,
        messages: list[dict],
        on_event: Callable[[dict], Any],
    ) -> TurnResult:
        """Run a single turn: user message -> fully resolved assistant response.

        The loop continues until the model stops calling tools, the escalation
        policy intervenes, or max iterations is reached.
        """
        # Compact context if needed
        messages = await self.compactor.maybe_compact(messages)

        tool_history: list[str] = []
        total_usage = {"input_tokens": 0, "output_tokens": 0}
        iteration = 0

        while True:
            iteration += 1

            # Call Claude
            response = await self._call_api(messages)

            # Track usage
            if response.usage:
                total_usage["input_tokens"] += getattr(response.usage, "input_tokens", 0)
                total_usage["output_tokens"] += getattr(response.usage, "output_tokens", 0)

            # If no tool calls, we're done
            if response.stop_reason == "end_turn":
                # Append assistant message
                messages.append({
                    "role": "assistant",
                    "content": self._extract_content_blocks(response),
                })
                break

            # Extract tool calls
            tool_uses = [
                block for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]

            if not tool_uses:
                # No tool calls despite stop_reason != end_turn — treat as done
                messages.append({
                    "role": "assistant",
                    "content": self._extract_content_blocks(response),
                })
                break

            # Append assistant message with tool_use blocks
            messages.append({
                "role": "assistant",
                "content": response.content,
            })

            # Execute each tool call
            context = RunContext(
                conversation_id=self.conversation_id,
                session_id=self.session_id,
                user_id=self.user_id,
                iteration=iteration,
                tool_history=tool_history,
                messages=messages,
            )

            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input if isinstance(tool_use.input, dict) else {}
                tool_id = tool_use.id

                # Pre-hooks
                hook_action = await run_pre_hooks(self.hooks, tool_name, tool_input, context)

                if hook_action.kind == "deny":
                    result = {"error": hook_action.reason, "_denied_by_hook": True}
                elif hook_action.kind == "escalate":
                    on_event({"type": "escalation", "message": hook_action.message})
                    result = {"_escalated": True, "message": hook_action.message}
                else:
                    # Execute tool
                    effective_input = hook_action.modified_input or tool_input
                    result = await self._execute_tool(tool_name, effective_input)

                # Post-hooks
                result = await run_post_hooks(self.hooks, tool_name, tool_input, result, context)

                tool_history.append(tool_name)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, default=str),
                })

                # Emit event
                on_event({"type": "tool_result", "tool_name": tool_name, "result": result})

            # Append tool results as user message
            messages.append({"role": "user", "content": tool_results})

            # Evaluate escalation
            action = self.escalation.evaluate(messages, iteration, tool_history)

            if action.kind == "hard_stop":
                on_event({"type": "hard_stop", "reason": action.reason})
                break
            elif action.kind == "escalate_to_user":
                on_event({
                    "type": "escalation",
                    "tried": action.tried,
                    "suggestion": action.suggestion,
                })
                break
            elif action.kind == "inject_guidance":
                # Inject guidance as a separate user message (not a synthetic
                # tool_result, which would violate the API contract requiring
                # every tool_result to reference a real tool_use_id).
                messages.append({
                    "role": "user",
                    "content": f"[Runtime guidance]: {action.message}",
                })

            # Compact again if context grew
            messages = await self.compactor.maybe_compact(messages)

        return TurnResult(
            messages=messages,
            usage=total_usage,
            iterations=iteration,
        )

    async def _call_api(self, messages: list[dict]):
        """Call the Anthropic API. Separated for testability."""
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        client = self._client

        # Apply prompt caching
        cached_system = [{
            "type": "text",
            "text": self.system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]

        cached_tools = list(self.tools)
        if cached_tools:
            cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

        return await client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=cached_system,
            tools=cached_tools if cached_tools else anthropic.NOT_GIVEN,
            messages=messages,
        )

    async def _execute_tool(self, name: str, tool_input: dict) -> dict:
        """Dispatch to the tool registry. Separated for testability."""
        from ..tools import execute_tool
        return await execute_tool(name, tool_input)

    def _extract_content_blocks(self, response) -> list[dict]:
        """Convert response content blocks to serializable dicts."""
        blocks = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                blocks.append({"type": "text", "text": block.text})
            elif getattr(block, "type", None) == "tool_use":
                blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        return blocks
