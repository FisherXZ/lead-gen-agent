# Agent Runtime Revamp — Design Spec

**Date:** 2026-04-05
**Status:** Draft
**Author:** Fisher + Claude

## Problem Statement

The current agent has four interconnected problems:

1. **Session breakdown** — Long research sessions (30+ tool calls) degrade as context overflows ~100K tokens. The agent re-searches queries, forgets candidates, and produces worse results over time.
2. **Hard stops** — Iteration caps (25 for research, 50 for chat) are walls, not intelligence. The agent hits the cap and gives up rather than switching strategy or asking for direction.
3. **Brittle extensibility** — Every new tool requires modifying the main loop's `if tool_name == ...` chain. Tool-specific lifecycle logic (DB writes, rate limits, context injection) is inlined in `chat_agent.py`.
4. **Prescriptive prompts fight the model** — A 500-line research prompt micromanages the search strategy with mandatory phases. The model either follows it robotically (bad results) or ignores it (wasted tokens).

## Design Principles

Drawn from three sources: claw-code-2 (mature agentic runtime), Anthropic's "Building Effective Agents" guide, and OpenAI's "Practical Guide to Building Agents."

1. **Simple loop, smart infrastructure** — The agent loop is ~50 lines. Intelligence lives in tools, hooks, compaction, and escalation — not in the loop itself.
2. **Trust the model** — Give it domain knowledge and good tools. Don't prescribe search strategy. (Anthropic: "Start with simple prompts, add complexity only when needed.")
3. **Tools are the product** — Invest in tool quality and documentation, not in loop special-casing. (Anthropic: "Invest as much in ACI as you would in HCI.")
4. **Human escalation over hard stops** — When the agent is stuck, ask the user for direction instead of giving up. (OpenAI: "Exceeding failure thresholds -> escalate to human.")
5. **Manager pattern** — Chat agent is the manager. Research is a specialized sub-agent invoked as a tool. (OpenAI: "Manager pattern — agents as tools.")

## Architecture Overview

```
User Message
    │
    ▼
┌─────────────────────────────────────────┐
│            AgentRuntime                  │
│                                          │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Compactor │  │  Hooks   │  │Escalat.│ │
│  └──────────┘  └──────────┘  └────────┘ │
│                                          │
│  while True:                             │
│    response = call_claude(messages)       │
│    if end_turn: break                    │
│    for tool_call in response:            │
│      hooks.pre_tool(...)                 │
│      result = registry.execute(...)      │
│      hooks.post_tool(...)                │
│    escalation.evaluate(...)              │
│    compactor.maybe_compact(messages)     │
└─────────────────────────────────────────┘
    │
    ▼
TurnResult (messages, usage, events)
```

Chat mode and research mode are **configurations** of the same runtime — different system prompts, tool sets, hooks, and escalation policies.

Research is also available as a **tool** that chat can invoke (manager pattern), spawning a sub-runtime internally.

## Component Specifications

### 1. AgentRuntime

**File:** `agent/src/runtime/agent_runtime.py`

The core loop. Takes a configuration and runs a single turn (user message -> assistant response with tool calls resolved).

```python
class AgentRuntime:
    def __init__(
        self,
        system_prompt: str,
        tools: list[ToolDef],
        hooks: list[Hook],
        compactor: Compactor,
        escalation: EscalationPolicy,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
    ): ...

    async def run_turn(
        self,
        messages: list[dict],
        on_event: Callable,          # SSE callback for streaming
    ) -> TurnResult: ...
```

**Loop behavior:**
1. `compactor.maybe_compact(messages)` — summarize older messages if over token threshold
2. Stream response from Claude with system prompt + messages + tool definitions
3. If `stop_reason == "end_turn"`: break (model is done)
4. For each tool call:
   - `hooks.pre_tool()` — can modify input, deny, or escalate
   - `registry.execute()` — dispatch to tool module
   - `hooks.post_tool()` — can transform output, persist side effects
5. `escalation.evaluate()` — check for stagnation, errors, or hard limit
6. Loop back to step 2

**Exit conditions:**
- Model returns `end_turn` (no tool calls)
- Escalation policy returns `EscalateToUser` or `HardStop`
- Maximum iterations reached (safety limit)

### 2. Compactor

**File:** `agent/src/runtime/compactor.py`

Keeps working context under the token threshold by summarizing older messages while preserving recent ones verbatim. Uses Haiku for cheap, fast summarization.

```python
class Compactor:
    def __init__(
        self,
        max_tokens: int = 80_000,
        preserve_recent: int = 6,
        summary_model: str = "claude-haiku-4-5-20251001",
    ): ...

    async def maybe_compact(self, messages: list[dict]) -> list[dict]:
        """If over threshold, summarize older messages. No-op otherwise."""
```

**Summarization extracts:**
- What the user asked for
- Tools called and their key results (not raw output)
- Discoveries made (EPC findings, confidence levels)
- Dead ends (searches that returned nothing useful)
- Current state of work (what's done, what's pending)

**Summary merging:** If a prior summary exists, the new compaction merges with it rather than summarizing a summary (preserves fidelity).

**Token economics:** ~$0.001 per compaction. Triggers 2-3 times in a long session. Net savings from avoiding bloated 100K+ context calls.

### 3. Hook System

**Files:** `agent/src/runtime/hooks.py` (protocol), `agent/src/hooks/` (implementations)

Replaces all `if tool_name == ...` special-casing in the current loop.

```python
class Hook(Protocol):
    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction: ...
    async def post_tool(self, tool_name: str, tool_input: dict, result: dict, context: RunContext) -> dict: ...

@dataclass
class RunContext:
    conversation_id: str
    session_id: str
    user_id: str
    iteration: int
    tool_history: list[str]
    messages: list[dict]
```

**HookAction variants:**
- `Continue(modified_input)` — proceed with (possibly modified) tool input
- `Deny(reason)` — skip this tool call, return reason as tool result
- `Escalate(message)` — pause and present to user

**Concrete hooks:**

| Hook | Replaces | Purpose |
|------|----------|---------|
| `InjectContextHook` | Inline `_conversation_id`/`session_id` injection | Auto-inject IDs into tools that need them |
| `RateLimitHook` | Inline "max 5 remember calls" | Configurable per-tool rate limits |
| `DiscoveryHook` | `_handle_report_findings()` in chat_agent.py | Persist discoveries to DB on report_findings |
| `ToolHealthHook` | `check_tool_health()` | Track consecutive failures, inject warnings |
| `BatchTrackingHook` | Inline batch progress logic | Update batch progress store during batch runs |

### 4. Escalation Policy

**File:** `agent/src/runtime/escalation.py`

Replaces hard iteration caps and `completeness.py` checkpoints with signal-based stopping.

```python
class EscalationPolicy:
    def __init__(
        self,
        max_iterations: int = 50,
        stagnation_window: int = 4,
        escalation_mode: str = "user",    # "user" or "autonomous"
    ): ...

    def evaluate(self, messages, iteration, tool_history) -> Action:
        """Returns Continue, InjectGuidance, EscalateToUser, or HardStop."""
```

**Decision logic:**
1. Hard safety limit exceeded -> `HardStop`
2. Stagnation detected (recent tools not producing new signals) -> `EscalateToUser` (chat) or `InjectGuidance` (batch)
3. Consecutive tool failures >= 3 -> `EscalateToUser`
4. Otherwise -> `Continue`

**Stagnation detection:** Checks whether recent tool results contain entity mentions not already seen. If <25% of recent calls found something new, the agent is stagnating.

**Mode difference:**
- `"user"` mode (interactive chat): Pauses and asks the user for direction
- `"autonomous"` mode (batch/sub-agent): Injects a guidance message telling the model to switch approach

### 5. Research as Sub-Agent

**File:** `agent/src/tools/run_research.py`

Research is a tool callable by the chat agent. Internally spawns its own `AgentRuntime` with research-specific configuration.

```python
DEFINITION = {
    "name": "run_research",
    "description": "Launch a focused EPC research session for a project.",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {"type": "integer"},
            "focus": {"type": "string"},
        },
        "required": ["project_id"]
    }
}

async def execute(tool_input: dict) -> dict:
    project = await get_project(tool_input["project_id"])
    kb_context = await get_knowledge_context(project)
    research_runtime = build_research_runtime(project, kb_context, api_key)
    result = await research_runtime.run_turn(
        messages=[user_message(f"Research EPC for: {project['name']}")],
        on_event=noop,
    )
    return extract_findings(result)
```

**User experience change:** Instead of separate research jobs, users say "research this" in chat. The chat agent delegates to the research sub-agent, receives findings, and presents them conversationally. Users can then ask follow-up questions or direct deeper research — all in the same conversation.

### 6. Simplified Prompts

**File:** `agent/src/prompts.py`

The research prompt shrinks from ~500 lines to ~150 lines.

**Kept (domain knowledge):**
- EPC vs developer distinction
- Confidence rubric (confirmed/likely/possible/unknown)
- Source reliability ranking
- Verification checklist (scale check, role check, counter-evidence)
- Red flags (portfolio confusion, cross-state assumptions)

**Removed (procedural commands):**
- Mandatory 4-phase search ordering
- "You MUST do X before Y" instructions
- Prescribed search strategy
- Progress notification instructions
- Scratchpad/todo management instructions

The model decides its own research approach. The runtime (via escalation and hooks) ensures it doesn't loop forever or lose context.

### 7. Agent Configurations

**Files:** `agent/src/agents/chat.py`, `agent/src/agents/research.py`

Each agent mode is a factory function that returns a configured `AgentRuntime`:

```python
# agents/chat.py
def build_chat_runtime(conversation_id, user_id, api_key) -> AgentRuntime:
    return AgentRuntime(
        system_prompt=CHAT_SYSTEM_PROMPT,
        tools=get_all_tools(),          # all 27 + run_research
        hooks=[InjectContextHook(...), RateLimitHook(), DiscoveryHook(...), ToolHealthHook()],
        compactor=Compactor(max_tokens=80_000, preserve_recent=6),
        escalation=EscalationPolicy(max_iterations=50, escalation_mode="user"),
        api_key=api_key,
    )

# agents/research.py
def build_research_runtime(project, kb_context, api_key) -> AgentRuntime:
    return AgentRuntime(
        system_prompt=build_research_prompt(project, kb_context),
        tools=get_tools(RESEARCH_TOOL_NAMES),
        hooks=[DiscoveryHook(), ToolHealthHook()],
        compactor=Compactor(max_tokens=60_000, preserve_recent=4),
        escalation=EscalationPolicy(max_iterations=30, escalation_mode="autonomous"),
        api_key=api_key,
    )
```

## File Structure

```
agent/src/
├── runtime/                    # NEW — generic agent engine
│   ├── __init__.py
│   ├── agent_runtime.py        # ~100 lines
│   ├── compactor.py            # ~80 lines
│   ├── escalation.py           # ~100 lines
│   ├── hooks.py                # ~40 lines (protocol + RunContext)
│   └── types.py                # dataclasses
├── hooks/                      # NEW — concrete hook implementations
│   ├── __init__.py
│   ├── inject_context.py
│   ├── rate_limit.py
│   ├── discovery.py
│   ├── tool_health.py
│   └── batch_tracking.py
├── agents/                     # NEW — agent configurations
│   ├── __init__.py
│   ├── chat.py
│   └── research.py
├── tools/                      # UNCHANGED (+ run_research.py)
│   ├── __init__.py             # simplified: remove special-case logic
│   ├── _base.py
│   ├── run_research.py         # NEW
│   └── ... (existing tools)
├── prompts.py                  # SIMPLIFIED
├── main.py                     # SIMPLIFIED — endpoints use runtime
├── sse.py                      # UNCHANGED
├── db.py                       # UNCHANGED
├── models.py                   # UNCHANGED
├── chat_agent.py               # DELETED
├── research.py                 # DELETED
└── completeness.py             # DELETED
```

**Estimated new code:** ~400 lines across 10 small files
**Estimated deleted code:** ~600 lines (chat_agent.py loop, research.py loop, completeness.py)
**Net: -200 lines** with more capability

## Migration Plan

Sequential commits on one branch. Commits 1-4 are pure additions (zero risk). Commit 5 is the cutover. Commits 6-8 are cleanup.

| # | Commit | Risk | Reversible |
|---|--------|------|------------|
| 1 | Add `runtime/` package | None — new code, nothing calls it | N/A |
| 2 | Add `hooks/` package | None — new code | N/A |
| 3 | Add `tools/run_research.py` | None — new tool, not registered | N/A |
| 4 | Add `agents/chat.py` and `agents/research.py` | None — new code | N/A |
| 5 | Wire `main.py` endpoints to new runtime | **Cutover** | Revert 1 commit |
| 6 | Simplify `prompts.py` — strip procedural commands | Prompt change | Revert 1 commit |
| 7 | Delete `chat_agent.py`, `research.py`, `completeness.py` | Cleanup | Revert 1 commit |
| 8 | Simplify `tools/__init__.py` | Cleanup | Revert 1 commit |

## Testing Strategy

1. **Unit tests for runtime components:** Compactor (mock Haiku call, verify summary structure), EscalationPolicy (test stagnation detection, error spiral), Hooks (test each hook in isolation)
2. **Integration test:** Run a full chat turn through the new runtime with mock LLM responses, verify tool dispatch, hook execution, and SSE event emission
3. **Regression test:** Run the same research query through old and new runtime, compare findings quality
4. **Manual smoke test:** Interactive chat session with research sub-agent invocation

## What This Doesn't Change

- **Frontend** — No changes. Same SSE protocol, same message format.
- **Database** — No schema changes. Same message storage, same discovery tables.
- **Tool implementations** — All 27 existing tools stay exactly as they are.
- **Batch job infrastructure** — `batch.py` and `agent_jobs.py` call the new runtime instead of the old one, but the job tracking mechanism is unchanged.

## Resolved Design Decisions

1. **Prompt caching** — The runtime applies `ephemeral` cache control to the system prompt and last tool definition, matching current behavior. The system prompt is the stable prefix; tool definitions follow. This preserves cache hit rates.
2. **Sub-agent streaming** — Sub-agent (research tool) runs silently and returns findings as a tool result. No intermediate streaming to frontend in v1. The `on_event` callback accepts a no-op for sub-agents. Intermediate visibility can be added later by passing a real callback that emits nested SSE events.
3. **Compaction and DB** — Compaction is in-memory only. The DB keeps full conversation history for audit. The compacted summary is never persisted — it's regenerated from DB messages if a session is resumed.

## Clarifications

- **`on_event` type:** `Callable[[SSEEvent], None]` where `SSEEvent` is a union of `TextDelta`, `ToolStart`, `ToolInputAvailable`, `ToolOutputAvailable`, `Escalation`, `Finish`. Same event types as current `sse.py`.
- **`extract_findings()`:** Reads the last assistant message from the sub-agent's turn result, parses any `report_findings` tool call from the tool history, and returns the structured `AgentResult` dict. Falls back to a text summary if no `report_findings` was called (e.g., the sub-agent escalated or hit hard stop).
