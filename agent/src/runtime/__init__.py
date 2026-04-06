"""Generic agent runtime engine.

Provides AgentRuntime — a configurable turn loop with context compaction,
tool hooks, and escalation policies. Chat and research modes are
configurations of this single runtime.
"""

from .types import TurnResult, RunContext, HookAction, Action
from .hooks import Hook
from .compactor import Compactor
from .escalation import EscalationPolicy
from .agent_runtime import AgentRuntime

__all__ = [
    "AgentRuntime",
    "TurnResult",
    "RunContext",
    "HookAction",
    "Action",
    "Hook",
    "Compactor",
    "EscalationPolicy",
]
