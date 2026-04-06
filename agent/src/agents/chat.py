"""Chat agent configuration — interactive chat with all tools."""

from __future__ import annotations

from ..hooks import (
    BatchTrackingHook,
    DiscoveryHook,
    InjectContextHook,
    RateLimitHook,
    ToolHealthHook,
)
from ..prompts import CHAT_SYSTEM_PROMPT
from ..runtime import AgentRuntime, EscalationPolicy
from ..runtime.compactor import HeuristicCompactor
from ..tools import get_all_tools


def build_chat_runtime(
    conversation_id: str,
    user_id: str,
    api_key: str | None = None,
    model: str | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=get_all_tools(),
        hooks=[
            InjectContextHook(),
            RateLimitHook(),
            DiscoveryHook(),
            ToolHealthHook(),
            BatchTrackingHook(),
        ],
        compactor=HeuristicCompactor(max_tokens=80_000, preserve_recent=6),
        escalation=EscalationPolicy(max_iterations=50, escalation_mode="user"),
        api_key=api_key,
        model=model,
        conversation_id=conversation_id,
        session_id=conversation_id,
        user_id=user_id,
    )
