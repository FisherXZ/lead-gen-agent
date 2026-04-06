"""Data classes for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnResult:
    """Result of a single agent turn (user message -> resolved response)."""

    messages: list[dict]
    usage: dict
    events: list[dict] = field(default_factory=list)
    iterations: int = 0


@dataclass
class RunContext:
    """Contextual info passed to hooks during tool execution."""

    conversation_id: str
    session_id: str
    user_id: str
    iteration: int
    tool_history: list[str]
    messages: list[dict]


@dataclass
class HookAction:
    """Result of a pre-tool hook."""

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


@dataclass
class Action:
    """Result of escalation policy evaluation."""

    kind: str
    message: str | None = None
    reason: str | None = None
    tried: list[str] = field(default_factory=list)
    suggestion: str | None = None

    @classmethod
    def keep_going(cls) -> Action:
        return cls(kind="continue")

    @classmethod
    def inject_guidance(cls, message: str) -> Action:
        return cls(kind="inject_guidance", message=message)

    @classmethod
    def escalate_to_user(cls, tried: list[str], suggestion: str) -> Action:
        return cls(kind="escalate_to_user", tried=tried, suggestion=suggestion)

    @classmethod
    def hard_stop(cls, reason: str) -> Action:
        return cls(kind="hard_stop", reason=reason)
