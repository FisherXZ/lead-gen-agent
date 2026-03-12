# Deep Dive: Harvey AI, Claude Code, and Manus AI — Agent Patterns

**Date:** 2026-03-12
**Purpose:** Comprehensive, citation-verified breakdown of specific questions from the agent research doc

---

## Plain English Summary

This document digs into the "how" behind three AI agent systems. Harvey built a law firm hierarchy in code — a Partner AI delegates to Associate AIs, grades their work with a dual score (quality + self-certainty), and lets non-technical lawyers build custom workflows with a drag-and-drop block editor. Claude Code's Plan Mode is surprisingly simple — same model, same conversation, just a read-only system reminder and write tools removed — and their 6-layer memory system is architecturally designed around one thing: keeping the KV-cache prefix stable. Manus solved the "expensive tokens" problem by treating context like a desk you keep tidy — file everything to disk, keep only sticky-note references in working memory, and never change anything that's already been cached.

---

# HARVEY AI

---

## 1. Confidence Model — Grade + Confidence-in-Grade

### How It Works

Harvey's evaluation architecture produces **two distinct outputs** per evaluation:

- **Grade**: How well the model's output meets expected quality/correctness standards
- **Confidence Score**: How reliable that grade itself is — a meta-evaluation

> *"The evaluator uses this information to produce two results: a grade that reflects how well the model's output meets the expected quality or correctness standards, and a confidence score that indicates how reliable that grade is."*
> — [Scaling AI Evaluation Through Expertise](https://www.harvey.ai/blog/scaling-ai-evaluation-through-expertise)

### Technical Implementation

The system uses **model-based grading** with expert-curated rubrics. Inputs to the evaluator:
- The model's output
- The original user request
- Relevant domain documentation/knowledge bases
- Expert-provided rubrics

This is a **separate evaluation pass** — not inline with generation. Harvey runs these as part of their automated evaluation infrastructure, including nightly canary runs.

### Scales

- **Human evaluation**: **Likert 1–7** for independent assessments, plus **A/B preference tests** (anonymized side-by-side). Example result: GPT-4.1 vs GPT-4o showed mean improvement from 5.10 to 5.63 on the 7-point scale.
- **Automated confidence**: Scale not publicly specified. Described as indicating "how much trust to place in the evaluation."

### Rubric Dimensions

Expert-curated rubrics assess:
- **Structure** (formatted output requirements)
- **Style** (e.g., actionable advice emphasis)
- **Substance** (factual correctness)
- **Hallucination detection**

### Role in the Search Loop

The confidence model drives the **completeness evaluation** — step 4 of Harvey's 5-step agentic search:

1. Query Understanding & Planning
2. Dynamic Tool Selection & Retrieval (150+ knowledge sources)
3. Reasoning & Synthesis
4. **Completeness Check** — "do I have enough?" → if not, loop back to step 2
5. Citation-Backed Response

> *"With agentic search, Harvey iteratively refines its search until it finds all of the information it needs — yielding answers that are more complete and reliable."* Complex queries scale from 1 tool call to **3–10 retrieval operations** based on demand.
> — [How Agentic Search Unlocks Legal Research Intelligence](https://www.harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence)

### Preventing Overconfidence

- The **dual-output design itself** forces separate confidence assessment — flags cases where grade looks good but certainty is low
- **Randomized ordering, standardized prompts, anonymized content** reduce evaluation bias
- **Nightly canary evaluations** catch regressions before production
- **Human-in-the-loop** — engineers regularly call with BigLaw partners for direct feedback
- **BigLaw Bench** — published benchmark with lawyer-designed rubrics scoring answer quality + source reliability

### What We Don't Know

- Whether grade + confidence is a single structured-output prompt or two separate calls
- Exact numerical scale for automated confidence scores
- Specific threshold at which low confidence triggers re-evaluation
- Whether they use temperature sampling, majority voting, or ensemble techniques

**Sources:** [Scaling AI Evaluation Through Expertise](https://www.harvey.ai/blog/scaling-ai-evaluation-through-expertise), [How Agentic Search Unlocks Legal Research Intelligence](https://www.harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence), [Introducing BigLaw Bench](https://www.harvey.ai/blog/introducing-biglaw-bench)

---

## 2. Partner + Associate Model & Thinking States UI

### The Architecture

Harvey explicitly models its system after law firm hierarchy:

- **Partner Model**: Top-level orchestrator that *"creates a plan to solve overall tasks and identifies which subsystems to delegate portions of each task to."* Based on assignments, *"Harvey's subsystems receive the necessary context from the Partner model."*
- **Associate-Level Subsystems**: Individual model systems that receive delegated subtasks — *"similar to how partners coordinate complex, multi-step tasks — delegating the work in a specific order to specific associates."*

Source: [What AI Models Does Harvey Use?](https://help.harvey.ai/articles/what-ai-models-does-harvey-use)

### Harvey's Four-Level Hierarchy

1. **Models**: Individual AI systems (GPT-4o, o1, Claude, Gemini) — single prompt → single response
2. **Model Systems**: Multiple models + task-specific tools, knowledge sources, RAG databases — *"rigid one-way trips"* with *"preset model calls and informational handoffs"*
3. **Agents**: Model systems + Plan + Adapt + Interact capabilities
4. **Workflows**: One or more agents that collectively produce a work product — the client-facing layer

Source: [Introducing Agents in Harvey](https://www.harvey.ai/blog/introducing-harvey-agents)

### How 30–1,500 Model Calls Happen

Each request is *"routed to a cascading series of LLMs tuned for legal synthesis, RAG systems that incorporate public or user-provided data, and powerful reasoning models like o1 that help orchestrate the work end to end."*

- Agentic search alone scales queries to **3–10 retrieval operations**, each involving model calls for query formulation, retrieval, evaluation, and synthesis
- Platform processes **400,000+ agentic queries daily**
- The 30–1,500 figure comes from [Contrary Research](https://research.contrary.com/company/harvey) — consistent with the cascading architecture

### Thinking States UI

Users get real-time visibility into:
- **Agent's plan** and how decisions are made
- **Intermediate results** in easy-to-digest format
- **Real-time context** about what models are thinking as they work
- Ability to **intervene at any step** — adding context, tweaking parameters, rerunning actions
- **Paper trail** of thinking steps and citations — backtrack through logic, verify sources

> *"Rather than requiring users to craft detailed queries, Harvey agents actively guide them through each step of a task."*

Source: [Integrating Deep Research into Harvey](https://www.harvey.ai/blog/integrating-deep-research-into-harvey), [How We Approach Design at Harvey](https://www.harvey.ai/blog/how-we-approach-design-at-harvey)

---

## 3. Agent Builder — No-Code Workflow Creation

### Interface

The system is **fully no-code**. Two creation methods:

1. **Natural language**: *"Tell Harvey what you want to build in plain language"* → system constructs the workflow
2. **Visual block-based editor**: *"Use the no-code interface to lay out steps manually by connecting different blocks"*

Source: [Introducing Workflow Builder](https://www.harvey.ai/blog/introducing-workflow-builder)

### Three Building Blocks

| Block Type | Purpose |
|------------|---------|
| **Input** | Gather info from users — text descriptions, file uploads, document selections |
| **Prompt** | Processing steps — AI analysis and generation. Users choose model or let Harvey auto-select |
| **Display** | Present results — tables, documents, notices |

### Data Flow

- Blocks connect sequentially with **@-mentions** referencing previous block outputs: *"Tag the contents of previous input blocks in your prompts with an @-mention"*
- **Internal chaining**: intermediate steps can run behind the scenes — users see only the final output
- **Conditional branching**: workflows branch based on conditions (e.g., high vs. low buyer leverage in a Supply Agreement)

### Concrete Examples

- **NDA Generation**: 4 blocks — describe requirements → upload template → draft with reference → display
- **Discovery Objections**: 4 blocks — upload pleadings → identify objection grounds → generate table → display
- **Litigation Hold Notice**: 5 blocks with internal chaining — upload complaint → identify categories → generate notice → display (user sees only final notice)

### Scale

- **25,000+** custom agentic workflows built by legal teams
- **400,000+** agentic queries daily
- GSK Stockmann: cut due diligence by **75%**
- Filip & Company: lawyers save **5 hours weekly**
- Paul Weiss served as **core design partner**

### Technical Storage (Inferred)

Harvey hasn't published the internal representation. What we know:
- User-facing is a **visual block graph** with sequential and branching connections
- Workflows are **versionable** and **shareable** with granular permissions
- Each block has a model assignment (auto or manual)
- Evolution from rigid Workflow Builder to flexible Agent Builder suggests shift from static DAG configs to more dynamic goal-oriented orchestration

**Sources:** [Introducing Agent Builder](https://www.harvey.ai/blog/introducing-agent-builder), [Introducing Workflow Builder](https://www.harvey.ai/blog/introducing-workflow-builder), [Getting Started with Workflow Builder](https://www.harvey.ai/blog/getting-started-with-workflow-builder-5-workflows-we-recommend), [Paul Weiss + Harvey](https://www.harvey.ai/blog/paul-weiss-harvey-workflow-builder)

---

## 4. Citation Verification — 95%+ Accuracy

### The Three-Stage Pipeline

**Stage 1: Structured Metadata Extraction**

> *"The process starts with structured metadata extraction from each citation, parsing details such as the title, source collection, volume/issue (if any), page range, author/organization, and publication date."*

Extracts machine-readable fields from raw citation strings that may be formatted inconsistently.

**Stage 2: Embedding-Based Retrieval**

Two paths depending on metadata quality:
- **Reliable publication data → database query**: Exact metadata matching against internal database
- **Partial metadata (title fragment only) → embedding retrieval with date filters**: Handles *"high-volume fuzzy matching"* across millions of legal documents with *"metadata weighting of fields like document name, date, parties, and publication"*

**Stage 3: Binary LLM Matching**

> *"An LLM performs a binary document-matching evaluation, confirming whether the retrieved candidate refers to the same document as the original citation."*

**"Binary" means yes/no**: Does this retrieved candidate match the cited document? Not a similarity score — a definitive match/no-match classification. This is the final verification gate after retrieval narrows candidates.

### Result

> *"This combination of structured parsing, intelligent retrieval, and LLM-based judgment has yielded over 95% accuracy on their internal benchmark dataset validated by attorneys."*

Source: [Scaling AI Evaluation Through Expertise](https://www.harvey.ai/blog/scaling-ai-evaluation-through-expertise)

### What We Can Apply to EPC Research

1. **Structured metadata extraction first** — parse sources into fields (company, project, location, date, source type) before fuzzy matching
2. **Two-tier retrieval** — exact DB lookups with strong identifiers, embedding search with partial info
3. **Binary LLM verification as final gate** — simple yes/no prompt: "Does this source support that [company X] is EPC for [project Y]?"
4. **Separate confidence from grade** — output both "is this correct?" AND "how sure am I about that?"
5. **Metadata weighting** — company name + project name + state >> company name alone

---

# CLAUDE CODE

---

## 1. How Plan Mode Is Implemented

### Activation

Press **Shift+Tab** to cycle through modes: Default → Auto-accept edits → **Plan mode**. Or use `/plan` or `--plan` flag.

### What Happens Under the Hood — Two Enforcement Layers

**Layer A: System reminder injected into every user message:**

> *"Plan mode is active. The user indicated that they do not want you to execute yet — you MUST NOT make any edits (with the exception of the plan file mentioned below), run any non-readonly tools (including changing configs or making commits), or otherwise make any changes to the system."*
> — [Sergey Karayev on X](https://x.com/sergeykarayev/status/1965575615941411071)

**Layer B: Enhanced Plan subagent prompt (~685 tokens):**

> *"=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS === This is a READ-ONLY planning task. You are STRICTLY PROHIBITED from: Creating new files... Your role is EXCLUSIVELY to explore the codebase and design implementation plans."*
> — [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/agent-prompt-plan-mode-enhanced.md)

### Same Model, NOT a Separate Agent

Plan mode uses the **same Claude model** with the same conversation context. The only differences:
1. System reminder injection
2. Write tools filtered out

### Tools Available

| Plan Mode (Read-Only) | Restricted |
|---|---|
| Read, LS, Glob, Grep | Edit, MultiEdit, Write |
| Task (research subagents) | Bash (command execution) |
| TodoRead/TodoWrite | NotebookEdit |
| WebFetch, WebSearch | MCP tools that modify state |
| NotebookRead | Git write operations |

**Exception:** CAN write to `~/.claude/plans/` — plan files only.

### Important Limitation

Enforcement is **primarily prompt-based, with tool-level filtering as secondary**. Armin Ronacher (Flask creator) analyzed this:

> *"The read-only behavior is enforced through instructions rather than technical restrictions... plan mode, like all prompts, is essentially a strong suggestion to the model."*
> — [lucumr.pocoo.org](https://lucumr.pocoo.org/2025/12/17/what-is-plan-mode/)

Known GitHub issue ([#19874](https://github.com/anthropics/claude-code/issues/19874)): write operations can execute despite the read-only guarantee in edge cases.

### Why System Reminder Instead of System Prompt Change

**KV cache optimization.** If plan mode modified the system prompt, it would invalidate the entire KV cache. By injecting instructions as a `<system-reminder>` in user messages, the cached prefix stays valid.

> Thariq Shafi (Claude Code engineer): the team *"builds our entire harness around prompt caching"* and *"treats drops in cache hit rate as production incidents."*
> — [Implicator.ai](https://www.implicator.ai/anthropic-says-cache-misses-are-production-incidents-reveals-caching-shaped-claude-code/)

### Transition to Execution

1. Claude writes structured markdown plan to `~/.claude/plans/<name>.md`
2. User reviews, iterates, asks questions
3. User exits plan mode (Shift+Tab or tells Claude to proceed)
4. Claude gets full tool access restored and executes the plan

**No automated handoff** — user explicitly switches modes.

**Sources:** [Claude Code Docs](https://code.claude.com/docs/en/how-claude-code-works), [Sergey Karayev](https://x.com/sergeykarayev/status/1965575615941411071), [Piebald-AI](https://github.com/Piebald-AI/claude-code-system-prompts), [Armin Ronacher](https://lucumr.pocoo.org/2025/12/17/what-is-plan-mode/), [Sondera AI](https://blog.sondera.ai/p/claude-codes-plan-mode-isnt-read)

---

## 2. CLAUDE.md + Six Layers of Memory

### The Six Layers (Most Stable → Most Dynamic)

**Layer 1: System Prompt (~4,000 tokens)**
Static, identical across all sessions/users. Defines Claude's identity, safety rules, core behavior. First part of cached prefix.

**Layer 2: Tool Definitions (~14,000+ tokens)**
All available tools as structured JSON schemas. Together with Layer 1, forms the **cached prefix** (~18K+ tokens). Adding MCP servers increases this.

**Layer 3: CLAUDE.md Files (variable, target <200 lines each)**
All in-scope CLAUDE.md + unconditional `.claude/rules/` files. Loaded at session start as **messages** (NOT system prompt).

**Why messages, not system prompt?** If CLAUDE.md were part of the system prompt, any edit would change the prefix hash and invalidate the KV cache. As messages, the prefix stays stable. Result: **92% cache hit rate, 81% cost reduction**.

Resolution order (walking UP from cwd):
1. Managed Policy (macOS: `/Library/Application Support/ClaudeCode/CLAUDE.md`)
2. User-level: `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md`
3. Project-level: `./CLAUDE.md` or `./.claude/CLAUDE.md`
4. Subdirectory CLAUDE.md: loaded **on-demand** when Claude reads files in those dirs
5. Path-scoped rules: `.claude/rules/*.md` with `paths:` frontmatter — loaded when matching files are accessed

**Layer 4: Auto Memory (MEMORY.md — first 200 lines only)**
Claude's self-written notes from previous sessions at `~/.claude/projects/<project>/memory/MEMORY.md`.
- Only first 200 lines load at startup
- Topic files (e.g., `debugging.md`) are NOT loaded — Claude reads on-demand
- All worktrees in same git repo share one memory directory

**Layer 5: Conversation History**
Your messages + Claude's responses + tool results. Most dynamic layer. Subject to **compaction** near context limit — CLAUDE.md is re-read from disk and re-injected fresh after compaction.

> *"CLAUDE.md fully survives compaction. After /compact, Claude re-reads your CLAUDE.md from disk and re-injects it fresh."*

**Layer 6: System Reminders (Dynamic Injections)**
`<system-reminder>` tags dynamically injected by the harness into user messages/tool results:
- Plan mode instructions, current date, skill metadata, file edit notifications, git status, permission state
- Can consume **15%+ of context** ([Issue #17601](https://github.com/anthropics/claude-code/issues/17601))
- High recency = **strong influence** on Claude's behavior (by design)

### Precedence (Practical, Highest → Lowest)

1. System reminders (Layer 6) — highest recency
2. Recent conversation (Layer 5) — recency bias
3. Subdirectory/path-scoped CLAUDE.md — most specific scope
4. Project CLAUDE.md (Layer 3)
5. User CLAUDE.md
6. Managed Policy CLAUDE.md
7. System prompt (Layer 1) — stable but oldest

Note: This is attention-based precedence, not hard enforcement. Contradictions may be resolved arbitrarily.

### The @import System

CLAUDE.md can import external files: `@README`, `@package.json`
- Relative and absolute paths supported
- Recursive imports, max depth 5
- First external import shows approval dialog

**Sources:** [Claude Code Docs - Memory](https://code.claude.com/docs/en/memory), [Implicator.ai](https://www.implicator.ai/anthropic-says-cache-misses-are-production-incidents-reveals-caching-shaped-claude-code/), [Issues #18560](https://github.com/anthropics/claude-code/issues/18560), [#17601](https://github.com/anthropics/claude-code/issues/17601), [#4464](https://github.com/anthropics/claude-code/issues/4464)

---

## 3. Tool Design — Anthropic's Philosophy

### "Choose High-Leverage Tools"

Don't create many granular tools. Consolidate.

**Bad — four separate tools:**
```
get_expense_by_id(id)
list_all_expenses()
filter_expenses_by_category(category)
search_expenses(query)
```

**Good — one consolidated tool:**
```
query_expenses(id?, category?, search?, limit?, offset?)
```

Tools should *"handle potentially multiple discrete operations (or API calls) under the hood"* and *"enrich tool responses with related metadata."*

Source: [Anthropic - Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

### "Tool Descriptions Are Prompts"

> *"Every word in your tool's name, description, and parameter documentation shapes how agents understand and use it."*

Think of it as *"writing a great docstring for a junior developer."*

**Bad parameter:** `start_date: string`
**Good parameter:** `start_date: ISO date string (YYYY-MM-DD) for the beginning of the expense search range. Required.`

**Bad field name:** `user`
**Good field name:** `user_id`

### "Human-Readable Fields"

> *"Agents reason better with human-readable fields and simplified outputs than with raw technical IDs."*

`{"user": "Jane Smith", "status": "active"}` >>> `{"id": "usr_7x9f2k", "status": 3}`

### Pagination, Truncation, Filtering

> *"Implement some combination of pagination, range selection, filtering, and/or truncation with sensible default parameter values for any tool responses that could use up lots of context."*

**The address book anti-pattern:**

> *"If an LLM agent uses a tool that returns ALL contacts and then has to read through each one token-by-token, it's wasting its limited context space on irrelevant information. The better approach is to skip to the relevant page first."*

### The Absolute Filepath Lesson

> *"The model made mistakes with tools using relative filepaths. To fix this, we changed the tool to always require absolute filepaths — and we found that the model used this method flawlessly."*

This is why Claude Code's Read/Edit tools require absolute paths.

### Evaluation-Driven Development

1. Build prototype tool
2. Design realistic tasks exercising the tool
3. Run agent with tool on those tasks
4. Examine: total runtime, tool calls, token consumption, error rates
5. Iterate on descriptions, parameters, output format

> Claude Sonnet 3.5 achieved state-of-the-art SWE-bench after *"precise refinements to tool descriptions, dramatically reducing error rates."* The agent had only a prompt, Bash tool, and Edit tool.

Source: [Anthropic - SWE-bench Sonnet](https://www.anthropic.com/research/swe-bench-sonnet)

### Context Engineering > Prompt Engineering

> *"Building effective AI agents is less about finding the right words and more about answering a critical question: What configuration of context is most likely to generate our model's desired behavior?"*

Four operations for context management:

| Operation | Definition | Claude Code Example |
|---|---|---|
| **Write** | Save context outside the window | Auto memory (MEMORY.md) |
| **Select** | Pull relevant context in | JIT skill loading, path-scoped rules |
| **Compress** | Retain only needed tokens | `/compact`, conversation summarization |
| **Isolate** | Split context to prevent interference | Subagents with separate context windows |

Key result: Multi-agent with isolated contexts **outperformed single Claude Opus 4 by 90.2%** on breadth-first research tasks.

**Sources:** [Writing Effective Tools](https://www.anthropic.com/engineering/writing-tools-for-agents), [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), [Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

---

# MANUS AI

---

## 1. How KV-Cache Actually Works and Saves Money

### First Principles

In a transformer, every input token produces three vectors: **Query (Q)**, **Key (K)**, and **Value (V)**. During autoregressive generation, the model computes attention between the new token and ALL previous tokens. Without caching, this means recomputing K and V for every previous token at every step — **quadratic scaling**.

KV-cache stores K and V vectors from all previous tokens for reuse. Only the new token's Q, K, V need fresh computation. Result: **quadratic → linear scaling**.

Benchmark: Tesla T4 GPU — **11.9 seconds with KV cache vs 56.2 seconds without** (~5x speedup).

Source: [Hugging Face KV Caching](https://huggingface.co/blog/not-lain/kv-caching), [Data Science Dojo](https://datasciencedojo.com/blog/kv-cache-how-to-speed-up-llm-inference/)

### Why 10x Cost Difference at the API Level

Anthropic's **prompt caching** operates at the API level as **prefix caching**. When your request's beginning matches a previous request exactly, Anthropic reuses pre-computed KV vectors from GPU memory.

| Token Type | Cost (Claude Sonnet) | Multiplier |
|---|---|---|
| Cache read (hit) | $0.30/MTok | 0.1x base |
| Cache write (miss, first time) | $3.75/MTok | 1.25x base |
| Standard (no caching) | $3.00/MTok | 1x base |
| TTL | 5 minutes standard, 1 hour at 2x | — |

> *"Reducing costs by up to 90% and latency by up to 85% for long prompts."*
> — [Anthropic Prompt Caching Announcement](https://www.anthropic.com/news/prompt-caching)

### How Manus Optimizes — Five Rules

From [Manus Context Engineering Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus):

**1. Stable prompt prefixes** — no timestamps or variable content at the start.
> *"A common mistake is including a timestamp — especially one precise to the second — at the beginning of the system prompt, which kills your cache hit rate."*

**2. Append-only context** — never modify previous actions or observations. Only add new content at the end.

**3. Deterministic serialization** — ensure JSON key ordering is stable.
> *"Many programming languages and libraries don't guarantee stable key ordering when serializing JSON objects, which can silently break the cache."*

**4. Tool masking not removal** — keep tool definitions constant, use logit masking during decoding to prevent selection of unavailable tools.

**5. Explicit cache breakpoints** — mark where cache boundaries should be.

### Why a Single Token Change Invalidates the Cache

Two reasons, one at each level:

**API level:** Anthropic uses **hash-based prefix matching**. Tokens are hashed sequentially. A change at token #5 produces a different hash from #5 onward — everything after is a cache miss.

**Transformer level:** If token #5 changes, its K and V vectors change. Every subsequent token's representation was computed attending to the old token #5. Their KV vectors are invalid because they were computed with stale attention. The cascade invalidates everything downstream.

Cache hierarchy: **tools → system → messages**. Changes to tools invalidate everything. Changes to messages only invalidate from the divergence point.

Source: [Anthropic Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

### Tool Masking vs Tool Removal

**Tool removal** = dynamically add/remove tool definitions per request. Breaks cache because tools are part of the prompt prefix (first in Anthropic's cache hierarchy). Changing tools invalidates tools + system + messages — the ENTIRE cache.

**Tool masking** = keep all tool definitions constant. Use **logit masking during decoding** — set logits for disallowed tool tokens to negative infinity. Model can't choose masked tools, but prompt (and cache) stays identical.

Bonus: *"When previous actions and observations still refer to tools that are no longer defined in the current context, the model gets confused."* Masking avoids this.

### Practical Steps for Our Agent

1. **Lock system prompt prefix.** Move variable content (current date, user info) to the END. `prompts.py` should have static content first, dynamic last.

2. **Never modify previous messages.** If `compact_messages()` replaces old tool results and those are re-sent, each compaction changes the prefix. Consider: compact only at conversation boundaries.

3. **Keep tool definitions static.** Send ALL tools every time. If tools shouldn't be available in certain states, reject the call in application logic — don't remove the tool from the API request.

4. **Deterministic JSON serialization.** `json.dumps(data, sort_keys=True)` in Python.

5. **Set cache breakpoints.** Use Anthropic's `cache_control` parameter on system prompt and tool definitions.

6. **Monitor cache metrics.** Check `cache_read_input_tokens` and `cache_creation_input_tokens` in API responses.

7. **Use automatic caching.** Add `cache_control` at top level of request body.

**Sources:** [Manus Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), [Anthropic Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [ZenML Analysis](https://www.zenml.io/llmops-database/context-engineering-strategies-for-production-ai-agents)

---

## 2. Manus File System vs Claude Code Memory — Comparison

### Manus: File System as Unlimited Memory

> *"Share memory by communicating, don't communicate by sharing memory."*

- Agent runs in a **sandboxed VM** with full file system access
- Intermediate results written to files (search outputs, scraped pages, analysis)
- Only conclusions and references stay in context window
- When old info needed, agent reads the file back
- Context window = working memory scratchpad; file system = long-term storage

### Claude Code: Layered In-Context Memory

| Layer | Scope | Persistence | Location |
|-------|-------|-------------|----------|
| System prompt | Global | Permanent | Hardcoded |
| User CLAUDE.md | Per-user | Permanent | `~/.claude/CLAUDE.md` |
| Project CLAUDE.md | Per-repo | Permanent (git) | Repo root `CLAUDE.md` |
| Modular rules | Per-file-type | Permanent | `.claude/rules/*.md` |
| MEMORY.md | Per-user-per-project | Permanent (local) | 200-line limit |
| Conversation | Per-session | Session only | Subject to compaction |

### Side-by-Side Comparison

| Dimension | Manus (File System) | Claude Code (Layers) |
|-----------|--------------------|--------------------|
| **Capacity** | Unlimited (disk) | ~200K tokens, 200-line MEMORY.md |
| **Retrieval** | On-demand via tools (grep, cat) | Always in context (CLAUDE.md) or lost |
| **Cache friendliness** | Excellent — offloading keeps context stable | Moderate — compaction changes prefix |
| **Precision** | High — reads exactly what's needed | Variable — may lose in compaction |
| **Overhead** | Extra tool calls per retrieval | Zero for CLAUDE.md; compaction is auto |
| **Multi-session** | Files persist naturally | CLAUDE.md persists; conversation doesn't |
| **Multi-agent** | Each gets own sandbox, no contamination | Shared CLAUDE.md context |
| **Complexity** | Agent must learn file management | Simple hierarchy, mostly automatic |

### Which Is Better When

- **Long multi-step research** (like EPC discovery): **Manus wins** — write search results to files, keep only summaries in context
- **Short instruction-heavy sessions**: **Claude Code wins** — rules in CLAUDE.md stay present without tool calls
- **Multi-agent workflows**: **Manus wins** — isolated sandboxes, no shared context contamination

### The Todo.md Problem

Manus agents naturally created `todo.md` for task planning, updating it after each step. This pushed the global plan into recent attention span (combating "lost-in-the-middle").

**The problem:** ~**1/3 of all agent actions** were spent updating the todo file — 30% of tokens wasted on bookkeeping.

**The solution:** Replace free-form `todo.md` with a **dedicated Planner sub-agent** that returns a structured Plan object. The planner manages the plan separately; the executor just works.

**Plain English:** Like spending a third of your work day rewriting your to-do list. Fix: hire a dedicated planner who hands you an updated checklist at the start of each session.

**Sources:** [Manus Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), [Manus Sandbox](https://manus.im/blog/manus-sandbox), [Lance Martin Analysis](https://rlancemartin.github.io/2025/10/15/manus/)

---

## 3. Two-Tier Compaction — How It Actually Works

### The Three Tiers

Strict preference order: **Raw > Compaction > Summarization (last resort)**

**Tier 1 — Raw:** Full unmodified tool call results.

**Tier 2 — Compaction:** Every tool call has two formats — full and compact. Compact strips info reconstructable from file system.

**Tier 3 — Summarization:** Only when compaction has "diminishing returns." Separate LLM call generates structured summaries.

### What Compact Format Looks Like

| Stays in Compact | Stripped (Recoverable from Files) |
|-----------------|----------------------------------|
| File path reference | Full file contents |
| Result count ("20 results") | Individual result details |
| Key identifiers (names, IDs) | Full metadata per item |
| Success/failure status | Stack traces, verbose errors |
| Summary sentence | Raw HTML/JSON responses |

Example: A search returning 20 results → compact version becomes file path + `"20 results found, top 3: Solar Farm Alpha, Desert Sun Project, Mesa Verde EPC"`. Full data stays on disk.

### How They Decide What to Compact

When context exceeds threshold (~128K tokens):
- Apply compaction to **oldest turns first**
- Target approximately the **oldest ~50%** of turns
- Keep recent turns in raw format
- Sliding window — progressively compact older content

### Why Keep Last 3 Turns Raw — "Rhythm"

Keeping recent tool calls in full raw format preserves:
- Output format consistency (JSON, markdown style)
- Decision-making momentum (what tools to call next)
- Level of detail in responses
- Error recovery behavior

> *"Leave the wrong turns in the context. When the model sees a failed action — and the resulting observation or stack trace — it implicitly updates its internal beliefs."*

### Comparison to Our Current Compaction

| Aspect | Our Implementation | Manus's Approach |
|--------|-------------------|-----------------|
| **Trigger** | `estimate_context_size > 100K chars` | ~128K tokens |
| **Protected turns** | Last 6 (`KEEP_RECENT_TURNS = 6`) | Last 3 |
| **Method** | Replace content > 500 chars with JSON stubs | Two formats per tool; compact references file system |
| **Stub content** | `{"_compacted": true, "tool": "...", "summary": "..."}` | File path + brief summary (data stays on disk) |
| **File system offload** | **No — data is lost** | **Yes — full results persist in files** |
| **Summarization tier** | Not implemented | Separate LLM call, last resort |
| **Reversibility** | Partial — stubs have summaries but originals gone | **Fully reversible** — agent re-reads files |

### Five Key Differences from "Just Summarize Old Stuff"

1. **Reversibility.** Compaction is lossless (data on disk). Summarization is lossy — details unrecoverable.

2. **No LLM call for compaction.** Switching full → compact is deterministic (swap for file reference). Summarization needs an expensive LLM call.

3. **Graduated degradation.** Raw → compact → summary is a smooth spectrum. Minimum information loss at each step.

4. **Cache preservation.** Compaction modifies older turns (less likely in cache prefix). Recent turns stay identical → cache hits preserved. Naive summarization rewrites everything, destroying cache.

5. **Structured output.** Summaries follow a schema, not free-form text. Machine-parseable, reducing misinterpretation risk.

**Plain English:** Think of cleaning your desk. Naive summarization = throw away all papers, write a one-page summary. Manus's approach = file papers in a cabinet (file system), leave sticky notes on desk (compact references) saying where to find each document. Only write a summary as a last resort when even sticky notes take too much space.

**Sources:** [Manus Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), [Phil Schmid Analysis](https://www.philschmid.de/context-engineering-part-2), [Lance Martin](https://rlancemartin.github.io/2025/10/15/manus/), [ZenML](https://www.zenml.io/llmops-database/context-engineering-strategies-for-production-ai-agents)

---

## Complete Source Index

### Harvey AI
- [Scaling AI Evaluation Through Expertise](https://www.harvey.ai/blog/scaling-ai-evaluation-through-expertise)
- [How Agentic Search Unlocks Legal Research Intelligence](https://www.harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence)
- [Introducing Agents in Harvey](https://www.harvey.ai/blog/introducing-harvey-agents)
- [Introducing Agent Builder](https://www.harvey.ai/blog/introducing-agent-builder)
- [Introducing Workflow Builder](https://www.harvey.ai/blog/introducing-workflow-builder)
- [Getting Started with Workflow Builder](https://www.harvey.ai/blog/getting-started-with-workflow-builder-5-workflows-we-recommend)
- [Integrating Deep Research into Harvey](https://www.harvey.ai/blog/integrating-deep-research-into-harvey)
- [What AI Models Does Harvey Use?](https://help.harvey.ai/articles/what-ai-models-does-harvey-use)
- [Harvey + OpenAI o1](https://www.harvey.ai/blog/harvey-building-legal-agents-and-workflows-with-openai-s-o1)
- [How We Approach Design at Harvey](https://www.harvey.ai/blog/how-we-approach-design-at-harvey)
- [Paul Weiss + Harvey](https://www.harvey.ai/blog/paul-weiss-harvey-workflow-builder)
- [Introducing BigLaw Bench](https://www.harvey.ai/blog/introducing-biglaw-bench)
- [Contrary Research: Harvey](https://research.contrary.com/company/harvey)

### Claude Code / Anthropic
- [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Writing Effective Tools for AI Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [SWE-bench Sonnet](https://www.anthropic.com/research/swe-bench-sonnet)
- [Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Prompt Caching Announcement](https://www.anthropic.com/news/prompt-caching)
- [Claude Code Docs - How It Works](https://code.claude.com/docs/en/how-claude-code-works)
- [Claude Code Docs - Memory](https://code.claude.com/docs/en/memory)
- [Armin Ronacher - Plan Mode](https://lucumr.pocoo.org/2025/12/17/what-is-plan-mode/)
- [Piebald-AI System Prompts](https://github.com/Piebald-AI/claude-code-system-prompts)
- [Sergey Karayev on X](https://x.com/sergeykarayev/status/1965575615941411071)
- [Sondera AI - Plan Mode](https://blog.sondera.ai/p/claude-codes-plan-mode-isnt-read)
- [Implicator.ai - Cache Misses](https://www.implicator.ai/anthropic-says-cache-misses-are-production-incidents-reveals-caching-shaped-claude-code/)
- [LangChain - Context Engineering](https://blog.langchain.com/context-engineering-for-agents/)
- GitHub Issues: [#19874](https://github.com/anthropics/claude-code/issues/19874), [#19649](https://github.com/anthropics/claude-code/issues/19649), [#18560](https://github.com/anthropics/claude-code/issues/18560), [#17601](https://github.com/anthropics/claude-code/issues/17601)

### Manus AI
- [Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Wide Research: Beyond the Context Window](https://manus.im/blog/manus-wide-research-solve-context-problem)
- [Understanding Manus Sandbox](https://manus.im/blog/manus-sandbox)
- [Lance Martin - Manus Analysis](https://rlancemartin.github.io/2025/10/15/manus/)
- [Phil Schmid - Context Engineering Part 2](https://www.philschmid.de/context-engineering-part-2)
- [ZenML - Context Engineering Strategies](https://www.zenml.io/llmops-database/context-engineering-strategies-for-production-ai-agents)

### KV-Cache Technical
- [Hugging Face - KV Caching](https://huggingface.co/blog/not-lain/kv-caching)
- [Data Science Dojo - KV Cache](https://datasciencedojo.com/blog/kv-cache-how-to-speed-up-llm-inference/)
- [Sebastian Raschka - KV Cache](https://magazine.sebastianraschka.com/p/coding-the-kv-cache-in-llms)
