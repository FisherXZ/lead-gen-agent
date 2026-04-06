"""RateLimitHook — per-tool call limits within a turn."""
from __future__ import annotations
from ._protocol_stub import Hook, HookAction, RunContext

_DEFAULT_LIMITS = {"remember": 5}

class RateLimitHook(Hook):
    def __init__(self, limits: dict[str, int] | None = None):
        self.limits = limits or dict(_DEFAULT_LIMITS)

    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction:
        limit = self.limits.get(tool_name)
        if limit is None:
            return HookAction.continue_with(tool_input)
        count = context.tool_history.count(tool_name)
        if count >= limit:
            return HookAction.deny(f"Rate limit: max {limit} {tool_name} calls per turn. Already called {count} times.")
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name: str, tool_input: dict, result: dict, context: RunContext) -> dict:
        return result
