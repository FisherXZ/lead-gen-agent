# Tool Budgeting and Resource Management in LLM Agents

*Research date: 2026-05-17. Context: solar-gen, a Python Claude-based agent with ~40 tools, long-running research jobs, and context compaction.*

This document synthesizes published practices from Claude Code, Anthropic's multi-agent research system, Cognition (Devin), Manus, Cursor, OpenHands, Aider, LangChain/LangGraph, AutoGen, smolagents, the Claude Agent SDK, and academic work (Reflexion, AutoGPT post-mortems). It ends with a concrete recommendation table for solar-gen.

## Plain English

Agents that "just keep going" are the #1 way to burn money and pollute their own thinking. Every well-run agent system enforces three kinds of budgets: (1) **per-call** caps so a single tool response can't dump 200 KB into the model's brain, (2) **per-task** caps on number of tool calls so a stuck agent stops itself, and (3) **per-job dollar/token** caps as a final circuit breaker. On top of that they add loop detection ("did I just call this exact thing five times?"), rate-limit handling for external APIs, and context compaction so the conversation can run forever without filling up. The numbers below come from real production systems; we use them as priors, not gospel.

## 1. Per-call token / output budgets

The pattern across mature agents is: **tools cap their own output, signal truncation, and let the model re-query for more.** A tool that can return arbitrary-size data is a foot-gun.

- **Claude Code – Bash tool.** Default output cap is **30,000 characters**, configurable via `BASH_MAX_OUTPUT_LENGTH`. When exceeded, Claude Code applies *middle-truncation* (keeps head + tail), and in newer versions writes the full output to a session-directory file and gives Claude only a path + preview. ([Claude Code issue #19901](https://github.com/anthropics/claude-code/issues/19901), [issue #12054](https://github.com/anthropics/claude-code/issues/12054))
- **Claude Code – Read tool.** Default **2,000 lines** from offset 0; lines longer than **2,000 characters** are truncated; there is also a hard ~**25,000-token** ceiling per read that returns an error rather than partial content, forcing the model to use `offset`/`limit`. ([Claude Code issue #6910](https://github.com/anthropics/claude-code/issues/6910), [issue #14888](https://github.com/anthropics/claude-code/issues/14888))
- **Claude Code – Grep tool.** Caps results at **100 files** (sorted by mtime), and exposes a `head_limit` parameter that limits content/file lists/counts. On hit, a truncation flag is set so the model can narrow the pattern. ([Claude Agent SDK TS issue #72](https://github.com/anthropics/claude-agent-sdk-typescript/issues/72))
- **Trae Agent.** Truncates each tool response to the **first 16 KB**. (cited in [CodeAnt blog](https://www.codeant.ai/blogs/poor-tool-calling-llm-cost-latency))
- **Manus.** Routes token-heavy outputs (search results, fetched pages) to the **file system** and feeds the model only a path/handle. Treats the FS as externalized memory rather than compressing in-band. ([Manus blog: Context Engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), [rlancemartin.github.io 2025-10-15](https://rlancemartin.github.io/2025/10/15/manus/))
- **Aider.** The repo map is **token-budgeted** (`--map-tokens`, default 1k) and uses binary search over a PageRank ranking to fit the budget. ([aider.chat/docs/repomap.html](https://aider.chat/docs/repomap.html))

**Design principle (universal):** every tool should declare a max output size, return a truncation signal, and where possible return a *handle* (file path, document ID, search-result ID) the agent can drill into instead of the raw blob.

## 2. Per-turn / per-task call budgets

Almost every framework ships an iteration cap. The numbers cluster surprisingly tightly.

| System | Default | Knob |
|---|---|---|
| **Cursor (agent mode)** | 25 tool calls / interaction | "Continue" prompt at the ceiling; MAX mode raises to **200** ([apidog](https://apidog.com/blog/cursor-tool-call-limit/)) |
| **LangGraph** | `recursion_limit = 25` | Raises `GraphRecursionError` ([LangChain docs](https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT)) |
| **LangChain AgentExecutor** | `max_iterations = 15` (legacy) | Returns partial answer |
| **OpenHands** | `max_iterations = 500` in config, `-i` flag on CLI | Hard abort ([OpenHands config.template.toml](https://github.com/OpenHands/OpenHands/blob/main/config.template.toml)) |
| **AutoGen** | `max_consecutive_auto_reply` (no default, must set) + `max_turns` for chats | Switches to human input or terminates ([AutoGen 0.2 docs](https://microsoft.github.io/autogen/0.2/docs/reference/agentchat/conversable_agent/)) |
| **smolagents** | `max_steps` (per-agent default, commonly 6–20) | Raises step-limit error ([HF docs](https://huggingface.co/docs/smolagents/reference/agents)) |
| **Anthropic multi-agent research** | Heuristic: simple fact-find = 3–10 calls; comparison = 2–4 subagents × 10–15 calls; complex = 10+ subagents | Embedded in the lead agent's prompt ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system)) |

**Behavior at the ceiling.** Three patterns:
1. **Hard error / abort** (LangGraph, OpenHands, smolagents). Best for batch jobs.
2. **Force-answer**: agent must produce a final answer with whatever it has (legacy LangChain AgentExecutor "early stopping"). Best for chat UX.
3. **Escalate to human / "Continue?" prompt** (Cursor). Best for interactive IDE use.

For solar-gen's long-running research jobs, **hard abort with a partial-result artifact** matches the pattern best — we're not in an interactive chat.

## 3. Dollar / token cost budgets

This is the layer most frameworks under-emphasize. The well-documented examples:

- **OpenHands** has three explicit ceilings: `MAX_ITERATIONS`, `LLM_NUM_RETRIES` (default 8), and `max_budget_per_task` in USD (CLI flag `-b 10.0` = $10 cap). The advice is explicit: "don't ship a headless agent without all three." ([OpenHands metrics docs](https://deepwiki.com/OpenHands/OpenHands/8.4-agent-implementations))
- **OpenAI Agents SDK** auto-tracks usage on the run object (`result.context_wrapper.usage`) including handoffs and tool calls; no built-in dollar cap — you must enforce it yourself. ([OpenAI Agents SDK usage docs](https://openai.github.io/openai-agents-python/usage/))
- **Anthropic multi-agent research.** "Token usage by itself explains **80% of the variance** in BrowseComp performance." Multi-agent uses ~**15×** more tokens than chat; single-agent ~**4×**. The economic guidance: only deploy multi-agent for high-value tasks. ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system))
- **AutoGPT post-mortems.** A widely circulated incident: a missing budget layer cost **$47K**; users routinely racked up hundreds of dollars on simple goals because there was no `max_budget`. The lesson cited everywhere: "the agent ecosystem hasn't yet built circuit breakers for tool-call patterns." ([awesome-agent-failures](https://github.com/vectara/awesome-agent-failures/blob/main/docs/case-studies/autogpt-planning-failures.md))
- **Cost-aware tool selection.** Less codified. Manus emphasizes **KV-cache hit rate as the #1 production metric** because cached input tokens on Sonnet are ~**10× cheaper** than uncached — so preserving stable prefixes and avoiding tool-list churn is itself a cost optimization. ([Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus))
- **Pre-call cost estimation** is largely DIY: estimate input tokens of the prompt + tool schemas, multiply by per-model rates, refuse to dispatch if predicted spend would exceed remaining budget.

## 4. Rate limiting and concurrency

External research tools (Tavily, Exa, Brave, Firecrawl) all have meaningful RPS caps.

- **Brave Search free tier:** 1 RPS. 429 returns `X-RateLimit-Reset`. ([Brave Search rate-limiting docs](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting))
- **Exa default:** 10 QPS across endpoints; standard practice is **exponential backoff with jitter**, retry on 429 + 5xx only. ([Exa rate-limit guide](https://lobehub.com/skills/jeremylongshore-claude-code-plugins-plus-skills-exa-rate-limits))
- **Tavily free tier:** 1,000 searches/month, with documented per-minute caps on paid tiers. ([Tavily docs](https://docs.tavily.com/documentation/rate-limits))

**Coordination patterns:**
- A **token bucket per provider** in the agent process, sized to ~80% of the documented cap (leaves headroom for parallel subagents).
- **Exponential backoff with jitter** for 429/5xx, max 3–5 retries, retry budget counted against the per-task tool-call cap so a flaky provider can't pad the iteration count.
- **Parallel tool calls.** Anthropic's research system spins up 3–5 subagents in parallel and each subagent uses 3+ tools in parallel — but this only works if your rate-limiting bucket is shared across goroutines/asyncio tasks.
- **Fallback provider chain** (e.g. Tavily → Exa → Brave) for critical search calls, so 429s don't abort the task.

## 5. Context window budgeting and compaction

Long-running agents *must* assume the context will be compacted; tools must be designed accordingly.

- **Claude API automatic context compaction.** Configurable via `compaction_control`; can drop tool-result content while keeping the call's metadata (so the agent knows it called X but not the 200KB it returned). For Opus 4.6+, **server-side compaction** is the recommended path. ([Claude API: Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction))
- **Claude API context editing** (`clear_tool_uses_20250919` strategy, beta header `context-management-2025-06-27`). Clears oldest tool results past a configurable threshold, replaces with placeholder text. `clear_at_least` parameter prevents wasteful micro-clears (and resulting cache invalidation). `clear_tool_inputs` toggles whether the call args also get removed. ([Claude API: Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing))
- **LangGraph** offers four strategies: **write, select, compress, isolate**. The `SummarizationNode` triggers an LLM summary when cumulative tokens cross a threshold (commonly **85% of `max_input_tokens`**), keeping the most recent ~10% verbatim and summarizing the rest. ([LangChain blog: Context Engineering](https://www.langchain.com/blog/context-engineering-for-agents))
- **Anthropic multi-agent research.** The LeadResearcher **saves its plan to Memory** explicitly because once context crosses 200k it gets truncated, and the plan must survive. Subagents act as compression: each runs in its own context window and returns a *condensed* summary to the lead. ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system))
- **Manus / Claude Code (file refs).** The strongest pattern: tools return **handles** (`file_path`, `doc_id`, `search_result_id`). Big payloads live in the file system / a doc store. The agent reads back only the slice it needs. This is what lets Claude Code Bash route >30 KB outputs to disk transparently.

**Solar-gen implication:** every search/scrape tool should return a `{summary, source_id}` pair, with the full HTML/JSON stored locally and re-readable via a `fetch_artifact(source_id, range?)` tool.

## 6. Subagent budgets

When the orchestrator dispatches a sub-task, the sub-task gets its **own** per-call, per-turn, and token budgets — and crucially, its own context window.

- **Anthropic multi-agent research.** Explicit budget guidance baked into the lead agent's prompt: "spawn N subagents for X kind of task, each with M tool calls." Subagents return *compressed* findings, not raw transcripts. ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system))
- **OpenAI Agents SDK.** `Runner.run` tracks aggregate usage across **all handoffs**, but does not enforce per-handoff caps — you wrap the runner and check `usage.total_tokens` between turns. ([OpenAI Agents SDK usage](https://openai.github.io/openai-agents-python/usage/))
- **Cognition / Devin.** The "Don't Build Multi-Agents" post argues subagents *without shared full traces* miscommunicate; their later "Multi-Agents: What's Actually Working" softens this to: subagents are OK when reads can fan out but writes stay single-threaded. The budget implication is that a subagent should be **read-only and short-lived** — easier to bound. ([Cognition: Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents), [Cognition: Multi-Agents: What's Actually Working](https://cognition.ai/blog/multi-agents-working))
- **LangChain DeepAgents** community guidance: cap both *tool calls within a subagent* and the *number of subagents per parent turn*, otherwise recursion can multiply. ([LangChain forum: cap tool and sub-agent calls](https://forum.langchain.com/t/how-to-cap-tool-and-sub-agent-calls-in-deepagents/1653))

**Pattern:** parent allocates a token/tool-call sub-budget to each child; child returns a structured result with a `tokens_used` field; parent debits its own remaining budget.

## 7. Loop detection

The dominant agent-failure mode is **degenerate repetition**, not bad reasoning. AutoGPT made this famous; Reflexion calls it *degeneration-of-thought*.

- **Detection signals:**
  1. Same `(tool, args)` triple ≥ N times. Common N = **3–5** (Claude Code feature-request thread proposes 5).
  2. Same `(tool, args, result)` triple — even one repeat past compaction is a strong signal.
  3. A–B–A alternation (calls A, then B, then A again with the same args).
  4. No-op loops: tool returns empty/error N times in a row.
  ([StuckLoopDetection write-up](https://medium.com/@kacperwlodarczyk/stuckloopdetection-how-we-stopped-an-agent-burning-12-on-47-identical-calls-a12b5ea1f193), [Claude Code issue #4277](https://github.com/anthropics/claude-code/issues/4277))
- **Reactions** (in order of escalation):
  1. **Inject a system note** ("you just called X with these args; the result was identical; try a different approach"). Cheapest.
  2. **Force a planning step** (require a `think` / no-tool turn).
  3. **Escalate to subagent / human / abort task.**
- **Reflexion literature.** Termination heuristics: fixed iteration count (2–3), quality threshold from a critic, convergence detection (successive answers diverge by < ε), external verification. ([Reflexion paper](https://openreview.net/pdf?id=vAElhFcKW6), [LangChain Reflection Agents blog](https://blog.langchain.com/reflection-agents/))
- **Post-compaction guard.** A specific failure mode: after the API compacts away an earlier tool result, the model re-issues the same call because it has forgotten doing it. Mitigation: keep a *durable* tool-call ledger (small structured log) outside the compacted message stream. ([Claude API context editing replaces cleared results with placeholders for this reason.](https://platform.claude.com/docs/en/build-with-claude/context-editing))

## Recommended budget knobs for solar-gen

Defaults below assume long-running research jobs (hours), Claude Opus/Sonnet 4.7, ~40 tools, batch (non-interactive) execution. They're starting points for the eval harness, not absolutes.

| Knob | Default | Why |
|---|---|---|
| `tool.output.max_chars` (per tool, configurable) | **30,000 chars** | Matches Claude Code Bash default; empirically the ceiling at which output stays cheap to keep in context. Tools that hit it return a `truncated: true` flag and an artifact handle. |
| `tool.read.max_lines` | **2,000 lines** | Matches Claude Code Read; long lines truncated to 2,000 chars. |
| `tool.grep.head_limit` | **100 results** | Matches Claude Code Grep; signals truncation so the agent narrows the query. |
| `tool.fetch.store_to_artifact_threshold` | **8 KB** | Anything bigger than ~2k tokens goes to the artifact store; the tool returns `{summary, artifact_id}`. Forces lazy-load discipline early. |
| `task.max_tool_calls` (per top-level job) | **120** | Roughly the Anthropic "complex research" budget (10 subagents × ~12 calls). Aborts with a partial-result artifact. |
| `task.max_subagents` | **8** | Anthropic's lead-agent ceiling for "complex" queries. Beyond this, parallelism stops helping and KV-cache thrashes. |
| `subagent.max_tool_calls` | **15** | Anthropic's "comparison" subagent cap. Subagents return a compressed summary, not raw transcripts. |
| `subagent.max_output_tokens` | **8,000** | Forces compression; lead agent gets digestible chunks. |
| `task.max_input_tokens` (cumulative across turns) | **2,000,000** | Conservative ~10× single-context cap. Server-side compaction handles the rest. |
| `task.max_usd` | **$5.00** | Hard circuit breaker (OpenHands-style `max_budget_per_task`). Aborts the run; tune per-job-class once we have cost telemetry. |
| `task.max_wall_time_minutes` | **30** | Avoids hung external APIs holding a job open indefinitely. |
| `tool.rpc.retry.max` | **4** | Exponential backoff with jitter on 429/5xx only. Retries count against `task.max_tool_calls`. |
| `tool.rpc.rate_bucket` (per external provider) | **80% of provider RPS** | Token bucket shared across all parallel subagents; Brave=0.8 RPS, Exa=8 QPS, Tavily=per plan. |
| `context.compaction.threshold` | **70% of context window** | Trigger Claude API server-side compaction / `clear_tool_uses_20250919` early enough to avoid mid-turn truncation. |
| `context.compaction.clear_at_least` | **20,000 tokens** | Prevents thrashing the KV cache with tiny clears. |
| `context.plan_persistence` | **always-on** | Write the research plan to a Memory artifact every N turns (Anthropic LeadResearcher pattern) so it survives compaction. |
| `loop.detect.identical_calls` | **3 in a row** | After 3 identical `(tool, args)` calls, inject a system note. After 5, abort the subagent and notify the parent. |
| `loop.detect.window` | **last 12 tool calls** | Bounded rolling window; cheap to maintain. |
| `loop.detect.post_compaction_guard` | **on** | After every compaction, log a "you may have already done X" reminder seeded from the durable tool-call ledger. |

Every knob should be **per-job overridable** (a deep-research run might want `max_tool_calls=300` and `max_usd=$20`), but the defaults should be tight enough that an accidental infinite loop costs cents, not dollars.

## Key sources

- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Cognition — Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) and [Multi-Agents: What's Actually Working](https://cognition.ai/blog/multi-agents-working)
- [Manus — Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Claude API — Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) and [Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- [Claude Code issues #19901 (Bash limits)](https://github.com/anthropics/claude-code/issues/19901), [#6910 (Read limits)](https://github.com/anthropics/claude-code/issues/6910), [#4277 (loop detection)](https://github.com/anthropics/claude-code/issues/4277), [#12054 (unbounded output)](https://github.com/anthropics/claude-code/issues/12054)
- [OpenHands config.template.toml](https://github.com/OpenHands/OpenHands/blob/main/config.template.toml) and [metrics docs](https://deepwiki.com/OpenHands/OpenHands/8.4-agent-implementations)
- [LangGraph — GRAPH_RECURSION_LIMIT](https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT), [LangChain blog — Context Engineering for Agents](https://www.langchain.com/blog/context-engineering-for-agents)
- [Cursor tool-call limits writeup](https://apidog.com/blog/cursor-tool-call-limit/)
- [Aider — Repository map](https://aider.chat/docs/repomap.html)
- [Brave Search rate-limiting](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting), [Tavily rate limits](https://docs.tavily.com/documentation/rate-limits)
- [Reflexion paper](https://openreview.net/pdf?id=vAElhFcKW6), [LangChain Reflection Agents](https://blog.langchain.com/reflection-agents/)
- [awesome-agent-failures: AutoGPT planning failures](https://github.com/vectara/awesome-agent-failures/blob/main/docs/case-studies/autogpt-planning-failures.md)
- [StuckLoopDetection — repeated-call patterns](https://medium.com/@kacperwlodarczyk/stuckloopdetection-how-we-stopped-an-agent-burning-12-on-47-identical-calls-a12b5ea1f193)
- [OpenAI Agents SDK — Usage](https://openai.github.io/openai-agents-python/usage/)
