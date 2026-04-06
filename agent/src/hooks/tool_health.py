"""ToolHealthHook — track consecutive tool failures."""

from __future__ import annotations

from ..runtime import Hook, HookAction, RunContext


class ToolHealthHook(Hook):
    def __init__(self, error_threshold: int = 3):
        self.error_threshold = error_threshold
        self._consecutive_errors = 0

    def reset(self) -> None:
        """Reset error counter. Call at the start of each turn."""
        self._consecutive_errors = 0

    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction:
        return HookAction.continue_with(tool_input)

    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict:
        if isinstance(result, dict) and "error" in result:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self.error_threshold:
                result["_guidance"] = (
                    f"{self._consecutive_errors} consecutive tool errors. "
                    "Consider switching to a different tool or approach."
                )
        else:
            self._consecutive_errors = 0
        return result
