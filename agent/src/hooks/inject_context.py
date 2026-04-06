"""InjectContextHook — auto-inject conversation/session IDs into tools."""

from __future__ import annotations

from ..runtime import Hook, HookAction, RunContext

_NEEDS_CONVERSATION_ID = {"remember", "recall"}
_NEEDS_SESSION_ID = {"manage_todo", "research_scratchpad"}


class InjectContextHook(Hook):
    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction:
        modified = dict(tool_input)
        if tool_name in _NEEDS_CONVERSATION_ID:
            modified["_conversation_id"] = context.conversation_id
        if tool_name in _NEEDS_SESSION_ID:
            modified.setdefault("session_id", context.session_id)
        return HookAction.continue_with(modified)

    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict:
        return result
