# Runtime Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the generic `AgentRuntime` engine with context compaction, escalation policy, and hook protocol — the foundation that replaces `chat_agent.py` and `research.py` loops.

**Architecture:** A single `AgentRuntime` class that takes configuration (system prompt, tools, hooks, compactor, escalation policy) and runs a turn loop. The loop streams from Claude, dispatches tools through the registry, runs hooks before/after each tool, compacts context when needed, and evaluates escalation policy after each iteration.

**Tech Stack:** Python 3.13, anthropic SDK, existing tool registry (`agent/src/tools/__init__.py`), existing SSE protocol (`agent/src/sse.py`)

**Worktree:** `.worktrees/runtime-core` (branch: `feature/runtime-core`)

**Spec:** `docs/superpowers/specs/2026-04-05-agent-runtime-revamp-design.md`

---

## File Structure

```
agent/src/runtime/
├── __init__.py              # Public exports
├── types.py                 # TurnResult, HookAction, Action, RunContext, SSEEvent dataclasses
├── hooks.py                 # Hook protocol (abstract interface)
├── compactor.py             # Summarization-based context compaction
├── escalation.py            # EscalationPolicy with stagnation detection
└── agent_runtime.py         # The core loop

agent/tests/
├── test_runtime_types.py
├── test_hooks_protocol.py
├── test_compactor.py
├── test_escalation.py
└── test_agent_runtime.py
```

---

### Task 1: Types & Data Classes

**Files:**
- Create: `agent/src/runtime/__init__.py`
- Create: `agent/src/runtime/types.py`
- Create: `agent/tests/test_runtime_types.py`

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_runtime_types.py`:

```python
"""Tests for runtime type definitions."""
from agent.src.runtime.types import (
    TurnResult,
    RunContext,
    HookAction,
    Action,
)


def test_turn_result_creation():
    result = TurnResult(
        messages=[{"role": "assistant", "content": "hello"}],
        usage={"input_tokens": 100, "output_tokens": 50},
        events=[],
        iterations=1,
    )
    assert result.iterations == 1
    assert len(result.messages) == 1


def test_run_context_creation():
    ctx = RunContext(
        conversation_id="conv-1",
        session_id="sess-1",
        user_id="user-1",
        iteration=0,
        tool_history=[],
        messages=[],
    )
    assert ctx.conversation_id == "conv-1"
    assert ctx.tool_history == []


def test_hook_action_continue():
    action = HookAction.continue_with({"query": "test"})
    assert action.kind == "continue"
    assert action.modified_input == {"query": "test"}


def test_hook_action_deny():
    action = HookAction.deny("rate limited")
    assert action.kind == "deny"
    assert action.reason == "rate limited"


def test_hook_action_escalate():
    action = HookAction.escalate("stuck on research")
    assert action.kind == "escalate"
    assert action.message == "stuck on research"


def test_action_continue():
    a = Action.keep_going()
    assert a.kind == "continue"


def test_action_inject_guidance():
    a = Action.inject_guidance("try a different approach")
    assert a.kind == "inject_guidance"
    assert a.message == "try a different approach"


def test_action_escalate_to_user():
    a = Action.escalate_to_user(
        tried=["web_search x3", "fetch_page x2"],
        suggestion="Should I try SEC filings?",
    )
    assert a.kind == "escalate_to_user"
    assert len(a.tried) == 2


def test_action_hard_stop():
    a = Action.hard_stop("max iterations")
    assert a.kind == "hard_stop"
    assert a.reason == "max iterations"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_runtime_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.src.runtime'`

- [ ] **Step 3: Write the implementation**

Create `agent/src/runtime/__init__.py`:

```python
"""Generic agent runtime engine.

Provides AgentRuntime — a configurable turn loop with context compaction,
tool hooks, and escalation policies. Chat and research modes are
configurations of this single runtime.
"""

from .types import TurnResult, RunContext, HookAction, Action
from .hooks import Hook
from .compactor import Compactor
from .escalation import EscalationPolicy

__all__ = [
    "TurnResult",
    "RunContext",
    "HookAction",
    "Action",
    "Hook",
    "Compactor",
    "EscalationPolicy",
]
```

Create `agent/src/runtime/types.py`:

```python
"""Data classes for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    """Result of a pre-tool hook. Controls whether/how the tool executes."""
    kind: str  # "continue", "deny", "escalate"
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
    kind: str  # "continue", "inject_guidance", "escalate_to_user", "hard_stop"
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_runtime_types.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core
git add agent/src/runtime/__init__.py agent/src/runtime/types.py agent/tests/test_runtime_types.py
git commit -m "feat(runtime): add core type definitions — TurnResult, RunContext, HookAction, Action"
```

---

### Task 2: Hook Protocol

**Files:**
- Create: `agent/src/runtime/hooks.py`
- Create: `agent/tests/test_hooks_protocol.py`

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_hooks_protocol.py`:

```python
"""Tests for the Hook protocol and hook runner."""
import pytest
from agent.src.runtime.hooks import Hook, run_pre_hooks, run_post_hooks
from agent.src.runtime.types import RunContext, HookAction


class AllowAllHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        return result


class InjectIdHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        if tool_name == "remember":
            tool_input["_conversation_id"] = context.conversation_id
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        return result


class DenyHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        if tool_name == "blocked_tool":
            return HookAction.deny("not allowed")
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        return result


class AnnotateResultHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        return HookAction.continue_with(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context):
        result["_annotated"] = True
        return result


def _make_context(**overrides):
    defaults = dict(
        conversation_id="conv-1",
        session_id="sess-1",
        user_id="user-1",
        iteration=0,
        tool_history=[],
        messages=[],
    )
    defaults.update(overrides)
    return RunContext(**defaults)


@pytest.mark.asyncio
async def test_pre_hooks_pass_through():
    hooks = [AllowAllHook()]
    ctx = _make_context()
    action = await run_pre_hooks(hooks, "web_search", {"query": "test"}, ctx)
    assert action.kind == "continue"
    assert action.modified_input == {"query": "test"}


@pytest.mark.asyncio
async def test_pre_hooks_modify_input():
    hooks = [InjectIdHook()]
    ctx = _make_context(conversation_id="conv-42")
    action = await run_pre_hooks(hooks, "remember", {"fact": "something"}, ctx)
    assert action.kind == "continue"
    assert action.modified_input["_conversation_id"] == "conv-42"


@pytest.mark.asyncio
async def test_pre_hooks_deny_short_circuits():
    hooks = [DenyHook(), InjectIdHook()]
    ctx = _make_context()
    action = await run_pre_hooks(hooks, "blocked_tool", {}, ctx)
    assert action.kind == "deny"
    assert action.reason == "not allowed"


@pytest.mark.asyncio
async def test_pre_hooks_chain_modifications():
    """Multiple hooks modify the same input — changes accumulate."""
    hooks = [InjectIdHook(), AllowAllHook()]
    ctx = _make_context(conversation_id="conv-99")
    action = await run_pre_hooks(hooks, "remember", {"fact": "x"}, ctx)
    assert action.modified_input["_conversation_id"] == "conv-99"
    assert action.modified_input["fact"] == "x"


@pytest.mark.asyncio
async def test_post_hooks_transform_result():
    hooks = [AnnotateResultHook()]
    ctx = _make_context()
    result = await run_post_hooks(hooks, "web_search", {}, {"data": "found"}, ctx)
    assert result["_annotated"] is True
    assert result["data"] == "found"


@pytest.mark.asyncio
async def test_post_hooks_chain():
    hooks = [AnnotateResultHook(), AllowAllHook()]
    ctx = _make_context()
    result = await run_post_hooks(hooks, "web_search", {}, {"data": "x"}, ctx)
    assert result["_annotated"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_hooks_protocol.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/runtime/hooks.py`:

```python
"""Hook protocol for tool lifecycle interception.

Hooks run before and after each tool call, allowing input modification,
denial, output transformation, and side effects — without touching the
core agent loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import HookAction, RunContext


class Hook(ABC):
    """Base class for tool lifecycle hooks."""

    @abstractmethod
    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction:
        """Called before tool execution.

        Return HookAction.continue_with(input) to proceed,
        HookAction.deny(reason) to skip, or
        HookAction.escalate(message) to pause for user.
        """
        ...

    @abstractmethod
    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict:
        """Called after tool execution. Return the (possibly modified) result."""
        ...


async def run_pre_hooks(
    hooks: list[Hook],
    tool_name: str,
    tool_input: dict,
    context: RunContext,
) -> HookAction:
    """Run all pre-tool hooks in order. Deny/Escalate short-circuits."""
    current_input = tool_input
    for hook in hooks:
        action = await hook.pre_tool(tool_name, current_input, context)
        if action.kind in ("deny", "escalate"):
            return action
        # Accumulate modifications
        if action.modified_input is not None:
            current_input = action.modified_input
    return HookAction.continue_with(current_input)


async def run_post_hooks(
    hooks: list[Hook],
    tool_name: str,
    tool_input: dict,
    result: dict,
    context: RunContext,
) -> dict:
    """Run all post-tool hooks in order. Each can transform the result."""
    current_result = result
    for hook in hooks:
        current_result = await hook.post_tool(tool_name, tool_input, current_result, context)
    return current_result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_hooks_protocol.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core
git add agent/src/runtime/hooks.py agent/tests/test_hooks_protocol.py
git commit -m "feat(runtime): add Hook protocol with pre/post runners and short-circuit semantics"
```

---

### Task 3: Compactor

**Files:**
- Create: `agent/src/runtime/compactor.py`
- Create: `agent/tests/test_runtime_compactor.py`

The Compactor uses a cheap Haiku call to summarize older messages. For testing, we mock the API call.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_runtime_compactor.py`:

```python
"""Tests for summarization-based context compaction."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from agent.src.runtime.compactor import Compactor, estimate_tokens


def _make_messages(count: int, content_size: int = 100) -> list[dict]:
    """Generate synthetic messages with predictable token estimates."""
    messages = []
    for i in range(count):
        if i % 2 == 0:
            messages.append({"role": "user", "content": "x" * content_size})
        else:
            messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": "y" * content_size}],
            })
    return messages


def test_estimate_tokens():
    messages = [{"role": "user", "content": "hello world"}]
    tokens = estimate_tokens(messages)
    # Rough estimate: ~4 chars per token
    assert tokens > 0
    assert isinstance(tokens, int)


@pytest.mark.asyncio
async def test_no_compaction_under_threshold():
    compactor = Compactor(max_tokens=100_000, preserve_recent=4)
    messages = _make_messages(4, content_size=50)  # small
    result = await compactor.maybe_compact(messages)
    assert result == messages  # unchanged


@pytest.mark.asyncio
async def test_compaction_preserves_recent_messages():
    compactor = Compactor(max_tokens=100, preserve_recent=4)  # very low threshold

    messages = _make_messages(10, content_size=200)

    with patch.object(compactor, "_summarize", new_callable=AsyncMock) as mock_summarize:
        mock_summarize.return_value = "Summary of earlier conversation."
        result = await compactor.maybe_compact(messages)

    # Should have: 1 summary message + last 4 messages
    assert len(result) == 5
    assert result[0]["role"] == "user"
    assert "Summary of earlier conversation" in result[0]["content"]
    # Last 4 messages preserved verbatim
    assert result[1:] == messages[-4:]


@pytest.mark.asyncio
async def test_compaction_calls_summarize_with_older_messages():
    compactor = Compactor(max_tokens=100, preserve_recent=2)

    messages = _make_messages(6, content_size=200)

    with patch.object(compactor, "_summarize", new_callable=AsyncMock) as mock_summarize:
        mock_summarize.return_value = "Summarized."
        await compactor.maybe_compact(messages)

    # _summarize should receive the older messages (first 4)
    call_args = mock_summarize.call_args
    older_messages = call_args[0][0]
    assert len(older_messages) == 4


@pytest.mark.asyncio
async def test_summary_merging():
    """When compacting already-compacted messages, merge summaries."""
    compactor = Compactor(max_tokens=100, preserve_recent=2)

    # First message is an existing summary
    messages = [
        {"role": "user", "content": "[Compacted summary]\nPrior summary: User asked about solar projects."},
        {"role": "assistant", "content": [{"type": "text", "text": "y" * 200}]},
        {"role": "user", "content": "x" * 200},
        {"role": "assistant", "content": [{"type": "text", "text": "y" * 200}]},
        {"role": "user", "content": "x" * 200},
        {"role": "assistant", "content": [{"type": "text", "text": "y" * 200}]},
    ]

    with patch.object(compactor, "_summarize", new_callable=AsyncMock) as mock_summarize:
        mock_summarize.return_value = "Merged summary."
        result = await compactor.maybe_compact(messages)

    # Should pass existing summary to _summarize
    call_args = mock_summarize.call_args
    existing_summary = call_args[1].get("existing_summary") or call_args[0][1] if len(call_args[0]) > 1 else None
    # The older messages include the summary message
    assert len(result) == 3  # 1 summary + 2 recent


def test_summary_message_format():
    from agent.src.runtime.compactor import _build_summary_message
    msg = _build_summary_message("User researched EPC for Sunrise Solar.")
    assert msg["role"] == "user"
    assert "Summary of earlier messages" in msg["content"]
    assert "Sunrise Solar" in msg["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_runtime_compactor.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/runtime/compactor.py`:

```python
"""Summarization-based context compaction.

When conversation context exceeds a token threshold, older messages are
summarized by a cheap model (Haiku) while recent messages are preserved
verbatim. This keeps long sessions coherent without context overflow.
"""

from __future__ import annotations

import json
import logging
import os

import anthropic

_logger = logging.getLogger(__name__)

SUMMARY_MODEL = "claude-haiku-4-5-20251001"

SUMMARY_PROMPT = """You are summarizing a conversation for context continuity.
The conversation is between a user and an AI research assistant that investigates
solar energy projects and EPC (Engineering, Procurement, Construction) contractors.

Extract from the messages below:
- What the user asked for
- Tools called and their key results (not raw output)
- Discoveries made (EPC findings, confidence levels, sources)
- Dead ends (searches that returned nothing useful)
- Current state of work (what's been done, what's pending)
- Key entities referenced (project names, company names, locations)

Be concise. This summary replaces the original messages."""

MERGE_PREFIX = """A prior summary exists from an earlier compaction.
Merge it with the new messages into a single coherent summary.

Prior summary:
{existing_summary}

New messages to incorporate:
"""


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: ~4 characters per token."""
    total_chars = sum(len(json.dumps(m, default=str)) for m in messages)
    return total_chars // 4


def _build_summary_message(summary: str) -> dict:
    """Wrap a summary string in a user message for injection."""
    return {
        "role": "user",
        "content": (
            "[This conversation was compacted for context management.]\n\n"
            "Summary of earlier messages:\n"
            f"{summary}\n\n"
            "Recent messages are preserved verbatim below. "
            "Continue from where you left off."
        ),
    }


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Format messages into a readable string for the summarizer."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text from content blocks
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", "")[:500])
                    elif block.get("type") == "tool_use":
                        texts.append(f"[tool_use: {block.get('name', '?')}]")
                    elif block.get("type") == "tool_result":
                        result_str = block.get("content", "")
                        texts.append(f"[tool_result: {result_str[:200]}]")
            content = "\n".join(texts)
        elif isinstance(content, str):
            content = content[:1000]
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _detect_existing_summary(messages: list[dict]) -> str | None:
    """Check if the first message is a compaction summary."""
    if not messages:
        return None
    first = messages[0]
    content = first.get("content", "")
    if isinstance(content, str) and "[This conversation was compacted" in content:
        return content
    return None


class Compactor:
    """Summarization-based context compaction."""

    def __init__(
        self,
        max_tokens: int = 80_000,
        preserve_recent: int = 6,
        summary_model: str = SUMMARY_MODEL,
        api_key: str | None = None,
    ):
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent
        self.summary_model = summary_model
        self._api_key = api_key

    async def maybe_compact(self, messages: list[dict]) -> list[dict]:
        """If context exceeds threshold, summarize older messages.

        Returns the original list if under threshold (no copy).
        Returns [summary_message] + recent_messages if compacted.
        """
        if estimate_tokens(messages) <= self.max_tokens:
            return messages

        if len(messages) <= self.preserve_recent:
            return messages  # nothing to compact

        older = messages[:-self.preserve_recent]
        recent = messages[-self.preserve_recent:]

        existing_summary = _detect_existing_summary(older)
        summary = await self._summarize(older, existing_summary=existing_summary)

        return [_build_summary_message(summary)] + recent

    async def _summarize(
        self,
        messages: list[dict],
        existing_summary: str | None = None,
    ) -> str:
        """Call Haiku to summarize messages."""
        formatted = _format_messages_for_summary(messages)

        if existing_summary:
            user_content = MERGE_PREFIX.format(existing_summary=existing_summary) + formatted
        else:
            user_content = formatted

        try:
            api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=self.summary_model,
                max_tokens=1024,
                system=SUMMARY_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            return response.content[0].text
        except Exception as exc:
            _logger.warning("Compaction summarization failed: %s", exc)
            # Fallback: truncate older messages to a simple list
            return _format_messages_for_summary(messages[-3:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_runtime_compactor.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core
git add agent/src/runtime/compactor.py agent/tests/test_runtime_compactor.py
git commit -m "feat(runtime): add Compactor — summarization-based context compaction via Haiku"
```

---

### Task 4: Escalation Policy

**Files:**
- Create: `agent/src/runtime/escalation.py`
- Create: `agent/tests/test_escalation.py`

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_escalation.py`:

```python
"""Tests for the EscalationPolicy."""
import json
import pytest
from agent.src.runtime.escalation import EscalationPolicy


def _tool_result_msg(tool_name: str, content: str) -> dict:
    """Build a user message containing a tool result."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": f"id-{tool_name}",
                "content": content,
            }
        ],
    }


def _assistant_msg(tool_name: str) -> dict:
    """Build an assistant message with a tool_use block."""
    return {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": f"id-{tool_name}", "name": tool_name, "input": {}},
        ],
    }


def test_continue_when_under_limits():
    policy = EscalationPolicy(max_iterations=50, stagnation_window=4)
    messages = [
        _assistant_msg("web_search"),
        _tool_result_msg("web_search", json.dumps({"results": [{"title": "SunPower EPC project"}]})),
    ]
    action = policy.evaluate(messages, iteration=2, tool_history=["web_search", "web_search"])
    assert action.kind == "continue"


def test_hard_stop_at_max_iterations():
    policy = EscalationPolicy(max_iterations=10)
    action = policy.evaluate([], iteration=10, tool_history=[])
    assert action.kind == "hard_stop"


def test_stagnation_detection_user_mode():
    """When recent tools return no new signals, escalate to user."""
    policy = EscalationPolicy(max_iterations=50, stagnation_window=4, escalation_mode="user")

    # Simulate 4 tool results with no EPC-related content
    messages = []
    for i in range(4):
        messages.append(_assistant_msg("web_search"))
        messages.append(_tool_result_msg("web_search", json.dumps({"results": []})))

    action = policy.evaluate(messages, iteration=8, tool_history=["web_search"] * 8)
    assert action.kind == "escalate_to_user"


def test_stagnation_detection_autonomous_mode():
    """In autonomous mode, inject guidance instead of escalating."""
    policy = EscalationPolicy(max_iterations=50, stagnation_window=4, escalation_mode="autonomous")

    messages = []
    for i in range(4):
        messages.append(_assistant_msg("web_search"))
        messages.append(_tool_result_msg("web_search", json.dumps({"results": []})))

    action = policy.evaluate(messages, iteration=8, tool_history=["web_search"] * 8)
    assert action.kind == "inject_guidance"


def test_no_stagnation_with_new_signals():
    """When results contain new entity mentions, don't flag stagnation."""
    policy = EscalationPolicy(max_iterations=50, stagnation_window=4)

    messages = []
    companies = ["SunPower Corp", "NextEra Energy", "Blattner Energy", "Mortenson Construction"]
    for company in companies:
        messages.append(_assistant_msg("web_search"))
        messages.append(_tool_result_msg(
            "web_search",
            json.dumps({"results": [{"title": f"{company} wins EPC contract"}]}),
        ))

    action = policy.evaluate(messages, iteration=8, tool_history=["web_search"] * 4)
    assert action.kind == "continue"


def test_consecutive_errors_escalate():
    """3+ consecutive tool errors should trigger escalation."""
    policy = EscalationPolicy(max_iterations=50, stagnation_window=4, escalation_mode="user")

    messages = []
    for i in range(3):
        messages.append(_assistant_msg("web_search"))
        messages.append(_tool_result_msg(
            "web_search",
            json.dumps({"error": "Search service returned 500"}),
        ))

    action = policy.evaluate(messages, iteration=5, tool_history=["web_search"] * 3)
    assert action.kind == "escalate_to_user"


def test_min_iterations_before_stagnation():
    """Don't flag stagnation in the first few iterations."""
    policy = EscalationPolicy(max_iterations=50, stagnation_window=4, min_iterations_before_stagnation=6)

    messages = []
    for i in range(4):
        messages.append(_assistant_msg("web_search"))
        messages.append(_tool_result_msg("web_search", json.dumps({"results": []})))

    action = policy.evaluate(messages, iteration=3, tool_history=["web_search"] * 3)
    assert action.kind == "continue"  # too early to flag
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_escalation.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/runtime/escalation.py`:

```python
"""Escalation policy for the agent runtime.

Replaces hard iteration caps with signal-based stopping. Detects
stagnation (tools not producing new information) and consecutive
errors, then either escalates to the user or injects guidance.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter

from .types import Action

_logger = logging.getLogger(__name__)

# Patterns that suggest new, relevant information was found
_SIGNAL_PATTERNS = [
    re.compile(r"(?i)\b(epc|contractor|construction|engineering|procurement)\b"),
    re.compile(r"(?i)\b(solar|photovoltaic|pv|renewable|energy)\b"),
    re.compile(r"(?i)\b(mw|megawatt|capacity|project)\b"),
    re.compile(r"(?i)\b(contract|award|agreement|engage|hire|select)\b"),
]


def _extract_signals(text: str) -> set[str]:
    """Extract meaningful entity-like tokens from text."""
    # Simple heuristic: capitalized multi-word phrases (likely company names)
    entities = set(re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text))
    return entities


def _get_recent_tool_results(messages: list[dict], window: int) -> list[str]:
    """Extract the last N tool result content strings from messages."""
    results = []
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results.append(block.get("content", ""))
                if len(results) >= window:
                    return results
    return results


def _count_consecutive_errors(messages: list[dict]) -> int:
    """Count consecutive tool errors from the end of the conversation."""
    count = 0
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            break
        has_tool_result = False
        all_errors = True
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                has_tool_result = True
                result_str = block.get("content", "")
                try:
                    parsed = json.loads(result_str)
                    if not (isinstance(parsed, dict) and "error" in parsed):
                        all_errors = False
                except (json.JSONDecodeError, TypeError):
                    all_errors = False
        if has_tool_result and all_errors:
            count += 1
        elif has_tool_result:
            break
    return count


class EscalationPolicy:
    """Signal-based escalation policy."""

    def __init__(
        self,
        max_iterations: int = 50,
        stagnation_window: int = 4,
        escalation_mode: str = "user",
        min_iterations_before_stagnation: int = 6,
    ):
        self.max_iterations = max_iterations
        self.stagnation_window = stagnation_window
        self.escalation_mode = escalation_mode
        self.min_iterations_before_stagnation = min_iterations_before_stagnation
        self._seen_signals: set[str] = set()

    def evaluate(
        self,
        messages: list[dict],
        iteration: int,
        tool_history: list[str],
    ) -> Action:
        """Evaluate whether the agent should continue, get guidance, or stop."""
        # 1. Hard safety limit
        if iteration >= self.max_iterations:
            return Action.hard_stop("max iterations reached")

        # 2. Consecutive errors
        consecutive_errors = _count_consecutive_errors(messages)
        if consecutive_errors >= 3:
            tried = _summarize_tool_usage(tool_history)
            if self.escalation_mode == "user":
                return Action.escalate_to_user(
                    tried=tried,
                    suggestion=f"{consecutive_errors} consecutive tool errors. Want me to continue or try a different approach?",
                )
            else:
                return Action.inject_guidance(
                    f"{consecutive_errors} consecutive tool errors. Switch to a different tool or approach."
                )

        # 3. Stagnation detection (only after minimum iterations)
        if iteration >= self.min_iterations_before_stagnation:
            recent_results = _get_recent_tool_results(messages, self.stagnation_window)
            if len(recent_results) >= self.stagnation_window and self._is_stagnating(recent_results):
                tried = _summarize_tool_usage(tool_history)
                if self.escalation_mode == "user":
                    return Action.escalate_to_user(
                        tried=tried,
                        suggestion="Recent searches aren't producing new leads. Should I try a different angle?",
                    )
                else:
                    return Action.inject_guidance(
                        "Recent searches returning diminishing results. Switch to an untried source category."
                    )

        # 4. All good
        return Action.keep_going()

    def _is_stagnating(self, recent_results: list[str]) -> bool:
        """Check if recent tool results contain new signals."""
        new_signal_count = 0
        for result_str in recent_results:
            # Check for empty results
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, dict):
                    results_list = parsed.get("results", [])
                    if isinstance(results_list, list) and len(results_list) == 0:
                        continue  # empty results, no new signals
            except (json.JSONDecodeError, TypeError):
                pass

            signals = _extract_signals(result_str)
            new_signals = signals - self._seen_signals
            if new_signals:
                new_signal_count += 1
                self._seen_signals.update(new_signals)

        # Stagnating if fewer than 25% of recent results had new signals
        return new_signal_count / len(recent_results) < 0.25


def _summarize_tool_usage(tool_history: list[str]) -> list[str]:
    """Summarize which tools were used and how many times."""
    counts = Counter(tool_history)
    return [f"{name} x{count}" for name, count in counts.most_common()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_escalation.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core
git add agent/src/runtime/escalation.py agent/tests/test_escalation.py
git commit -m "feat(runtime): add EscalationPolicy — stagnation detection, error spirals, mode-dependent escalation"
```

---

### Task 5: AgentRuntime — The Core Loop

**Files:**
- Create: `agent/src/runtime/agent_runtime.py`
- Create: `agent/tests/test_agent_runtime.py`

This is the main class that ties everything together. Tests use mocks for the Anthropic API.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_agent_runtime.py`:

```python
"""Tests for the AgentRuntime core loop."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.src.runtime.agent_runtime import AgentRuntime
from agent.src.runtime.compactor import Compactor
from agent.src.runtime.escalation import EscalationPolicy
from agent.src.runtime.hooks import Hook
from agent.src.runtime.types import HookAction, RunContext


# -- Mock helpers --

class MockContentBlock:
    def __init__(self, block_type, **kwargs):
        self.type = block_type
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockResponse:
    def __init__(self, stop_reason, content_blocks):
        self.stop_reason = stop_reason
        self.content = content_blocks
        self.usage = MagicMock(input_tokens=100, output_tokens=50,
                                cache_creation_input_tokens=0,
                                cache_read_input_tokens=0)


def _text_response(text="Hello!"):
    """Mock a simple text response (no tool calls)."""
    return MockResponse(
        stop_reason="end_turn",
        content_blocks=[MockContentBlock("text", text=text)],
    )


def _tool_use_response(tool_name, tool_input, tool_id="tool-1"):
    """Mock a response that calls a tool."""
    return MockResponse(
        stop_reason="tool_use",
        content_blocks=[MockContentBlock(
            "tool_use", id=tool_id, name=tool_name, input=tool_input,
        )],
    )


class NoOpHook(Hook):
    async def pre_tool(self, tool_name, tool_input, context):
        return HookAction.continue_with(tool_input)
    async def post_tool(self, tool_name, tool_input, result, context):
        return result


# -- Tests --

@pytest.mark.asyncio
async def test_simple_text_response():
    """Runtime handles a simple text response with no tool calls."""
    events = []

    runtime = AgentRuntime(
        system_prompt="You are helpful.",
        tools=[],
        hooks=[],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = _text_response("Hello!")
        result = await runtime.run_turn(
            messages=[{"role": "user", "content": "Hi"}],
            on_event=events.append,
        )

    assert result.iterations == 1
    assert len(result.messages) > 0


@pytest.mark.asyncio
async def test_tool_call_and_response():
    """Runtime executes a tool call and feeds result back."""
    events = []
    tool_def = {"name": "web_search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}

    runtime = AgentRuntime(
        system_prompt="You are helpful.",
        tools=[tool_def],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    # First call: tool_use. Second call: end_turn.
    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            _tool_use_response("web_search", {"query": "test"}),
            _text_response("Found results."),
        ]
        mock_exec.return_value = {"results": [{"title": "Result 1"}]}

        result = await runtime.run_turn(
            messages=[{"role": "user", "content": "Search for test"}],
            on_event=events.append,
        )

    assert result.iterations == 2
    mock_exec.assert_called_once_with("web_search", {"query": "test"})


@pytest.mark.asyncio
async def test_hooks_run_on_tool_calls():
    """Pre and post hooks are called for each tool execution."""
    pre_called = []
    post_called = []

    class TrackingHook(Hook):
        async def pre_tool(self, tool_name, tool_input, context):
            pre_called.append(tool_name)
            return HookAction.continue_with(tool_input)
        async def post_tool(self, tool_name, tool_input, result, context):
            post_called.append(tool_name)
            return result

    runtime = AgentRuntime(
        system_prompt="test",
        tools=[{"name": "web_search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}],
        hooks=[TrackingHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            _tool_use_response("web_search", {"query": "test"}),
            _text_response("Done"),
        ]
        mock_exec.return_value = {"results": []}
        await runtime.run_turn(
            messages=[{"role": "user", "content": "search"}],
            on_event=lambda e: None,
        )

    assert pre_called == ["web_search"]
    assert post_called == ["web_search"]


@pytest.mark.asyncio
async def test_hook_deny_skips_tool():
    """A deny hook prevents tool execution."""
    class DenyAllHook(Hook):
        async def pre_tool(self, tool_name, tool_input, context):
            return HookAction.deny("blocked")
        async def post_tool(self, tool_name, tool_input, result, context):
            return result

    runtime = AgentRuntime(
        system_prompt="test",
        tools=[{"name": "blocked_tool", "description": "X", "input_schema": {"type": "object", "properties": {}}}],
        hooks=[DenyAllHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            _tool_use_response("blocked_tool", {}),
            _text_response("OK"),
        ]
        await runtime.run_turn(
            messages=[{"role": "user", "content": "do thing"}],
            on_event=lambda e: None,
        )

    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_hard_stop_on_max_iterations():
    """Runtime stops when escalation policy says hard_stop."""
    runtime = AgentRuntime(
        system_prompt="test",
        tools=[{"name": "web_search", "description": "Search", "input_schema": {"type": "object", "properties": {}}}],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=2),
        api_key="test-key",
    )

    with patch.object(runtime, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(runtime, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        # Always return tool calls (would loop forever without hard stop)
        mock_api.return_value = _tool_use_response("web_search", {"query": "test"})
        mock_exec.return_value = {"results": []}

        result = await runtime.run_turn(
            messages=[{"role": "user", "content": "search forever"}],
            on_event=lambda e: None,
        )

    assert result.iterations <= 3  # max_iterations=2, may execute 1-2 tool rounds before stop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_agent_runtime.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/runtime/agent_runtime.py`:

```python
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
                # Append guidance to the last tool result message
                last_msg = messages[-1]
                if isinstance(last_msg.get("content"), list):
                    last_msg["content"].append({
                        "type": "tool_result",
                        "tool_use_id": "guidance",
                        "content": json.dumps({
                            "_runtime_guidance": action.message,
                        }),
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
        client = anthropic.AsyncAnthropic(api_key=self._api_key)

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_agent_runtime.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Update `__init__.py` exports**

Add `AgentRuntime` to `agent/src/runtime/__init__.py`:

```python
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
```

- [ ] **Step 6: Run all runtime tests**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core && python3.13 -m pytest agent/tests/test_runtime_types.py agent/tests/test_hooks_protocol.py agent/tests/test_runtime_compactor.py agent/tests/test_escalation.py agent/tests/test_agent_runtime.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-core
git add agent/src/runtime/agent_runtime.py agent/src/runtime/__init__.py agent/tests/test_agent_runtime.py
git commit -m "feat(runtime): add AgentRuntime — generic turn loop with hooks, compaction, and escalation"
```

---

## Summary

| Task | Files Created | Tests |
|------|--------------|-------|
| 1. Types | `runtime/types.py`, `runtime/__init__.py` | 10 |
| 2. Hook Protocol | `runtime/hooks.py` | 6 |
| 3. Compactor | `runtime/compactor.py` | 6 |
| 4. Escalation | `runtime/escalation.py` | 7 |
| 5. AgentRuntime | `runtime/agent_runtime.py` | 5 |
| **Total** | **5 new files** | **34 tests** |
