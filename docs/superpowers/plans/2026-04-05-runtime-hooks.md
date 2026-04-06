# Runtime Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 5 concrete hook implementations that replace all `if tool_name ==` special-casing in `chat_agent.py`. Each hook is a small, testable class.

**Architecture:** Each hook implements the `Hook` protocol from `runtime/hooks.py` (built in the runtime-core worktree). Since that code doesn't exist in this worktree yet, we create a local stub of the protocol for development and testing. When both branches merge, the stub is replaced by the real protocol.

**Tech Stack:** Python 3.13, pytest, unittest.mock

**Worktree:** `.worktrees/runtime-hooks` (branch: `feature/runtime-hooks`)

**Spec:** `docs/superpowers/specs/2026-04-05-agent-runtime-revamp-design.md`

**Depends on:** `feature/runtime-core` (Hook protocol, RunContext, HookAction). We stub these locally.

---

## File Structure

```
agent/src/hooks/
├── __init__.py              # Public exports
├── _protocol_stub.py        # Local stub of Hook/RunContext/HookAction (removed after merge)
├── inject_context.py        # InjectContextHook
├── rate_limit.py            # RateLimitHook
├── discovery.py             # DiscoveryHook
├── tool_health.py           # ToolHealthHook
└── batch_tracking.py        # BatchTrackingHook

agent/tests/
├── test_hook_inject_context.py
├── test_hook_rate_limit.py
├── test_hook_discovery.py
├── test_hook_tool_health.py
└── test_hook_batch_tracking.py
```

---

### Task 1: Protocol Stub + Package Init

**Files:**
- Create: `agent/src/hooks/__init__.py`
- Create: `agent/src/hooks/_protocol_stub.py`

This stub mirrors the Hook protocol from runtime-core so hooks can be developed in parallel.

- [ ] **Step 1: Create the protocol stub**

Create `agent/src/hooks/_protocol_stub.py`:

```python
"""Local stub of runtime types for parallel development.

These types mirror agent.src.runtime.types and agent.src.runtime.hooks.
After merging feature/runtime-core, replace imports with:
    from agent.src.runtime import Hook, RunContext, HookAction
"""

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
    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction:
        ...

    @abstractmethod
    async def post_tool(self, tool_name: str, tool_input: dict, result: dict, context: RunContext) -> dict:
        ...
```

Create `agent/src/hooks/__init__.py`:

```python
"""Concrete hook implementations for the agent runtime.

Each hook handles a specific cross-cutting concern (context injection,
rate limiting, discovery persistence, etc.) so the agent loop stays clean.
"""

from .inject_context import InjectContextHook
from .rate_limit import RateLimitHook
from .discovery import DiscoveryHook
from .tool_health import ToolHealthHook
from .batch_tracking import BatchTrackingHook

__all__ = [
    "InjectContextHook",
    "RateLimitHook",
    "DiscoveryHook",
    "ToolHealthHook",
    "BatchTrackingHook",
]
```

- [ ] **Step 2: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks
git add agent/src/hooks/__init__.py agent/src/hooks/_protocol_stub.py
git commit -m "feat(hooks): add package init and protocol stub for parallel development"
```

Note: The `__init__.py` will fail to import until all hook files exist. That's fine — we'll create them in order.

---

### Task 2: InjectContextHook

**Files:**
- Create: `agent/src/hooks/inject_context.py`
- Create: `agent/tests/test_hook_inject_context.py`

Replaces inline `_conversation_id` and `session_id` injection in `chat_agent.py:237-243,310-313`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_hook_inject_context.py`:

```python
"""Tests for InjectContextHook."""
import pytest
from agent.src.hooks._protocol_stub import RunContext, HookAction
from agent.src.hooks.inject_context import InjectContextHook


def _ctx(**overrides):
    defaults = dict(conversation_id="conv-1", session_id="sess-1", user_id="u-1",
                     iteration=0, tool_history=[], messages=[])
    defaults.update(overrides)
    return RunContext(**defaults)


@pytest.mark.asyncio
async def test_injects_conversation_id_for_remember():
    hook = InjectContextHook()
    action = await hook.pre_tool("remember", {"fact": "test"}, _ctx(conversation_id="conv-42"))
    assert action.kind == "continue"
    assert action.modified_input["_conversation_id"] == "conv-42"
    assert action.modified_input["fact"] == "test"


@pytest.mark.asyncio
async def test_injects_conversation_id_for_recall():
    hook = InjectContextHook()
    action = await hook.pre_tool("recall", {"query": "epc"}, _ctx(conversation_id="conv-99"))
    assert action.modified_input["_conversation_id"] == "conv-99"


@pytest.mark.asyncio
async def test_injects_session_id_for_manage_todo():
    hook = InjectContextHook()
    action = await hook.pre_tool("manage_todo", {"action": "list"}, _ctx(session_id="sess-7"))
    assert action.modified_input["session_id"] == "sess-7"


@pytest.mark.asyncio
async def test_injects_session_id_for_research_scratchpad():
    hook = InjectContextHook()
    action = await hook.pre_tool("research_scratchpad", {"data": "x"}, _ctx(session_id="sess-3"))
    assert action.modified_input["session_id"] == "sess-3"


@pytest.mark.asyncio
async def test_no_injection_for_other_tools():
    hook = InjectContextHook()
    action = await hook.pre_tool("web_search", {"query": "test"}, _ctx())
    assert action.kind == "continue"
    assert "_conversation_id" not in action.modified_input
    assert "session_id" not in action.modified_input


@pytest.mark.asyncio
async def test_does_not_overwrite_existing_session_id():
    hook = InjectContextHook()
    action = await hook.pre_tool("manage_todo", {"action": "list", "session_id": "custom"}, _ctx(session_id="sess-7"))
    # setdefault semantics: keep existing value
    assert action.modified_input["session_id"] == "custom"


@pytest.mark.asyncio
async def test_post_tool_passthrough():
    hook = InjectContextHook()
    result = await hook.post_tool("remember", {}, {"status": "ok"}, _ctx())
    assert result == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_inject_context.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/hooks/inject_context.py`:

```python
"""InjectContextHook — auto-inject conversation/session IDs into tools.

Replaces the inline ID injection in chat_agent.py for remember, recall,
manage_todo, and research_scratchpad.
"""

from __future__ import annotations

from ._protocol_stub import Hook, HookAction, RunContext

_NEEDS_CONVERSATION_ID = {"remember", "recall"}
_NEEDS_SESSION_ID = {"manage_todo", "research_scratchpad"}


class InjectContextHook(Hook):
    """Inject conversation_id or session_id into tools that need them."""

    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_inject_context.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks
git add agent/src/hooks/inject_context.py agent/tests/test_hook_inject_context.py
git commit -m "feat(hooks): add InjectContextHook — auto-inject conversation/session IDs"
```

---

### Task 3: RateLimitHook

**Files:**
- Create: `agent/src/hooks/rate_limit.py`
- Create: `agent/tests/test_hook_rate_limit.py`

Replaces inline `remember_count > 5` check in `chat_agent.py:238-240`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_hook_rate_limit.py`:

```python
"""Tests for RateLimitHook."""
import pytest
from agent.src.hooks._protocol_stub import RunContext, HookAction
from agent.src.hooks.rate_limit import RateLimitHook


def _ctx(**overrides):
    defaults = dict(conversation_id="c", session_id="s", user_id="u",
                     iteration=0, tool_history=[], messages=[])
    defaults.update(overrides)
    return RunContext(**defaults)


@pytest.mark.asyncio
async def test_allows_under_limit():
    hook = RateLimitHook(limits={"remember": 5})
    ctx = _ctx(tool_history=["remember", "remember"])
    action = await hook.pre_tool("remember", {"fact": "x"}, ctx)
    assert action.kind == "continue"


@pytest.mark.asyncio
async def test_denies_at_limit():
    hook = RateLimitHook(limits={"remember": 3})
    ctx = _ctx(tool_history=["remember", "remember", "remember"])
    action = await hook.pre_tool("remember", {"fact": "x"}, ctx)
    assert action.kind == "deny"
    assert "rate limit" in action.reason.lower()


@pytest.mark.asyncio
async def test_no_limit_for_unlisted_tools():
    hook = RateLimitHook(limits={"remember": 5})
    ctx = _ctx(tool_history=["web_search"] * 100)
    action = await hook.pre_tool("web_search", {"query": "test"}, ctx)
    assert action.kind == "continue"


@pytest.mark.asyncio
async def test_counts_only_matching_tool():
    hook = RateLimitHook(limits={"remember": 2})
    ctx = _ctx(tool_history=["web_search", "remember", "fetch_page", "remember"])
    action = await hook.pre_tool("remember", {"fact": "x"}, ctx)
    assert action.kind == "deny"


@pytest.mark.asyncio
async def test_post_tool_passthrough():
    hook = RateLimitHook()
    result = await hook.post_tool("remember", {}, {"ok": True}, _ctx())
    assert result == {"ok": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_rate_limit.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/hooks/rate_limit.py`:

```python
"""RateLimitHook — configurable per-tool call limits within a turn.

Replaces the inline remember_count check in chat_agent.py.
"""

from __future__ import annotations

from ._protocol_stub import Hook, HookAction, RunContext

_DEFAULT_LIMITS = {"remember": 5}


class RateLimitHook(Hook):
    """Deny tool calls that exceed a per-turn limit."""

    def __init__(self, limits: dict[str, int] | None = None):
        self.limits = limits or dict(_DEFAULT_LIMITS)

    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction:
        limit = self.limits.get(tool_name)
        if limit is None:
            return HookAction.continue_with(tool_input)

        count = context.tool_history.count(tool_name)
        if count >= limit:
            return HookAction.deny(
                f"Rate limit: max {limit} {tool_name} calls per turn. "
                f"Already called {count} times."
            )

        return HookAction.continue_with(tool_input)

    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict:
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_rate_limit.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks
git add agent/src/hooks/rate_limit.py agent/tests/test_hook_rate_limit.py
git commit -m "feat(hooks): add RateLimitHook — per-tool call limits per turn"
```

---

### Task 4: DiscoveryHook

**Files:**
- Create: `agent/src/hooks/discovery.py`
- Create: `agent/tests/test_hook_discovery.py`

Replaces `_handle_report_findings()` in `chat_agent.py:40-60`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_hook_discovery.py`:

```python
"""Tests for DiscoveryHook."""
import pytest
from unittest.mock import AsyncMock, patch
from agent.src.hooks._protocol_stub import RunContext
from agent.src.hooks.discovery import DiscoveryHook


def _ctx(**overrides):
    defaults = dict(conversation_id="conv-1", session_id="s", user_id="u",
                     iteration=0, tool_history=[], messages=[])
    defaults.update(overrides)
    return RunContext(**defaults)


@pytest.mark.asyncio
async def test_ignores_non_report_tools():
    hook = DiscoveryHook()
    result = await hook.post_tool("web_search", {}, {"results": []}, _ctx())
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_persists_discovery_on_report_findings():
    hook = DiscoveryHook()
    tool_input = {
        "epc_contractor": "Blattner Energy",
        "confidence": "confirmed",
        "sources": [{"channel": "epc_website", "url": "https://blattner.com"}],
        "reasoning": {"summary": "Found on EPC website"},
        "_project_id": 42,
    }
    result = {"status": "ok"}

    with patch("agent.src.hooks.discovery.parse_report_findings") as mock_parse, \
         patch("agent.src.hooks.discovery.db") as mock_db:
        mock_parse.return_value = {"epc_contractor": "Blattner Energy", "confidence": "confirmed"}
        mock_db.get_project.return_value = {"id": 42, "project_name": "Test Solar"}
        mock_db.store_discovery.return_value = {"id": 99}

        result = await hook.post_tool("report_findings", tool_input, result, _ctx())

    mock_db.store_discovery.assert_called_once()
    assert result.get("discovery_id") == 99


@pytest.mark.asyncio
async def test_handles_missing_project_id():
    hook = DiscoveryHook()
    tool_input = {
        "epc_contractor": "SunPower",
        "confidence": "possible",
        "sources": [],
        "reasoning": {"summary": "Uncertain"},
    }

    with patch("agent.src.hooks.discovery.parse_report_findings") as mock_parse:
        mock_parse.return_value = {"epc_contractor": "SunPower"}
        result = await hook.post_tool("report_findings", tool_input, {"status": "ok"}, _ctx())

    assert result.get("note") is not None  # recorded without DB storage


@pytest.mark.asyncio
async def test_pre_tool_passthrough():
    hook = DiscoveryHook()
    action = await hook.pre_tool("report_findings", {"epc": "test"}, _ctx())
    assert action.kind == "continue"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_discovery.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/hooks/discovery.py`:

```python
"""DiscoveryHook — persist EPC discoveries when report_findings is called.

Replaces _handle_report_findings() in chat_agent.py. Runs as a post-tool
hook so the tool executes normally, then we persist the result.
"""

from __future__ import annotations

from ._protocol_stub import Hook, HookAction, RunContext

from ..parsing import parse_report_findings
from .. import db


class DiscoveryHook(Hook):
    """Persist discoveries to DB when report_findings is called."""

    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction:
        return HookAction.continue_with(tool_input)

    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict:
        if tool_name != "report_findings":
            return result

        parsed = parse_report_findings(tool_input)

        project_id = tool_input.get("_project_id")
        if project_id:
            project = db.get_project(project_id)
            if project:
                discovery = db.store_discovery(
                    project_id, parsed, agent_log=[], total_tokens=0, project=project
                )
                result["discovery_id"] = discovery.get("id") if discovery else None
                result["status"] = "recorded"
                return result

        result["status"] = "recorded"
        result["note"] = "No project_id provided — finding recorded in conversation only."
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_discovery.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks
git add agent/src/hooks/discovery.py agent/tests/test_hook_discovery.py
git commit -m "feat(hooks): add DiscoveryHook — persist EPC discoveries from report_findings"
```

---

### Task 5: ToolHealthHook

**Files:**
- Create: `agent/src/hooks/tool_health.py`
- Create: `agent/tests/test_hook_tool_health.py`

Replaces `check_tool_health()` in `tools/__init__.py:150-171`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_hook_tool_health.py`:

```python
"""Tests for ToolHealthHook."""
import pytest
from agent.src.hooks._protocol_stub import RunContext
from agent.src.hooks.tool_health import ToolHealthHook


def _ctx(**overrides):
    defaults = dict(conversation_id="c", session_id="s", user_id="u",
                     iteration=0, tool_history=[], messages=[])
    defaults.update(overrides)
    return RunContext(**defaults)


@pytest.mark.asyncio
async def test_no_warning_on_success():
    hook = ToolHealthHook(error_threshold=3)
    result = await hook.post_tool("web_search", {}, {"results": ["ok"]}, _ctx())
    assert "_guidance" not in result


@pytest.mark.asyncio
async def test_warning_after_consecutive_errors():
    hook = ToolHealthHook(error_threshold=3)
    ctx = _ctx()
    # Simulate 3 consecutive errors
    await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    await hook.post_tool("web_search", {}, {"error": "500"}, ctx)
    result = await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    assert "_guidance" in result


@pytest.mark.asyncio
async def test_success_resets_counter():
    hook = ToolHealthHook(error_threshold=3)
    ctx = _ctx()
    await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    await hook.post_tool("web_search", {}, {"error": "500"}, ctx)
    # Success resets
    await hook.post_tool("web_search", {}, {"results": ["ok"]}, ctx)
    # Next error should not trigger warning
    result = await hook.post_tool("web_search", {}, {"error": "timeout"}, ctx)
    assert "_guidance" not in result


@pytest.mark.asyncio
async def test_pre_tool_passthrough():
    hook = ToolHealthHook()
    action = await hook.pre_tool("web_search", {"q": "test"}, _ctx())
    assert action.kind == "continue"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_tool_health.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/hooks/tool_health.py`:

```python
"""ToolHealthHook — track consecutive tool failures.

Replaces check_tool_health() in tools/__init__.py. Injects a guidance
message into tool results when errors accumulate.
"""

from __future__ import annotations

from ._protocol_stub import Hook, HookAction, RunContext


class ToolHealthHook(Hook):
    """Track consecutive tool errors and inject warnings."""

    def __init__(self, error_threshold: int = 3):
        self.error_threshold = error_threshold
        self._consecutive_errors = 0

    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_tool_health.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks
git add agent/src/hooks/tool_health.py agent/tests/test_hook_tool_health.py
git commit -m "feat(hooks): add ToolHealthHook — consecutive error tracking with guidance injection"
```

---

### Task 6: BatchTrackingHook

**Files:**
- Create: `agent/src/hooks/batch_tracking.py`
- Create: `agent/tests/test_hook_batch_tracking.py`

Replaces inline batch progress setup in `chat_agent.py:244-308`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_hook_batch_tracking.py`:

```python
"""Tests for BatchTrackingHook."""
import pytest
from unittest.mock import patch, MagicMock
from agent.src.hooks._protocol_stub import RunContext
from agent.src.hooks.batch_tracking import BatchTrackingHook


def _ctx(**overrides):
    defaults = dict(conversation_id="conv-1", session_id="s", user_id="u",
                     iteration=0, tool_history=[], messages=[])
    defaults.update(overrides)
    return RunContext(**defaults)


@pytest.mark.asyncio
async def test_ignores_non_batch_tools():
    hook = BatchTrackingHook()
    action = await hook.pre_tool("web_search", {"query": "test"}, _ctx())
    assert action.kind == "continue"
    assert "_batch_id" not in action.modified_input


@pytest.mark.asyncio
async def test_injects_batch_id_and_progress():
    hook = BatchTrackingHook()

    tool_input = {"project_ids": [1, 2, 3]}

    with patch("agent.src.hooks.batch_tracking.create_batch") as mock_create, \
         patch("agent.src.hooks.batch_tracking.get_cancel_event") as mock_cancel, \
         patch("agent.src.hooks.batch_tracking.db") as mock_db:
        mock_create.return_value = MagicMock(cancelled=False, projects=[], total=3)
        mock_cancel.return_value = MagicMock()
        mock_db.get_project.side_effect = lambda pid: {"id": pid, "project_name": f"Project {pid}", "queue_id": f"Q{pid}"}

        action = await hook.pre_tool("batch_research_epc", tool_input, _ctx(conversation_id="conv-1"))

    assert action.kind == "continue"
    assert "_batch_id" in action.modified_input
    assert "_project_names" in action.modified_input
    assert "_progress_callback" in action.modified_input
    assert "_cancel_event" in action.modified_input


@pytest.mark.asyncio
async def test_post_tool_marks_batch_done():
    hook = BatchTrackingHook()
    hook._active_batch_id = "batch-42"

    with patch("agent.src.hooks.batch_tracking.mark_done") as mock_done:
        result = await hook.post_tool("batch_research_epc", {}, {"results": []}, _ctx())

    mock_done.assert_called_once_with("batch-42")


@pytest.mark.asyncio
async def test_pre_tool_passthrough_for_other_tools():
    hook = BatchTrackingHook()
    action = await hook.pre_tool("remember", {"fact": "x"}, _ctx())
    assert "_batch_id" not in action.modified_input
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_batch_tracking.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/hooks/batch_tracking.py`:

```python
"""BatchTrackingHook — set up batch progress tracking for batch_research_epc.

Replaces inline batch setup logic in chat_agent.py:244-308. Creates the
batch in the progress store, injects tracking metadata into tool input,
and marks the batch as done after execution.
"""

from __future__ import annotations

import uuid

from ._protocol_stub import Hook, HookAction, RunContext

from .. import db
from ..batch_progress import create_batch, get_cancel_event, update_project, mark_done


class BatchTrackingHook(Hook):
    """Set up batch progress tracking for batch_research_epc tool calls."""

    def __init__(self):
        self._active_batch_id: str | None = None

    async def pre_tool(
        self, tool_name: str, tool_input: dict, context: RunContext
    ) -> HookAction:
        if tool_name != "batch_research_epc":
            return HookAction.continue_with(tool_input)

        batch_id = str(uuid.uuid4())
        self._active_batch_id = batch_id

        # Fetch project records
        batch_projects = []
        for pid in tool_input.get("project_ids", []):
            p = db.get_project(pid)
            if p:
                batch_projects.append(p)

        batch_state = create_batch(batch_id, batch_projects, conversation_id=context.conversation_id)

        # Build progress callback
        async def on_progress(update: dict, _bid: str = batch_id):
            update_project(_bid, update)

        modified = dict(tool_input)
        modified["_batch_id"] = batch_id
        modified["_project_names"] = {
            p["id"]: p.get("project_name") or p.get("queue_id", p["id"])
            for p in batch_projects
        }
        modified["_progress_callback"] = on_progress
        modified["_cancel_event"] = get_cancel_event(batch_id)

        return HookAction.continue_with(modified)

    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: RunContext
    ) -> dict:
        if tool_name == "batch_research_epc" and self._active_batch_id:
            mark_done(self._active_batch_id)
            self._active_batch_id = None
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_batch_tracking.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run all hook tests**

Run: `cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks && python3.13 -m pytest agent/tests/test_hook_*.py -v`
Expected: All 24 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/.worktrees/runtime-hooks
git add agent/src/hooks/batch_tracking.py agent/tests/test_hook_batch_tracking.py
git commit -m "feat(hooks): add BatchTrackingHook — batch progress setup and cleanup"
```

---

## Summary

| Task | Files Created | Tests |
|------|--------------|-------|
| 1. Protocol Stub | `hooks/__init__.py`, `hooks/_protocol_stub.py` | 0 |
| 2. InjectContextHook | `hooks/inject_context.py` | 7 |
| 3. RateLimitHook | `hooks/rate_limit.py` | 5 |
| 4. DiscoveryHook | `hooks/discovery.py` | 4 |
| 5. ToolHealthHook | `hooks/tool_health.py` | 4 |
| 6. BatchTrackingHook | `hooks/batch_tracking.py` | 4 |
| **Total** | **7 new files** | **24 tests** |

## Post-Merge Cleanup

After merging both `feature/runtime-core` and `feature/runtime-hooks`:
1. Delete `agent/src/hooks/_protocol_stub.py`
2. Update all hook imports from `._protocol_stub` to `..runtime` (e.g., `from ..runtime import Hook, HookAction, RunContext`)
3. Run all tests to verify
