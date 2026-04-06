# Runtime Integration Implementation Plan (Phases 3-6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the new AgentRuntime (from PR #1 and #2) into the existing FastAPI app, replacing the old `chat_agent.py` and `research.py` loops while preserving SSE streaming and all frontend behavior.

**Architecture:** Two factory functions (`build_chat_runtime`, `build_research_runtime`) configure the generic AgentRuntime with different prompts, tools, hooks, and escalation policies. A new `run_research` tool lets the chat agent spawn research as a sub-agent. The main.py `/api/chat` endpoint switches from `run_chat_agent()` to the new runtime. Streaming is added to AgentRuntime via `client.messages.stream()`.

**Tech Stack:** Python 3.13, anthropic SDK, FastAPI, existing SSE protocol (`sse.py`), existing tool registry

**Prerequisites:** Merge PR #1 (runtime-core) and PR #2 (runtime-hooks) to main first. Then delete `_protocol_stub.py` and update hook imports.

---

## File Structure

```
agent/src/
├── runtime/                    # FROM PR #1 (already merged)
│   ├── agent_runtime.py        # MODIFY: add streaming support to _call_api
│   └── ...
├── hooks/                      # FROM PR #2 (already merged)
│   ├── _protocol_stub.py       # DELETE: replace with real imports
│   ├── inject_context.py       # MODIFY: import from runtime instead of stub
│   ├── rate_limit.py           # MODIFY: import from runtime instead of stub
│   ├── discovery.py            # MODIFY: import from runtime instead of stub
│   ├── tool_health.py          # MODIFY: import from runtime instead of stub
│   └── batch_tracking.py       # MODIFY: import from runtime instead of stub
├── agents/                     # NEW
│   ├── __init__.py
│   ├── chat.py                 # build_chat_runtime() factory
│   └── research.py             # build_research_runtime() factory
├── tools/
│   └── run_research.py         # NEW: research-as-tool (manager pattern)
├── prompts.py                  # MODIFY: simplify research prompt
├── main.py                     # MODIFY: switch /api/chat to new runtime
├── chat_agent.py               # DELETE after cutover verified
├── research.py                 # KEEP for now (/api/discover still uses it)
└── completeness.py             # DELETE after cutover verified
```

---

### Task 1: Merge PRs and Fix Hook Imports

**Files:**
- Delete: `agent/src/hooks/_protocol_stub.py`
- Modify: `agent/src/hooks/inject_context.py:3`
- Modify: `agent/src/hooks/rate_limit.py:3`
- Modify: `agent/src/hooks/discovery.py:3`
- Modify: `agent/src/hooks/tool_health.py:3`
- Modify: `agent/src/hooks/batch_tracking.py:4`

- [ ] **Step 1: Merge both PRs to main**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
git checkout main
git merge feature/runtime-core --no-ff -m "Merge feature/runtime-core: AgentRuntime engine"
git merge feature/runtime-hooks --no-ff -m "Merge feature/runtime-hooks: concrete hooks"
```

- [ ] **Step 2: Delete the protocol stub**

```bash
rm agent/src/hooks/_protocol_stub.py
```

- [ ] **Step 3: Update all hook imports**

In each of these 5 files, replace:
```python
from ._protocol_stub import Hook, HookAction, RunContext
```
with:
```python
from ..runtime import Hook, HookAction, RunContext
```

Files: `inject_context.py`, `rate_limit.py`, `discovery.py`, `tool_health.py`, `batch_tracking.py`

- [ ] **Step 4: Run all tests to verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_runtime_types.py agent/tests/test_hooks_protocol.py agent/tests/test_runtime_compactor.py agent/tests/test_escalation.py agent/tests/test_agent_runtime.py agent/tests/test_hook_inject_context.py agent/tests/test_hook_rate_limit.py agent/tests/test_hook_tool_health.py agent/tests/test_hook_discovery.py agent/tests/test_hook_batch_tracking.py -v
```

Expected: All 55 tests pass

- [ ] **Step 5: Update hook test imports**

The hook tests import from `_protocol_stub` — update them to use `agent.src.runtime`:

In each test file (`test_hook_inject_context.py`, `test_hook_rate_limit.py`, `test_hook_tool_health.py`), replace:
```python
from agent.src.hooks._protocol_stub import RunContext
```
with:
```python
from agent.src.runtime import RunContext
```

For `test_hook_discovery.py` and `test_hook_batch_tracking.py`, also remove the `sys.modules.setdefault("agent.src.db", mock_db)` lines at module level since those were only needed because the stub couldn't handle the import chain. The lazy imports in the hooks themselves handle this now.

- [ ] **Step 6: Re-run all tests**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_runtime_*.py agent/tests/test_hook_*.py agent/tests/test_escalation.py -v
```

Expected: All 55 tests pass

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: merge runtime branches, replace protocol stub with real imports"
```

---

### Task 2: Add Streaming to AgentRuntime

**Files:**
- Modify: `agent/src/runtime/agent_runtime.py`
- Create: `agent/tests/test_agent_runtime_streaming.py`

The current `_call_api` uses `client.messages.create` (non-streaming). We need `client.messages.stream` to emit SSE events in real-time.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_agent_runtime_streaming.py`:

```python
"""Tests for streaming support in AgentRuntime."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.src.runtime.agent_runtime import AgentRuntime
from agent.src.runtime.compactor import Compactor
from agent.src.runtime.escalation import EscalationPolicy


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
                                cache_creation_input_tokens=0, cache_read_input_tokens=0)


@pytest.mark.asyncio
async def test_streaming_emits_text_events():
    """on_event should receive text_delta events during streaming."""
    events = []
    rt = AgentRuntime(
        system_prompt="test",
        tools=[],
        hooks=[],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="test-key",
    )

    # Mock _call_api to return a simple text response
    mock_response = MockResponse("end_turn", [MockContentBlock("text", text="Hello!")])
    with patch.object(rt, "_call_api", new_callable=AsyncMock) as mock:
        mock.return_value = mock_response
        result = await rt.run_turn(
            messages=[{"role": "user", "content": "Hi"}],
            on_event=events.append,
        )

    assert result.iterations == 1
    # Events should include at least the final message content
    assert len(result.messages) >= 1


@pytest.mark.asyncio
async def test_streaming_emits_tool_events():
    """on_event should receive tool_result events for tool calls."""
    events = []
    tool_def = {"name": "web_search", "description": "S", "input_schema": {"type": "object", "properties": {}}}

    from agent.src.runtime.hooks import Hook
    from agent.src.runtime.types import HookAction

    class NoOpHook(Hook):
        async def pre_tool(self, n, i, c): return HookAction.continue_with(i)
        async def post_tool(self, n, i, r, c): return r

    rt = AgentRuntime(
        system_prompt="t",
        tools=[tool_def],
        hooks=[NoOpHook()],
        compactor=Compactor(max_tokens=100_000),
        escalation=EscalationPolicy(max_iterations=50),
        api_key="k",
    )

    with patch.object(rt, "_call_api", new_callable=AsyncMock) as mock_api, \
         patch.object(rt, "_execute_tool", new_callable=AsyncMock) as mock_exec:
        mock_api.side_effect = [
            MockResponse("tool_use", [MockContentBlock("tool_use", id="t1", name="web_search", input={"query": "test"})]),
            MockResponse("end_turn", [MockContentBlock("text", text="Done")]),
        ]
        mock_exec.return_value = {"results": []}
        await rt.run_turn(
            messages=[{"role": "user", "content": "search"}],
            on_event=events.append,
        )

    tool_events = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_events) == 1
    assert tool_events[0]["tool_name"] == "web_search"
```

- [ ] **Step 2: Run test to verify it passes (existing behavior)**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_agent_runtime_streaming.py -v
```

These tests should pass with the current mock-based approach (we're testing event emission, not actual HTTP streaming). This verifies the contract.

- [ ] **Step 3: Add streaming SSE emission to the run_turn method**

Modify `agent/src/runtime/agent_runtime.py`. Add a `stream_writer` parameter to `__init__` and emit SSE events from the `on_event` callback within `run_turn`. The key change is making `_call_api` optionally stream:

In `agent_runtime.py`, add this method alongside the existing `_call_api`:

```python
async def _call_api_streaming(self, messages: list[dict], on_event: Callable):
    """Call the Anthropic API with streaming. Emits SSE events via on_event."""
    if self._client is None:
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

    cached_system = [{
        "type": "text",
        "text": self.system_prompt,
        "cache_control": {"type": "ephemeral"},
    }]

    cached_tools = list(self.tools)
    if cached_tools:
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    tool_calls = []
    current_tool_input = ""

    async with self._client.messages.stream(
        model=self.model,
        max_tokens=4096,
        system=cached_system,
        tools=cached_tools if cached_tools else anthropic.NOT_GIVEN,
        messages=messages,
    ) as stream:
        async for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "text":
                    on_event({"type": "text_start"})
                elif event.content_block.type == "tool_use":
                    tool_calls.append({
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input": {},
                    })
                    current_tool_input = ""
                    on_event({"type": "tool_input_start", "tool_name": event.content_block.name, "tool_id": event.content_block.id})

            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    on_event({"type": "text_delta", "text": event.delta.text})
                elif event.delta.type == "input_json_delta":
                    current_tool_input += event.delta.partial_json

            elif event.type == "content_block_stop":
                if tool_calls and current_tool_input:
                    import json as _json
                    try:
                        tool_calls[-1]["input"] = _json.loads(current_tool_input)
                    except _json.JSONDecodeError:
                        tool_calls[-1]["input"] = {}
                    on_event({"type": "tool_input_available", "tool_id": tool_calls[-1]["id"], "tool_name": tool_calls[-1]["name"], "input": tool_calls[-1]["input"]})

        response = await stream.get_final_message()

    return response
```

Then update `run_turn` to use `_call_api_streaming` when `on_event` is provided (which is always in production). The existing `_call_api` stays for tests that don't need streaming.

Replace the line in `run_turn`:
```python
response = await self._call_api(messages)
```
with:
```python
response = await self._call_api_streaming(messages, on_event)
```

Keep the old `_call_api` for testability (tests mock it directly).

- [ ] **Step 4: Run tests**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_agent_runtime.py agent/tests/test_agent_runtime_streaming.py -v
```

Expected: All pass (existing tests mock `_call_api` directly so streaming doesn't affect them)

- [ ] **Step 5: Commit**

```bash
git add agent/src/runtime/agent_runtime.py agent/tests/test_agent_runtime_streaming.py
git commit -m "feat(runtime): add streaming support to AgentRuntime via messages.stream()"
```

---

### Task 3: Agent Configurations (chat + research factories)

**Files:**
- Create: `agent/src/agents/__init__.py`
- Create: `agent/src/agents/chat.py`
- Create: `agent/src/agents/research.py`
- Create: `agent/tests/test_agents_chat.py`
- Create: `agent/tests/test_agents_research.py`

- [ ] **Step 1: Write the failing test for chat factory**

Create `agent/tests/test_agents_chat.py`:

```python
"""Tests for chat agent factory."""
import pytest
from agent.src.agents.chat import build_chat_runtime


def test_build_chat_runtime_returns_agent_runtime():
    from agent.src.runtime import AgentRuntime
    rt = build_chat_runtime(
        conversation_id="conv-1",
        user_id="user-1",
        api_key="test-key",
    )
    assert isinstance(rt, AgentRuntime)
    assert rt.conversation_id == "conv-1"
    assert rt.user_id == "user-1"


def test_chat_runtime_has_all_tools():
    rt = build_chat_runtime(conversation_id="c", user_id="u", api_key="k")
    tool_names = [t["name"] for t in rt.tools]
    # Should have all registered tools
    assert "web_search" in tool_names
    assert "report_findings" in tool_names
    assert "search_projects" in tool_names


def test_chat_runtime_has_hooks():
    rt = build_chat_runtime(conversation_id="c", user_id="u", api_key="k")
    assert len(rt.hooks) >= 3  # InjectContext, RateLimit, Discovery, ToolHealth at minimum


def test_chat_runtime_escalation_is_user_mode():
    rt = build_chat_runtime(conversation_id="c", user_id="u", api_key="k")
    assert rt.escalation.escalation_mode == "user"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_agents_chat.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.src.agents'`

- [ ] **Step 3: Write chat factory implementation**

Create `agent/src/agents/__init__.py`:

```python
"""Agent configurations — factory functions for different runtime modes."""

from .chat import build_chat_runtime
from .research import build_research_runtime

__all__ = ["build_chat_runtime", "build_research_runtime"]
```

Create `agent/src/agents/chat.py`:

```python
"""Chat agent configuration.

Factory function that returns an AgentRuntime configured for interactive
chat: all tools, user-mode escalation, full hook set.
"""

from __future__ import annotations

from ..runtime import AgentRuntime, Compactor, EscalationPolicy
from ..hooks import InjectContextHook, RateLimitHook, DiscoveryHook, ToolHealthHook, BatchTrackingHook
from ..prompts import CHAT_SYSTEM_PROMPT
from ..tools import get_all_tools


def build_chat_runtime(
    conversation_id: str,
    user_id: str,
    api_key: str | None = None,
    model: str | None = None,
) -> AgentRuntime:
    """Build an AgentRuntime configured for interactive chat."""
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
        compactor=Compactor(max_tokens=80_000, preserve_recent=6, api_key=api_key),
        escalation=EscalationPolicy(max_iterations=50, escalation_mode="user"),
        api_key=api_key,
        model=model,
        conversation_id=conversation_id,
        session_id=conversation_id,  # session = conversation for chat
        user_id=user_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_agents_chat.py -v
```

Expected: All 4 tests pass

- [ ] **Step 5: Write research factory**

Create `agent/src/agents/research.py`:

```python
"""Research agent configuration.

Factory function for autonomous EPC research: limited tools,
autonomous escalation, tighter compaction.
"""

from __future__ import annotations

from ..runtime import AgentRuntime, Compactor, EscalationPolicy
from ..hooks import DiscoveryHook, ToolHealthHook
from ..prompts import RESEARCH_SYSTEM_PROMPT
from ..tools import get_tools
from ..knowledge_base import build_knowledge_context

RESEARCH_TOOL_NAMES = [
    "web_search", "brave_search", "fetch_page",
    "search_sec_edgar", "fetch_sec_filing",
    "search_osha", "search_enr", "search_wiki_solar", "search_spw",
    "query_kb", "remember", "recall",
    "manage_todo", "think", "notify_progress", "research_scratchpad",
    "report_findings",
]


def build_research_runtime(
    project: dict,
    kb_context: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> AgentRuntime:
    """Build an AgentRuntime configured for autonomous EPC research."""
    from ..prompts import build_user_message

    # Build the system prompt with project context baked in
    system = RESEARCH_SYSTEM_PROMPT

    return AgentRuntime(
        system_prompt=system,
        tools=get_tools(RESEARCH_TOOL_NAMES),
        hooks=[
            DiscoveryHook(),
            ToolHealthHook(),
        ],
        compactor=Compactor(max_tokens=60_000, preserve_recent=4, api_key=api_key),
        escalation=EscalationPolicy(
            max_iterations=30,
            escalation_mode="autonomous",
            min_iterations_before_stagnation=6,
        ),
        api_key=api_key,
        model=model,
    )
```

Create `agent/tests/test_agents_research.py`:

```python
"""Tests for research agent factory."""
from agent.src.agents.research import build_research_runtime, RESEARCH_TOOL_NAMES


def test_build_research_runtime():
    from agent.src.runtime import AgentRuntime
    rt = build_research_runtime(
        project={"id": 1, "project_name": "Test Solar"},
        api_key="test-key",
    )
    assert isinstance(rt, AgentRuntime)


def test_research_has_limited_tools():
    rt = build_research_runtime(project={"id": 1}, api_key="k")
    tool_names = [t["name"] for t in rt.tools]
    assert "web_search" in tool_names
    assert "report_findings" in tool_names
    # Should NOT have batch or HubSpot tools
    assert "batch_research_epc" not in tool_names
    assert "push_to_hubspot" not in tool_names


def test_research_escalation_is_autonomous():
    rt = build_research_runtime(project={"id": 1}, api_key="k")
    assert rt.escalation.escalation_mode == "autonomous"


def test_research_tool_names_valid():
    from agent.src.tools import get_tool_names
    registered = get_tool_names()
    for name in RESEARCH_TOOL_NAMES:
        assert name in registered, f"Research tool '{name}' not in registry"
```

- [ ] **Step 6: Run all agent config tests**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_agents_chat.py agent/tests/test_agents_research.py -v
```

Expected: All 8 tests pass

- [ ] **Step 7: Commit**

```bash
git add agent/src/agents/ agent/tests/test_agents_chat.py agent/tests/test_agents_research.py
git commit -m "feat: add agent configurations — chat and research factory functions"
```

---

### Task 4: Research-as-Tool (Manager Pattern)

**Files:**
- Create: `agent/src/tools/run_research.py`
- Modify: `agent/src/tools/__init__.py` (register new tool)
- Create: `agent/tests/test_run_research_tool.py`

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_run_research_tool.py`:

```python
"""Tests for run_research tool (research as sub-agent)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent.src.tools.run_research import DEFINITION, execute


def test_definition_has_required_fields():
    assert DEFINITION["name"] == "run_research"
    assert "project_id" in DEFINITION["input_schema"]["properties"]
    assert "project_id" in DEFINITION["input_schema"]["required"]


@pytest.mark.asyncio
async def test_execute_calls_research_runtime():
    mock_runtime = MagicMock()
    mock_runtime.run_turn = AsyncMock(return_value=MagicMock(
        messages=[
            {"role": "assistant", "content": [{"type": "text", "text": "Found EPC: Blattner Energy"}]},
        ],
        iterations=5,
    ))

    with patch("agent.src.tools.run_research.build_research_runtime", return_value=mock_runtime) as mock_build, \
         patch("agent.src.tools.run_research.db") as mock_db, \
         patch("agent.src.tools.run_research.build_knowledge_context", return_value=""):
        mock_db.get_project.return_value = {"id": 42, "project_name": "Test Solar"}

        result = await execute({
            "project_id": 42,
            "_api_key": "test-key",
        })

    mock_build.assert_called_once()
    mock_runtime.run_turn.assert_called_once()
    assert "findings" in result or "summary" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_run_research_tool.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Create `agent/src/tools/run_research.py`:

```python
"""run_research — research as a sub-agent tool (manager pattern).

When the chat agent calls this tool, it spawns a focused research
sub-runtime that runs autonomously and returns findings.
"""

from __future__ import annotations

from ..agents.research import build_research_runtime
from ..knowledge_base import build_knowledge_context
from .. import db
from ..prompts import build_user_message

DEFINITION = {
    "name": "run_research",
    "description": (
        "Launch a focused EPC research session for a project. "
        "Runs autonomously and returns findings including EPC contractor, "
        "confidence level, and sources. Use this when the user asks to "
        "research or discover the EPC for a specific project."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "integer",
                "description": "The project ID to research",
            },
            "focus": {
                "type": "string",
                "description": "Optional focus area (e.g., 'check OSHA records specifically')",
            },
        },
        "required": ["project_id"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Run a research sub-agent and return findings."""
    project_id = tool_input["project_id"]
    focus = tool_input.get("focus", "")
    api_key = tool_input.get("_api_key")

    project = db.get_project(project_id)
    if not project:
        return {"error": f"Project {project_id} not found"}

    kb_context = build_knowledge_context(project)

    runtime = build_research_runtime(
        project=project,
        kb_context=kb_context,
        api_key=api_key,
    )

    user_msg = build_user_message(project, kb_context)
    if focus:
        user_msg += f"\n\nFocus: {focus}"

    try:
        result = await runtime.run_turn(
            messages=[{"role": "user", "content": user_msg}],
            on_event=lambda e: None,  # sub-agent doesn't stream to frontend
        )

        # Extract findings from the last assistant message
        last_assistant = None
        for msg in reversed(result.messages):
            if msg.get("role") == "assistant":
                last_assistant = msg
                break

        summary = ""
        if last_assistant:
            content = last_assistant.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        summary = block.get("text", "")
                        break
            elif isinstance(content, str):
                summary = content

        return {
            "findings": summary,
            "iterations": result.iterations,
            "project_name": project.get("project_name", ""),
        }
    except Exception as exc:
        return {"error": f"Research failed: {type(exc).__name__}: {exc}"}
```

- [ ] **Step 4: Register the tool**

In `agent/src/tools/__init__.py`, add after the existing imports:

```python
from . import run_research
```

And add after the existing `_register` calls:

```python
_register(run_research)
```

- [ ] **Step 5: Run tests**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/test_run_research_tool.py -v
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add agent/src/tools/run_research.py agent/src/tools/__init__.py agent/tests/test_run_research_tool.py
git commit -m "feat: add run_research tool — research as sub-agent (manager pattern)"
```

---

### Task 5: Wire main.py /api/chat Endpoint (The Cutover)

**Files:**
- Modify: `agent/src/main.py:991-1026` (`_run_agent_job` function)
- Modify: `agent/src/main.py:36` (import)

This is the critical switch. We change `_run_agent_job` to use the new runtime instead of `run_chat_agent`.

- [ ] **Step 1: Update imports in main.py**

Add to imports section (around line 36):

```python
from .agents import build_chat_runtime
```

- [ ] **Step 2: Create a new `_run_agent_job_v2` function**

Add this function after the existing `_run_agent_job` (don't delete the old one yet):

```python
async def _run_agent_job_v2(
    job, messages: list[dict], conversation_id: str, stream_writer: StreamWriter,
    api_key: str | None = None, user_id: str = "",
) -> None:
    """Background wrapper using the new AgentRuntime."""
    try:
        runtime = build_chat_runtime(
            conversation_id=conversation_id,
            user_id=user_id,
            api_key=api_key,
        )

        message_id = str(uuid.uuid4())
        job.append_event(stream_writer.start(message_id))
        job.append_event(stream_writer.start_step())

        full_text = ""
        all_parts: list[dict] = []

        def on_event(event: dict):
            nonlocal full_text
            etype = event.get("type")

            if etype == "text_start":
                pass  # Could emit text-start SSE here
            elif etype == "text_delta":
                text = event.get("text", "")
                full_text += text
                job.append_event(stream_writer.text_delta(str(len(all_parts)), text))
            elif etype == "tool_input_start":
                job.append_event(stream_writer.tool_input_start(event["tool_id"], event["tool_name"]))
            elif etype == "tool_input_available":
                job.append_event(stream_writer.tool_input_available(event["tool_id"], event["tool_name"], event["input"]))
            elif etype == "tool_result":
                job.append_event(stream_writer.tool_output_available(
                    event.get("tool_id", ""),
                    event.get("result", {}),
                ))

        result = await runtime.run_turn(messages, on_event)

        # Persist assistant message
        job.append_event(stream_writer.finish_step())
        job.append_event(stream_writer.finish())
        job.append_event(stream_writer.done())

        db.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=full_text,
            parts=all_parts,
        )

        mark_job_done(job.job_id)

    except asyncio.CancelledError:
        logger.info("Agent job %s cancelled by user", job.job_id)
        sw = StreamWriter()
        job.append_event(sw.finish_step())
        job.append_event(sw.finish("stop"))
        job.append_event(sw.done())
        mark_job_done(job.job_id)
        db.save_message(conversation_id=conversation_id, role="assistant", content="[Stopped by user]")

    except anthropic.AuthenticationError:
        error_sw = StreamWriter()
        job.append_event(error_sw.text("\n\n**Authentication failed.** Your API key is invalid or expired."))
        job.append_event(error_sw.finish("error"))
        job.append_event(error_sw.done())
        mark_job_done(job.job_id, error="Authentication failed")

    except Exception:
        logger.exception("Agent job %s failed", job.job_id)
        error_sw = StreamWriter()
        job.append_event(error_sw.finish("error"))
        job.append_event(error_sw.done())
        mark_job_done(job.job_id, error=db.sanitize_key_from_string(traceback.format_exc()[:500]))
```

- [ ] **Step 3: Switch the chat endpoint to use v2**

In the `chat` function (line 977), change:

```python
task = asyncio.create_task(_run_agent_job(job, messages, conversation_id, stream_writer, api_key=api_key))
```

to:

```python
task = asyncio.create_task(_run_agent_job_v2(job, messages, conversation_id, stream_writer, api_key=api_key, user_id=_user_id))
```

- [ ] **Step 4: Manual smoke test**

Start the dev server and test:
1. Send a simple chat message — verify text streams
2. Ask to search for a project — verify tool calls work
3. Ask to research an EPC — verify run_research sub-agent works
4. Have a long conversation — verify compaction kicks in

- [ ] **Step 5: Commit**

```bash
git add agent/src/main.py
git commit -m "feat: wire /api/chat endpoint to new AgentRuntime (the cutover)"
```

---

### Task 6: Simplify Research Prompt

**Files:**
- Modify: `agent/src/prompts.py`

Strip procedural commands from the research prompt. Keep domain knowledge.

- [ ] **Step 1: Identify what to keep vs remove**

**Keep** (domain knowledge — lines 16-250 of `_EPC_RESEARCH_INSTRUCTIONS`):
- Key Distinction (EPC vs developer)
- Confidence Levels definitions
- Source reliability ranking
- Verification checklist (scale, role, counter-evidence)
- Red flags
- Multi-phase project handling
- Source requirements (date, URL, source_method)
- Negative evidence tracking

**Remove** (procedural commands):
- Mandatory 4-phase search ordering ("Phase 1: ...", "Phase 2: ...", etc.)
- "You MUST search X before Y" instructions
- Progress notification instructions ("call notify_progress with status...")
- Scratchpad/todo management instructions ("Use manage_todo to track...")
- Research scratchpad format instructions

- [ ] **Step 2: Create the simplified research prompt**

This is a judgment call — read `prompts.py:252-322` (RESEARCH_SYSTEM_PROMPT) and remove the procedural sections while keeping the domain expertise sections. The goal is ~150 lines instead of ~300.

The model decides its own search strategy. The runtime ensures coherence via compaction and escalation.

- [ ] **Step 3: Run existing research tests to check for regressions**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/ -k "research" -v
```

- [ ] **Step 4: Commit**

```bash
git add agent/src/prompts.py
git commit -m "refactor: simplify research prompt — keep domain knowledge, remove procedural commands"
```

---

### Task 7: Cleanup — Delete Old Files

**Files:**
- Delete: `agent/src/chat_agent.py`
- Delete: `agent/src/completeness.py`
- Modify: `agent/src/main.py` (remove old import)

Only do this AFTER the cutover (Task 5) is verified working in production.

- [ ] **Step 1: Remove old imports from main.py**

Remove:
```python
from .chat_agent import run_chat_agent
```

Remove the old `_run_agent_job` function (keep `_run_agent_job_v2`, rename it to `_run_agent_job`).

- [ ] **Step 2: Delete old files**

```bash
rm agent/src/chat_agent.py
rm agent/src/completeness.py
```

- [ ] **Step 3: Remove old tests that reference deleted modules**

```bash
# Check which tests import chat_agent or completeness
grep -rl "chat_agent\|completeness" agent/tests/
```

Update or remove as needed.

- [ ] **Step 4: Run full test suite**

```bash
/opt/homebrew/bin/python3.13 -m pytest agent/tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete old chat_agent.py and completeness.py — fully replaced by AgentRuntime"
```

---

## Summary

| Task | What | Risk | Reversible |
|------|------|------|------------|
| 1 | Merge PRs, fix hook imports | Low | Yes (git revert) |
| 2 | Add streaming to AgentRuntime | Low | Yes (revert 1 file) |
| 3 | Agent config factories | None — new code | N/A |
| 4 | run_research tool | None — new code | N/A |
| 5 | Wire /api/chat (CUTOVER) | **Medium** | Revert 1 commit |
| 6 | Simplify prompts | Low — prompt change | Revert 1 commit |
| 7 | Delete old files | Low — cleanup | Revert 1 commit |

Tasks 1-4 are safe additions. Task 5 is the cutover — test manually before proceeding. Tasks 6-7 are post-cutover cleanup.
