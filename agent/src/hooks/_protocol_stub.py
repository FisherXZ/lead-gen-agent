"""Local stub of runtime types for parallel development."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class RunContext:
    conversation_id: str = ""
    session_id: str = ""
    user_id: str = ""
    iteration: int = 0
    tool_history: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)

@dataclass
class HookAction:
    kind: str
    modified_input: dict | None = None
    reason: str | None = None
    message: str | None = None

    @classmethod
    def continue_with(cls, modified_input: dict) -> HookAction:
        return cls(kind="continue", modified_input=modified_input)

    @classmethod
    def deny(cls, reason: str) -> HookAction:
        return cls(kind="deny", reason=reason)

    @classmethod
    def escalate(cls, message: str) -> HookAction:
        return cls(kind="escalate", message=message)

class Hook(ABC):
    @abstractmethod
    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction: ...
    @abstractmethod
    async def post_tool(self, tool_name: str, tool_input: dict, result: dict, context: RunContext) -> dict: ...
