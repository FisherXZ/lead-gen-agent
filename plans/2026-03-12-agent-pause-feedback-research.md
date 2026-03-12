# How Top AI Agents Handle Pausing, Feedback & Clarification

**Date:** 2026-03-12
**Purpose:** Research to inform redesign of our `request_guidance` feature and research flow

---

## TL;DR — The Four Philosophies

| Product | Pause Philosophy | Key Mechanism |
|---------|-----------------|---------------|
| **Harvey AI** | Workflow-defined checkpoints — the architect decides when to pause, not the AI | Pre-defined pause points in workflow templates |
| **Claude Code** | Permission-gated autonomy — the AI runs freely, but dangerous actions require approval | 3-tier permission system (allow/ask/deny) + AskUserQuestion tool |
| **Manus** | Maximum autonomy, minimal interruption — only ask when genuinely stuck | Two distinct tools: `message_notify_user` (no pause) vs `message_ask_user` (pause) |
| **Cursor** | Sandbox-first — let the agent run in a box, rewind if wrong | Sandboxing + checkpoints + user-chosen modes (Ask/Agent/Plan) |

---

## Harvey AI

### How They Pause

Harvey defines an **agent** (vs a basic AI system) as requiring three capabilities:
1. **Planning** — break tasks into steps
2. **Adaptation** — modify plans based on intermediate results
3. **Interaction** — solicit human input *during* execution

Checkpoints are **built into the workflow definition**, not left to the AI's judgment. Example: a regulatory review agent (1) searches company policies, (2) flags misaligned language, then (3) **pauses to ask the user to confirm the approach** before editing documents.

### Their Search Loop (most relevant to us)

Five stages, inspired by ReAct:
1. Query understanding & planning
2. Dynamic tool selection & retrieval
3. Reasoning & synthesis
4. **Completeness evaluation** — "do I have enough?" If not, loop back to step 2
5. Citation-backed response

The **completeness evaluation** step is what our research function is missing.

### Confidence Model

Two outputs per evaluation:
- A **grade** (the answer quality)
- A **confidence-in-that-grade** score (how sure am I about my own assessment)

### Other High-Value Concepts

- **Partner/Associate model**: A "Partner" model plans and delegates to specialized "Associate" models. Single query can trigger 30-1,500 model calls.
- **Thinking states UI**: Shows what the agent is doing, how decisions are made, and task progress in real-time.
- **Agent Builder**: Users can define custom workflows with human-in-the-loop checkpoints. 25,000+ custom agentic workflows built by legal teams.
- **Citation verification**: 95%+ accuracy through structured metadata extraction + embedding-based retrieval + binary LLM matching.

**Sources:** harvey.ai/blog/introducing-harvey-agents, harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence

---

## Claude Code (Anthropic)

### How They Pause

Claude Code uses a **layered permission system** — not a single pause mechanism:

| Mechanism | When It Triggers | What Happens |
|-----------|-----------------|--------------|
| **Permission system** | Tool matches "ask" rule or has no "allow" rule | User approves/denies in terminal |
| **AskUserQuestion tool** | Claude detects ambiguity mid-execution | User picks from options or types custom input |
| **Plan mode** (Shift+Tab) | User activates before a big task | Claude researches and proposes a plan, user approves before any edits |
| **Hooks (PreToolUse)** | Custom script returns exit code 2 | Error message sent back to Claude, operation blocked |
| **Escape key** | User presses Esc | Interrupts Claude, allows clarification |
| **Checkpoints** | Automatic on every action | User can double-Esc to rewind |

### The AskUserQuestion Tool

This is their equivalent of our `request_guidance`. Key design details:
- Presents **structured multiple-choice questions** with selectable options
- Used when instructions are ambiguous or multiple valid approaches exist
- Explicitly NOT for asking "should I proceed?" — that's handled by Plan mode
- Recently added HTML preview support for visual comparisons (UI mockups, code snippets)

### When Claude Asks vs. Proceeds Autonomously

- **Asks:** Ambiguous instructions, multiple valid approaches, unclear requirements
- **Proceeds:** Clear instructions, obvious single approach, sufficient guidance in CLAUDE.md
- **Key insight:** The system prompt and CLAUDE.md files reduce the need to ask by giving the agent enough context to make decisions

### The Agent Loop

A single `while(tool_call)` loop — no classifiers, no RAG pipeline, no DAG orchestrator. The model follows a **Gather-Act-Verify** pattern:
1. Gather context (search/read files)
2. Take action (edit/write/run)
3. Verify results (run tests, check output)
4. Repeat

### Other High-Value Concepts

- **Sub-agents**: Explore (codebase search), Plan (research during plan mode), General-purpose (complex multi-step). Sub-agents **cannot spawn other sub-agents** (prevents infinite nesting).
- **Context compaction**: Auto-triggers at ~92% context window usage. Summarizes stale content, preserves recent turns.
- **CLAUDE.md as persistent context**: Instructions persist across sessions. Deliberately injected as messages (not system prompt) so system prompt caching isn't invalidated.
- **6 layers of memory**: System prompt, CLAUDE.md, MEMORY.md, session memory, conversation history, system reminders.
- **Hooks for input modification**: PreToolUse hooks can modify tool inputs before execution (secret redaction, path correction, commit message formatting).

### Anthropic's Agent Design Philosophy

From their "Building Effective Agents" blog:
- **Start simple**: Most successful implementations use simple, composable patterns — not complex frameworks.
- **Five workflow patterns** (increasing complexity): Prompt Chaining → Routing → Parallelization → Orchestrator-Workers → Evaluator-Optimizer
- **Tool design**: Choose high-leverage tools, use human-readable fields, implement pagination/truncation/filtering, use evaluation-driven development.
- **Context engineering > prompt engineering**: "What configuration of context is most likely to generate the model's desired behavior?"

**Sources:** anthropic.com/research/building-effective-agents, anthropic.com/engineering/effective-context-engineering-for-ai-agents, code.claude.com/docs/en/hooks

---

## Manus AI

### How They Pause

Two distinct message tools with different behaviors:
- **`message_notify_user`** — One-way notification. Does NOT pause. For progress updates, status reports, approach changes.
- **`message_ask_user`** — Pauses execution and waits for response. For clarification, confirmation, additional information.

**Design bias: heavily autonomous.** The system prompt instructs: "Do NOT ask unnecessary questions that would halt the autonomous flow. Push forward and only ask when you genuinely cannot proceed."

### Context Engineering (Their Most Important Published Insight)

From their blog post "Context Engineering for AI Agents":

**KV-Cache hit rate is the #1 optimization metric:**
- Cached tokens on Claude Sonnet: $0.30/MTok. Uncached: $3.00/MTok — **10x difference**
- A single token change at the start of context invalidates the entire cache
- Context must be **append-only** — never modify previous actions or observations
- Serialization must be **deterministic** (same input → same token sequence)

**Tool masking, not tool removal:**
- Never dynamically add/remove tools mid-session (invalidates KV-cache and confuses the model)
- Instead, use **logit masking** during decoding to prevent selection of certain tools based on state
- Tool names use consistent prefixes (`browser_*`, `shell_*`) so groups can be masked efficiently

**File system as unlimited memory:**
- Agent writes intermediate results to files rather than keeping them in chat context
- Only conclusions and next-action decisions stay in the live context

**The Todo.md problem:**
- Initially used a `todo.md` for task planning
- Problem: ~**one-third of all agent actions** were spent updating the todo list
- Solution: shifted to a dedicated planner agent that manages the plan separately

**Error traces should be preserved:**
- Failed attempts stay in context so the model avoids repeating mistakes
- Error recovery is "one of the clearest indicators of true agentic behavior"

### Context Compaction Strategy

Three tiers, in order of preference:
1. **Raw** — keep full detail as long as possible
2. **Compaction** — every tool call has two formats (full and compact). Compact strips info that can be reconstructed from file system. Applied to oldest ~50% first.
3. **Summarization (last resort)** — summarize older turns into JSON. Always keep last 3 turns raw to preserve the model's "rhythm."

### Wide Research: Parallel Sub-Agents

For tasks requiring research across many entities:
- Main agent breaks request into N independent sub-tasks
- Each sub-task gets a dedicated agent with its **own fresh context window**
- Agents work in parallel with no shared context
- Errors in one sub-agent don't propagate
- Results synthesized after all complete

### Other High-Value Concepts

- **One-action-per-iteration rule**: Agent executes one tool, observes result, then decides next action. No parallel tool calls within a single iteration.
- **Controlled variation**: Repetitive contexts cause LLM drift. Manus introduces variation through different serialization templates and alternate phrasing.
- **Sandbox per task**: Every task gets a dedicated cloud VM (E2B/Firecracker). Agent has root access within sandbox.
- **Planner/Executor split**: Dedicated planning step before execution. Planner agent manages the plan, executor sub-agents do the work.

**Sources:** manus.im/blog/Context-Engineering-for-AI-Agents, manus.im/blog/manus-wide-research-solve-context-problem

---

## Cursor

### How They Pause

Cursor does NOT auto-detect when to ask. Users choose the mode:

- **Ask Mode** — Read-only. AI answers questions but never makes changes.
- **Agent Mode** — Full autonomy. AI explores, edits, runs commands, iterates.
- **Plan Mode** (Shift+Tab) — Agent researches, asks clarifying questions, produces a plan. User approves before execution.

Community feedback confirms this is a known limitation: "it just can't stop in agent mode."

### Sandboxing > Permission Prompts

Cursor's key insight: **sandboxing beats approval prompts.**
- Agent runs freely inside a constrained sandbox (Seatbelt on macOS, Bubblewrap on Linux)
- Only asks when it needs to break out (network access, writing outside project dir)
- **Result: sandboxed agents stop 40% less often** than unsandboxed ones

### Checkpoints > Pre-Approval

- A checkpoint is created **before every code edit** in Agent mode
- If the agent goes off the rails, you rewind rather than having needed to approve each step
- Philosophy: **it's faster to let the agent run and rewind if wrong, than to ask permission at every step**

### Background Agents

Fully asynchronous model:
- Agent runs in a **remote VM** (AWS EC2 with Firecracker)
- Clones your repo, works on a separate branch
- Creates a **pull request** when done
- Human-in-the-loop happens entirely at the PR review stage — no mid-execution pausing

### Other High-Value Concepts

- **Shadow Workspace**: When AI writes code and wants to check lints, it spawns a hidden Electron window. Edits are applied invisibly, lints collected, results sent back — without touching user's visible workspace.
- **Parallel agents**: Up to 8 agents in parallel, each in an isolated git worktree. ~2x faster than serial.
- **Speculative edits (Fast Apply)**: Predicts large chunks at once rather than token-by-token. ~1000 tokens/sec on 70B model — **13x speedup** over vanilla inference.
- **Two-stage codebase retrieval**: Chunk → embed → vector search (Turbopuffer) → re-rank with second model.
- **Composer model**: Custom MoE model for agent tasks, ~4x faster than comparably intelligent models. Trained with RL specifically for agentic coding.
- **Tool use must be baked into the model**, not just prompted. Prompting alone is not enough for reliable tool calling inside long loops.

**Sources:** cursor.com/blog/agent-sandboxing, cursor.com/blog/shadow-workspace, cursor.com/blog/plan-mode

---

## Cross-Cutting Patterns — What We Should Adopt

### 1. Separate "Notify" from "Ask" (Manus pattern)

Our `request_guidance` tool conflates notification with asking. Split into two tools:
- **`notify_progress`** — one-way, doesn't pause (search started, candidate found, verifying)
- **`request_guidance`** — pauses execution, waits for user response

### 2. Workflow-Defined Checkpoints, Not AI-Decided (Harvey pattern)

Don't hope the AI decides to pause — **build pause points into the research workflow**:
- After Phase 1 (initial search): "Found candidate X. Proceed with verification?"
- Before reporting "unknown": "Exhausted N searches. Want me to try different approach?"
- After reporting: "Here's what I found. Want to discuss or accept?"

### 3. Completeness Evaluation Before Reporting (Harvey pattern)

Add an explicit "do I have enough?" step before the agent calls `report_findings`. Harvey's search loop evaluates sufficiency before generating a response. Our agent just... stops when it feels like it.

### 4. Plan-Then-Execute Mode (Claude Code + Cursor pattern)

Both Claude Code and Cursor have a "plan mode" where the agent researches first, proposes a plan, and waits for approval before acting. Our research function could:
- Phase 1: Agent searches and proposes a research plan ("I'll check these 5 sources")
- User can modify the plan ("Also check McCarthy's portfolio")
- Phase 2: Agent executes the approved plan

### 5. Checkpoints Over Pre-Approval (Cursor pattern)

For the research flow specifically: instead of asking "should I search this?" every time, let the agent run and provide a rewind/refine mechanism after. The discovery becomes editable, not final.

### 6. File System as Extended Memory (Manus pattern)

For long research runs, write intermediate findings to a structured scratch file instead of relying solely on chat context. Prevents the compaction problem where early findings get lost.

### 7. Append-Only Context + KV-Cache Awareness (Manus pattern)

Never modify previous messages in the conversation. Our compaction system replaces old tool results — this is correct. But we should ensure the system prompt prefix stays stable for cache hits.

### 8. Error Preservation, Not Cleanup (Manus pattern)

Keep failed search attempts visible in context so the agent doesn't repeat them. Our `negative_evidence` field captures this in the final report, but the *during-research* context loses failed searches via compaction.

### 9. Parallel Sub-Agents for Batch Research (Manus + Cursor pattern)

Each batch project should get its own fresh context window (Manus "wide research" pattern). Cursor does the same with parallel agents in isolated worktrees. Our batch already does this — good.

### 10. Autonomy Dial (Industry pattern)

Let the user set the pause level:
- **Autonomous**: Run to completion, report results (current research button)
- **Checkpoints**: Pause at key decision points (Harvey pattern)
- **Interactive**: Full chat-based research (current chat agent)

---

## How This Applies to Our Agent

### For the Research Function (headless):
1. Split `request_guidance` into notify + ask
2. Add **completeness evaluation** before reporting (Harvey's "do I have enough?" step)
3. Build **workflow-defined checkpoints** at iteration 5/10 (not AI-decided)
4. Preserve error traces through compaction (don't compact failed searches)
5. Write intermediate findings to a scratch structure that survives compaction

### For the Chat Agent (interactive):
1. Actually USE `request_guidance` — add it to prompt guidance for when to ask vs. proceed
2. Add **plan mode** for research tasks ("here's my research plan, approve before I start")
3. Add **discovery editing** — let the agent update existing results mid-conversation
4. Show **thinking states** (Harvey pattern) — what the agent is doing and why

### For Both:
1. **Autonomy dial** in the UI — user picks the interaction level before starting
2. **Two-tier compaction** (Manus pattern) — compact first, summarize only as last resort
3. Pin system prompt prefix for KV-cache efficiency

---

## Plain English Summary

Every major AI agent handles the "when to pause" question differently, but they all agree on one thing: **don't leave it entirely up to the AI.** Harvey builds pause points into workflow templates. Claude Code uses a permission system that gates dangerous actions. Cursor lets the agent run freely in a sandbox and provides rewind. Manus heavily biases toward autonomy but has an explicit "ask the user" tool for genuine blockers.

For our agent, the biggest gaps are: (1) we have `request_guidance` but the agent barely uses it because the prompt doesn't tell it when to, (2) our research function has no "completeness check" before reporting — it just stops when it feels done, (3) results are final instead of editable, and (4) we don't separate progress notifications from actual questions.

The fix is to build structured checkpoints into the research workflow (Harvey's approach), split our messaging into notify vs. ask (Manus's approach), and make discoveries editable through chat (Claude Code's approach). The "autonomy dial" concept lets different users (Liav wants oversight, we want speed) both get what they need.
