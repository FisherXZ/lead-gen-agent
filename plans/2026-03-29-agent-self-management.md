# Agent Self-Management — Todo List, Think Tool, and Reflection

**Date:** 2026-03-29
**Status:** CEO Review CLEARED, pending eng review
**Branch:** main

## Plain English

Right now the agent starts Googling without a plan and hopes it remembers what it tried. The best AI agents (Manus, Claude Code) give themselves a checklist and cross things off as they go. We're adding three things:

1. **A todo list** the agent writes for itself and updates as it works, stored in the database so it survives even if the conversation gets too long
2. **A "think" tool** so the agent can pause and reason through a decision instead of being forced to take an action every single turn
3. **A reflection step** after research where the agent checks its own work, and gets a few more tries if it spots a concrete gap (the Reflexion pattern, proven to improve quality from 80% to 91% on benchmarks)

The chat agent gets planning too, so users can see what the agent intends to do before it starts. The existing checkpoint system gets smarter by reading the agent's own todo list instead of just counting how many searches it's done.

---

## Research Background

### What leading agent systems do

| System | Pattern | Key Insight |
|--------|---------|-------------|
| **Manus AI** | `todo.md` rewrite pattern. Plan-Execute-Reflect loop. | Constantly rewriting the checklist keeps the plan in the model's recent attention. Their #1 architecture principle. |
| **Claude Code** | `TaskCreate/TaskUpdate/TaskList` tools. Structured DAG with states. | Task management as first-class tools. Ownership, dependencies, status tracking. |
| **Reflexion** (NeurIPS 2023) | Post-task self-evaluation with retry. | 80% → 91% on code benchmarks. Agent reflects on failures, stores verbal feedback, retries with context. |
| **BabyAGI** | Task queue with execute → create → reprioritize cycle. | Dynamic task generation. Overkill for single-objective research. |
| **LangGraph** | Plan-and-Execute graph with conditional replanning. | Planner generates steps upfront, executor handles one at a time, replanner adjusts. |

### Key finding from research

Reflection **with retry** is where the quality gains come from. Capture-only reflection (logging without acting on it) has weaker evidence. But reflection without external grounding (no concrete checks) can actually degrade performance. The agent must check against specific criteria, not just ask "did I do well?"

### What we already have

- `research_scratchpad` tool — DB-backed key-value storage for findings (candidates, dead_ends, sources). Survives compaction.
- `completeness.py` — Deterministic checkpoint system at iterations 6, 12, 18. Counts tool calls heuristically. Three escalation levels: gentle → firm → mandatory.
- `run_research_plan()` — Separate endpoint that generates a plan but doesn't integrate into the research loop.

---

## Scope

### In scope (7 items)

| # | Feature | Type | Effort |
|---|---------|------|--------|
| 1 | `manage_todo` tool (create/update/read) | Core | S |
| 2 | `think` tool (reasoning pause) | Core | S |
| 3 | Prompt changes (research + chat) | Core | S |
| 4 | Smarter completeness checks | Core | S |
| 5 | Post-research reflection w/ bounded retry | Core | M |
| 6 | Todo analytics (store final state) | Expansion | S |
| 7 | Chat agent planning prompt | Expansion | S |

### NOT in scope (deferred)

- **Plan templates per project type** — wait for organic usage patterns before templatizing
- **Scratchpad consolidation** — tasks and findings are different things, keep `research_scratchpad` separate (outside voice recommendation, accepted)

---

## Implementation Details

### 1. New Tool: `manage_todo`

**Inspired by:** Manus's `todo.md` + Claude Code's TaskCreate/TaskUpdate, adapted to our stack (Supabase DB instead of filesystem, single tool instead of three).

A single tool with 3 operations. Stored in the existing `research_scratch` table with key = `"todo"`. No migration needed.

```python
DEFINITION = {
    "name": "manage_todo",
    "description": (
        "Manage your research task list. Create a plan at the start, "
        "check off tasks as you complete them, and review remaining work. "
        "Your todo list persists across context compaction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create", "update", "read"],
                "description": "create: Set the full task list. update: Mark task(s) done or add new tasks. read: Get current state."
            },
            "session_id": {
                "type": "string",
                "description": "Research session identifier (provided in project details)."
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done", "skipped"]
                        },
                        "result_summary": {
                            "type": "string",
                            "description": "Brief note on what was found (when marking done)."
                        }
                    }
                },
                "description": "For create: full task list. For update: tasks to modify (by id)."
            }
        },
        "required": ["operation", "session_id"]
    }
}
```

**Edge cases:**
- `update` before `create` → return error "No todo list exists. Call create first."
- `create` called twice → overwrites (upsert)
- Duplicate task IDs on create → validate uniqueness
- Empty tasks array → allowed (agent might add tasks later)
- Concurrent batch sessions → safe (keyed by unique session_id)

### 2. New Tool: `think`

**Inspired by:** Anthropic's "think" tool pattern, Manus's "analyze events" phase.

Lets the agent pause and reason without calling an external tool. The thought is recorded in the conversation context but doesn't hit any API or database.

```python
DEFINITION = {
    "name": "think",
    "description": (
        "Pause to reason about your findings, evaluate your progress, "
        "or plan your next steps. Use this when you need to think through "
        "a decision before acting — e.g., weighing conflicting evidence, "
        "deciding which phase to enter next, or assessing whether a candidate "
        "EPC is credible. Your thought is recorded in conversation context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "Your reasoning, analysis, or evaluation."
            }
        },
        "required": ["thought"]
    }
}
```

Returns `{"recorded": true, "thought": <echo>}`. No external calls.

### 3. Prompt Changes

**Add to `_EPC_RESEARCH_INSTRUCTIONS` in `prompts.py`:**

```
## Self-Management
Before starting research, call manage_todo to create your task plan (3-8 tasks
based on what you know about the project). As you complete each task, update it
with a brief result summary. Before calling report_findings, read your todo list
to verify you haven't skipped anything.

Use the think tool when you need to evaluate evidence, weigh conflicting sources,
or decide which phase to enter next. Thinking before acting leads to better research.
```

**Add to `CHAT_SYSTEM_PROMPT` in `prompts.py`:**

```
## Planning Complex Requests
For multi-step requests (batch research, comparisons, multi-project analysis),
call manage_todo first to show the user your plan. Execute the plan, updating
tasks as you go. This makes your reasoning visible to the user.
```

### 4. Smarter Completeness Checks

Update `completeness.py` to read the todo list via `db.read_scratch()`:

- **Iteration 6 (gentle):** Check if agent created a plan. If not, inject "You haven't created a research plan yet. Call manage_todo to create your task plan now."
- **Iteration 12 (firm):** Check tasks done vs pending. Report completion rate instead of just search count. If most tasks are pending, suggest wrapping up with what's found.
- **Iteration 18 (mandatory):** Check for critical uncompleted tasks. Include them in the mandatory wrap-up message.
- **Fallback:** If DB read fails (connection error, missing data), fall back to the current heuristic-only behavior. Never crash.

### 5. Post-Research Reflection with Bounded Retry

**Inspired by:** Reflexion (Shinn et al., NeurIPS 2023) + Manus's Plan-Execute-Reflect loop.

After `report_findings` is called in `research.py`, before returning:

1. Inject a reflection prompt into the conversation:
   > "Review your todo list and findings. Check: (a) Are all tasks done or explicitly skipped? (b) Does your confidence level match your evidence? (c) If you named an EPC, is the name specific and verified?"
2. Make one API call with `manage_todo` (read) + `think` + `report_findings` as available tools
3. If the agent calls `report_findings` again (same or updated result), accept it and return
4. If the agent identifies a gap and calls other research tools, allow max 3 iterations, then force-close with the last `report_findings` result
5. Store the reflection text in `agent_log` under `{"reflection": text, "retry_triggered": bool, "gap_identified": str | null}`

**Fires on all outcomes** including "unknown" — the agent might realize it skipped a source.

**Gated by:** `ENABLE_REFLECTION=true` env var (opt-in, off by default).

**Cost:** One extra API call always (~500 tokens). Retry cycle adds ~2x cost when triggered.

### 6. Todo Analytics

After the research loop completes in `research.py`:
- Read the final todo state from `research_scratch`
- Include it in the `agent_log` data passed to `store_discovery()`
- No schema change needed (`agent_log` is already JSONB)
- Over time this reveals: which phases complete vs skip, average completion rate, correlation with confidence levels

### 7. Error Handling Improvement

Add a broad `except Exception` catch to `execute_tool()` in `tools/__init__.py`:

```python
except Exception as exc:
    return {
        "error": f"Unexpected error in {name}: {type(exc).__name__}",
        "error_category": "tool_error",
        "detail": str(exc),
    }
```

This protects all tools (including DB-touching ones like `manage_todo`) from unhandled exceptions that would otherwise crash the research loop.

---

## Files to Modify

| File | Change |
|------|--------|
| `agent/src/tools/manage_todo.py` | **NEW** — manage_todo tool (~60 LOC) |
| `agent/src/tools/think.py` | **NEW** — think tool (~15 LOC) |
| `agent/src/tools/__init__.py` | Register both new tools, add broad Exception catch |
| `agent/src/research.py` | Add to RESEARCH_TOOLS, exclude from iteration budget, add reflection loop, store todo analytics |
| `agent/src/prompts.py` | Self-management instructions in research + chat prompts |
| `agent/src/completeness.py` | Read todo at checkpoints for smarter evaluation |
| `agent/tests/test_manage_todo.py` | **NEW** — unit tests |
| `agent/tests/test_think.py` | **NEW** — unit tests |
| `agent/tests/test_reflection.py` | **NEW** — reflection loop tests |

## What This Does NOT Change

- No new database tables or migrations (reuses `research_scratch`)
- No changes to the agent loop structure (still iteration-based)
- No changes to the frontend
- `research_scratchpad` stays as-is (separate tool for findings)

---

## Implementation Order

1. `agent/src/tools/think.py` — trivial, ~15 LOC
2. `agent/src/tools/manage_todo.py` — ~60 LOC
3. `agent/src/tools/__init__.py` — register + broad exception catch
4. `agent/src/research.py` — RESEARCH_TOOLS + iteration exclusion + reflection loop + todo analytics
5. `agent/src/prompts.py` — research + chat prompt additions
6. `agent/src/completeness.py` — todo-aware checkpoints
7. Tests (test_manage_todo, test_think, test_reflection)

---

## Verification

1. Run a single research on a known project — verify the agent creates a todo, updates it, and the completeness checks use it
2. Check agent_log — confirm `think` and `manage_todo` calls appear but don't burn the effective iteration budget
3. Run a batch of 3 projects — verify concurrent session isolation (keyed by session_id)
4. Test reflection: mock a scenario where agent reports "possible" with weak evidence — verify retry triggers
5. Test reflection hard cap: verify max 3 retry iterations, no infinite loop, no double-report
6. Compare token usage before/after — expect ~5-10% overhead, fewer wasted iterations from goal drift

---

## Outside Voice Findings

An independent adversarial reviewer challenged the plan. 10 issues raised, resolutions:

| # | Finding | Resolution |
|---|---------|-----------|
| 1 | `think` is a no-op workaround for loop design | Standard Anthropic-recommended pattern. Keep it. |
| 2 | Don't consolidate scratchpad into manage_todo | **Accepted.** Tasks ≠ findings. Keep separate. |
| 3 | Todo doesn't truly survive compaction (tool results get stubbed) | Agent calls `manage_todo read` to recover. DB is source of truth. |
| 4 | Reflection cost on "unknown" outcomes | **User decision:** always reflect. Agent might catch skipped phases. |
| 5 | Prompt instructions aren't enforceable | Mitigated by completeness check at iteration 6 (nudge if no plan). |
| 6 | session_id as tool parameter is fragile | Same pattern as existing research_scratchpad. Works in practice. |
| 7 | No baseline measurement for "goal drift" | **TODO:** Run 20 projects through current system first. |
| 8 | No cleanup/TTL on research_scratch | **TODO:** Add cleanup for entries older than 30 days. |
| 9 | Chat agent planning is scope creep | **Rejected.** Chat agent IS the primary agent. Planning is the whole point. |
| 10 | Is planning actually the bottleneck vs. info availability? | **TODO:** Sample 10 "unknown" outcomes to validate. Ship anyway — tools are cheap. |

---

## Open TODOs (follow-up work)

- [ ] **Baseline measurement:** Run 20 projects through current system, record iterations used, confidence accuracy, wasted searches. Establish before-metrics.
- [ ] **research_scratch cleanup:** Add TTL/cron to delete entries older than 30 days.
- [ ] **Validate bottleneck hypothesis:** Sample 10 "unknown" outcomes, categorize why they failed (planning vs. information availability).
- [ ] **Plan templates:** After observing organic todo patterns, create starter templates per project type.
- [ ] **Chat agent deep integration:** Evaluate todo usage in chat, consider richer integration if the pattern proves valuable.

---

## Review Status

| Review | Status | Date |
|--------|--------|------|
| CEO Review (`/plan-ceo-review`) | CLEARED | 2026-03-29 |
| Eng Review (`/plan-eng-review`) | CLEARED | 2026-03-30 |
| Design Review (`/plan-design-review`) | CLEARED | 2026-03-30 |
| Outside Voice (Claude subagent) | 10 issues, 2 accepted | 2026-03-29 |

## Eng Review Findings (2026-03-30)

- **Architecture:** 1 issue. Reflection loop needs to preserve original AgentResult as fallback if retry fails. Resolved.
- **Code Quality:** 0 issues. Broad Exception catch in execute_tool must include logger.exception().
- **Tests:** 24 code paths mapped. 5 test files planned. 100% coverage of new code.
- **Performance:** 0 issues. ~5-10% token overhead. Reflection gated by env var.
- **Failure Modes:** 9 mapped, 0 critical gaps.
- **Added to scope:** research_scratch TTL cleanup (5 lines of SQL)

**Sources consulted:**
- [Context Engineering for AI Agents — Manus Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [The "think" tool — Anthropic Engineering](https://www.anthropic.com/engineering/claude-think-tool)
- [Reflexion: Language Agents with Verbal Reinforcement Learning — NeurIPS 2023](https://arxiv.org/pdf/2303.11366)
- [The Reflection Pattern: Why Self-Reviewing AI Improves Quality](https://qat.com/reflection-pattern-ai/)
- [Agentic Design Patterns: The 2026 Guide](https://www.sitepoint.com/the-definitive-guide-to-agentic-design-patterns-in-2026/)
- [AI Trends 2026: Test-Time Reasoning and Reflective Agents — Hugging Face](https://huggingface.co/blog/aufklarer/ai-trends-2026-test-time-reasoning-reflective-agen)
