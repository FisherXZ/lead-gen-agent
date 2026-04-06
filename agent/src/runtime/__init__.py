"""Generic agent runtime engine.

Provides AgentRuntime — a configurable turn loop with context compaction,
tool hooks, and escalation policies. Chat and research modes are
configurations of this single runtime.
"""

from .agent_runtime import AgentRuntime
from .compactor import Compactor
from .escalation import EscalationPolicy
from .hooks import Hook
from .types import Action, HookAction, RunContext, TurnResult

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
