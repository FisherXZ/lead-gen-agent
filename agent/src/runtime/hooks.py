"""Hook protocol for tool lifecycle interception."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import HookAction, RunContext


class Hook(ABC):
    @abstractmethod
    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction: ...

    @abstractmethod
    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict: ...


async def run_pre_hooks(
    hooks: list[Hook], tool_name: str, tool_input: dict, context: RunContext
) -> HookAction:
    current_input = tool_input
    for hook in hooks:
        action = await hook.pre_tool(tool_name, current_input, context)
        if action.kind in ("deny", "escalate"):
            return action
        if action.modified_input is not None:
            current_input = action.modified_input
    return HookAction.continue_with(current_input)


async def run_post_hooks(
    hooks: list[Hook], tool_name: str, tool_input: dict, result: dict, context: RunContext
) -> dict:
    current_result = result
    for hook in hooks:
        current_result = await hook.post_tool(tool_name, tool_input, current_result, context)
    return current_result
