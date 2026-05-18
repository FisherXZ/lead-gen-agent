# Agent Memory Redesign — Phase 0: Design Lock-In

**Date:** 2026-05-18
**Status:** Phase 0 design lock. Awaiting Fisher review. Implementation plan refinements deferred to subsequent rounds.
**Branch:** `claude/agent-memory-design-mUZ3T`
**References:**
- `research/2026-05-17-gbrain-memory-architecture-findings.md`
- `research/2026-05-17-agentic-rag-memory-findings.md`
- Hermes deep-dive — *not yet written; pattern is referenced as an assumption (see Open Item H1)*

---

## Plain English

Solar-gen's agent already has a memory system — a `agent_memory` table, `remember` and `recall` tools, a compactor, a scratchpad. It works but it's thin: keyword search only, two scopes (project / global), an "importance" integer instead of real confidence, no time semantics, no embedding. This document locks the design for a deeper memory subsystem that will replace the thin one over the coming weeks.

The big shape: **five layers** of memory (working, episodic, two flavors of semantic, procedural), **five scopes** of sharing (from global to per-conversation), **bi-temporal time tracking** so we can answer "what did we believe in March," and **hybrid history** — we keep full audit trails on structured facts (EPC relationships, deal terms) but overwrite the lighter stuff (chat summaries, preferences). All of this is built on Supabase Postgres + pgvector for durable storage and **hosted Redis (Upstash)** for the hot path: working memory, job queue, locks, caches, pub/sub.

We're explicitly **not** adopting LangGraph or LangMem as libraries. Instead we keep solar-gen's direct Anthropic-SDK loop and build the memory plumbing as code we own. Same pattern as Anthropic's internal gbrain system that the prior research surveyed. Five things are open for next round: how memory gets *into* the prompt (read path), how it gets *extracted* (write path), when summaries promote up the layer stack (compaction), how users see/edit/forget memories (governance UX), and how we measure whether memory actually helps (eval framework). Plus one open question — confirming what "Hermes" refers to in the design lineage.

---

## What this document is (and isn't)

**It is**: a Phase 0 design lock that captures the architectural decisions made across two prior research rounds (gbrain, agentic-RAG) and a third design conversation (this round). It enumerates the locked decisions, marks the open items, and sketches phased implementation against the existing codebase.

**It isn't**: a full implementation spec. Read path design, write path design, compaction strategy, governance UX, and the evaluation framework are deferred to subsequent design rounds. Code changes are *not* started until Fisher approves both the design and a per-phase implementation plan.

---

## Baseline: what exists in solar-gen today

The redesign is a migration on top of working code, not a greenfield build. The relevant baseline:

### Data layer (Supabase Postgres)

| Object | Location | Shape |
|---|---|---|
| `agent_memory` table | `supabase/migrations/011_create_agent_memory.sql` | `id`, `memory TEXT`, `scope ('project'\|'global')`, `memory_key`, `importance INT 1-10`, `conversation_id`, `project_id`, `created_at`, `updated_at`, `memory_tsv` (GIN). Upsert-by-(`memory_key`, `scope`). No embeddings, no bi-temporal columns, no confidence float, no supersession. |
| `research_scratch` table | migrations `013`, `024_research_scratch_ttl.sql` | Working-memory equivalent. TTL'd. |
| `tool_cache` table | migration `017_create_tool_cache.sql` | Tool-result caching. |
| `epc_engagements` table | (existed before, modified by `016`) | Structured relationships (developer → EPC → project). Currently no bi-temporal columns despite gbrain research recommending them. |
| `entities` table | (existed before) | Canonical entity normalization for `epc_engagements`. |

**Scope today: two tiers (`project`, `global`).** Workspaces were introduced in migration `014` and **dropped** in `016_drop_workspaces_simplify_auth.sql`. Solar-gen is currently per-user with a static allowlist (`fisher262425@gmail.com`, `liav@civrobotics.com`).

### Code layer (Python, direct Anthropic SDK)

| Component | Path | What it does |
|---|---|---|
| `AgentRuntime` | `agent/src/runtime/agent_runtime.py` | The Claude tool-use loop. Direct `anthropic` SDK. |
| `HeuristicCompactor` | `agent/src/runtime/compactor.py` | Zero-LLM string-extraction compactor. Preserves last N messages, summarizes older ones heuristically. |
| `EscalationPolicy` | `agent/src/runtime/escalation.py` | Max-iteration + stagnation control. |
| Hooks framework | `agent/src/runtime/hooks.py` + `agent/src/hooks/` | `pre_tool` / `post_tool` interception. |
| `InjectContextHook` | `agent/src/hooks/inject_context.py` | Auto-injects `conversation_id` / `session_id` into memory tools. |
| `recall` tool | `agent/src/tools/recall.py` | Keyword + scope search via `db.search_memories()`. No vector retrieval. |
| `remember` tool | `agent/src/tools/remember.py` | Writes to `agent_memory`. Field set: memory, scope, memory_key, importance, project_id. |
| `research_scratchpad` tool | `agent/src/tools/research_scratchpad.py` | Session-scoped working memory. |
| `manage_todo` / `think` tools | `agent/src/tools/manage_todo.py`, `think.py` | Self-management surface. |
| `confidence.py` | `agent/src/confidence.py` | **EPC-discovery-specific** confidence aggregator (4-level enum: `confirmed/likely/possible/unknown`). Operates over `EpcSource` reliability. Not generic memory confidence. |

### Agent stack

| Layer | Choice | Status |
|---|---|---|
| LLM access | `anthropic` SDK directly (`AsyncAnthropic`) | Locked — staying here, not migrating to LangGraph/LangMem. |
| Framework | Handwritten loop in `AgentRuntime` | Locked — keep. |
| DB | Supabase (Postgres) | Existing. Will add `pgvector` extension. |
| Cache / queue / locks | None today | **Adding**: hosted Redis (Upstash leaning). |

---

## Architecture decisions

### Locked this round (extends or supersedes prior research)

| # | Decision | Source |
|---|---|---|
| D1 | **Five cognitive layers**: working, episodic, semantic_structured, semantic_freetext, procedural. Splits the prior research's "semantic" into structured (knowledge-graph) and free-text (preferences/insights). | This round; extends agentic-RAG four-layer model |
| D2 | **Five scope tiers**: `global` / `tenant` / `workspace` / `user` / `thread`. All four scope columns nullable on every row; `scope` enum declares intended sharing level. Solar-gen today populates only `user`-equivalent + `workspace`-equivalent (via `project_id`); other tiers reserved for product evolution. | This round |
| D3 | **Hybrid history model**: append-only with `superseded_by` for **structured semantic only** (EPC engagements, deal terms, entity-attribute facts). In-place mutation for working / episodic / free-text-semantic / procedural. Overrides the prior gbrain-derived "soft-expire everywhere" call. | This round; supersedes gbrain finding §1 application to `agent_memory` |
| D4 | **Bi-temporal columns** (`valid_from`, `valid_until`) populated only on structured semantic rows. Other layers leave them null. Schema has the columns on every row (cheap) for uniformity. | This round; refines gbrain finding §1 |
| D5 | **Confidence as float 0–1** stored on every row. UI buckets at display time. Replaces (for memory rows) the four-level enum used in `confidence.py`. `confidence.py`'s EPC-source aggregation stays — it produces the float that gets written to memory. | This round |
| D6 | **Storage triad**: Postgres + pgvector (durable, all five layers' canonical store) / Redis (working memory hot path + job queue + distributed locks + caches + pub/sub) / object store (raw artifacts, scraped HTML, large tool outputs referenced by handle). | This round |
| D7 | **Redis hosted**: managed service (Upstash leaning for serverless-friendly HTTP API; ElastiCache deferred as later option if we hit throughput limits). | This round |
| D8 | **Library stack**: direct Anthropic SDK, no LangGraph, no LangMem, no Mem0/Letta dependency. Memory subsystem built as code we own in `agent/src/memory/` (new module). Track A and Track B extractors are direct Haiku/Sonnet calls. Matches gbrain's own pattern. | This round |
| D9 | **Phased rollout** of scope tiers: v1 single-tenant (today) → v2 deals/pipeline/portfolios → v3 multi-tenant SaaS → v4 curated cross-tenant pool. Schema fixed from v1; columns populated over time. | This round |

### Retained from prior research

| # | Decision | Source |
|---|---|---|
| R1 | Two write tracks: Track A (deterministic regex post-tool extractor, sync) and Track B (small-model judge on conversation turns, async). | gbrain findings §2 |
| R2 | `ADD` / `UPDATE` / `DELETE` / `NOOP` classification on every candidate write. | gbrain findings §3 |
| R3 | Routing principle: deterministic ops → code; judgment ops → model. Scoped to the memory subsystem for now. | gbrain findings §5 |
| R4 | Subagent synthesis pattern: cheap Haiku verdict gates expensive Sonnet synthesis (for consolidation / classification on large clusters). | gbrain findings §6 |
| R5 | Hybrid retrieval: BM25 (lexical) + dense vector (semantic) + cross-encoder rerank on merged candidates. Filter by validity window. | agentic-RAG findings §3 |
| R6 | Compaction *promotes* durable insights into long-term memory before producing the working-context summary — does not just shrink context. | agentic-RAG findings §5 |
| R7 | Memory is a first-class tool surface (`recall`, `remember`, `forget`) — the agent acts on memory, not just receives injected context. | agentic-RAG findings §1 + existing `recall.py` / `remember.py` |

### Deferred from prior research

| # | Item | Why deferred |
|---|---|---|
| F1 | Full async job queue (gbrain's `minion_jobs` pattern) | Redis Streams gives us 80% of this for v1. Full Postgres-backed job queue with `FOR UPDATE SKIP LOCKED` is its own project. Track B runs sync via Haiku for v1; promote to async via Redis Streams in v2. |
| F2 | Nightly consolidation (facts → "takes") | Depends on F1 + meaningful fact volume. Revisit once we have 6+ months of accumulated memory. |
| F3 | Generalizing routing principle beyond memory | Stays scoped to memory subsystem for now. |
| F4 | Cross-tenant global knowledge pool | Product call, not v1. Schema supports it via `scope='global'`; population strategy waits for multi-tenant maturity. |

---

## The five cognitive layers

| Layer | What it stores | Write trigger | Read profile | Decay | Current solar-gen location |
|---|---|---|---|---|---|
| **Working** | Live conversation, current todos, scratchpad, in-flight entity IDs | Implicit (message append) + explicit (`research_scratchpad`, `manage_todo`) | Always fully in-context up to budget | Volatile — TTL minutes, cleared on session end | `research_scratch` table + in-memory message list. Redis-backed working memory replaces `research_scratch` for hot path. |
| **Episodic** | Summarized conversation segments, research session outcomes, notable tool calls | Post-turn extractor (Track B) on conversation boundaries | Top-K vector search filtered by user + recency | Compaction-driven; older episodes get re-summarized | New — adds to `agent_memory` with `layer='episodic'`. |
| **Semantic-structured** | Typed entity-attribute facts: `(entity, predicate, value)` — EPC relationships, contract terms, credit ratings, headquarters | Track A regex on `report_findings` / `related_leads` tool outputs; promotions from episodic via Track B | Filter by entity + predicate + validity window; vector fallback for free-form lookup | None — append-only with `valid_from`/`valid_until` | Lives in **`epc_engagements`** + new `entity_facts` table. Bi-temporal columns added. |
| **Semantic-freetext** | Insights, preferences, "Acme delivers fast on residential but slow on utility" — assertions that don't fit a typed predicate | Track B judge | Vector + BM25 hybrid retrieval filtered by user/workspace scope | In-place mutation on update | New — adds to `agent_memory` with `layer='semantic_freetext'`. Migrates current free-form `agent_memory` rows. |
| **Procedural** | "How to" knowledge: research playbooks, contact-discovery sequences, templates the agent has learned | Track B judge with manual promotion gate; future: usage-driven promotion | Filter by task type + retrieval-by-similarity | Low decay; usage-counter for relevance | New — adds to `agent_memory` with `layer='procedural'`. Some overlap with existing `prompts.py` system prompts. |

**Why split structured vs free-text semantic.** EPC relationships and contract terms have stable predicates (`headquartered_in`, `default_rate`, `contract_value`) where you'd want SQL-style queries and audit trails. Free-form insights ("the user prefers concise responses") don't — they're vector-retrieved one-off strings. Single-table mixing forces either too much structure on free-text or too little on entity facts. The split is cheap (same row schema with a `layer` enum + nullable `entity_id`/`predicate`/`value` fields).

---

## The five scope tiers

Every memory row carries four nullable scope columns plus a `scope` enum declaring intended sharing:

| Scope | tenant_id | workspace_id | user_id | thread_id | Example |
|---|---|---|---|---|---|
| `global` | null | null | null | null | "EPCs typically structure POs as X." Objective facts. |
| `tenant` | set | null | null | null | "Civ Robotics's installs are 6 weeks faster than industry avg." |
| `workspace` | set | set | null | null | "Project #4291: customer wants Tier 1 panels only." Maps to current `project_id`. |
| `user` | set | (any) | set | null | "Fisher prefers concise responses." |
| `thread` | set | (any) | set | set | Working memory only. Conversation-scoped. |

**Phased population:**

| Phase | Trigger | tenant_id | workspace_id | user_id | thread_id |
|---|---|---|---|---|---|
| **v1 (now)** | Single tenant, no multi-project mode | `'default'` | = current `project_id` (rename for clarity) | = auth.uid() | per-conversation |
| **v2** | Deals / pipeline / portfolios land as distinct entities | `'default'` | per-deal / per-pipeline / per-portfolio | set | set |
| **v3** | Multi-tenant SaaS | per-customer | per-deal within customer | set | set |
| **v4** | Curated cross-tenant pool lights up | `global` populated by curation rules | n/a | n/a | n/a |

**Note on workspace history.** Migration `016` dropped the `workspaces` table after the team tried per-workspace scoping and reverted. The new design uses `workspace_id` *conceptually* — but maps it to `project_id` in the current schema (rename is optional, function is the same). Re-introducing a `workspaces` table is **not** part of v1.

---

## Schema target

### `agent_memory` (extended from migration `011`)

```sql
-- Additive migration — preserves existing rows, defaults all new columns
ALTER TABLE agent_memory
    ADD COLUMN layer TEXT NOT NULL DEFAULT 'semantic_freetext'
        CHECK (layer IN ('working', 'episodic', 'semantic_structured',
                         'semantic_freetext', 'procedural')),
    ADD COLUMN scope_tier TEXT NOT NULL DEFAULT 'workspace'
        CHECK (scope_tier IN ('global', 'tenant', 'workspace', 'user', 'thread')),
    ADD COLUMN tenant_id TEXT,
    ADD COLUMN workspace_id UUID,  -- aliases project_id during transition
    ADD COLUMN user_id UUID REFERENCES auth.users(id),
    ADD COLUMN thread_id UUID,  -- aliases conversation_id during transition

    -- Provenance
    ADD COLUMN source_type TEXT
        CHECK (source_type IN ('user_utterance', 'agent_inference',
                               'tool_output', 'document_extract',
                               'promoted_from_lower_layer')),
    ADD COLUMN source_ref JSONB,
    ADD COLUMN created_by_user_id UUID REFERENCES auth.users(id),

    -- Confidence (float supersedes integer importance for new rows;
    -- importance retained for backfill compatibility)
    ADD COLUMN confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    ADD COLUMN confidence_source TEXT
        CHECK (confidence_source IN ('extractor_llm', 'retrieval_match',
                                     'user_confirmed', 'manually_verified')),
    ADD COLUMN verification_status TEXT DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'acknowledged', 'verified')),

    -- Bi-temporal (populated only when layer = 'semantic_structured')
    ADD COLUMN valid_from TIMESTAMPTZ,
    ADD COLUMN valid_until TIMESTAMPTZ,
    ADD COLUMN superseded_by UUID REFERENCES agent_memory(id),
    ADD COLUMN superseded_at TIMESTAMPTZ,

    -- TTL for working memory + time-bounded facts
    ADD COLUMN ttl_expires_at TIMESTAMPTZ,

    -- Structured-semantic extras (nullable, populated only when applicable)
    ADD COLUMN entity_id UUID REFERENCES entities(id),
    ADD COLUMN predicate TEXT,
    ADD COLUMN value JSONB,

    -- Embedding (pgvector)
    ADD COLUMN embedding vector(1536);  -- text-embedding-3-small default

-- Indexes
CREATE INDEX idx_agent_memory_layer ON agent_memory (layer);
CREATE INDEX idx_agent_memory_scope_tier ON agent_memory (scope_tier);
CREATE INDEX idx_agent_memory_user ON agent_memory (user_id)
    WHERE user_id IS NOT NULL;
CREATE INDEX idx_agent_memory_thread ON agent_memory (thread_id)
    WHERE thread_id IS NOT NULL;
CREATE INDEX idx_agent_memory_entity ON agent_memory (entity_id, predicate)
    WHERE entity_id IS NOT NULL;
CREATE INDEX idx_agent_memory_valid ON agent_memory (valid_from, valid_until)
    WHERE layer = 'semantic_structured';
CREATE INDEX idx_agent_memory_ttl ON agent_memory (ttl_expires_at)
    WHERE ttl_expires_at IS NOT NULL;
CREATE INDEX idx_agent_memory_embedding ON agent_memory
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_agent_memory_superseded ON agent_memory (superseded_by)
    WHERE superseded_by IS NOT NULL;

-- Existing memory_tsv FTS index is preserved.
```

### `epc_engagements` (bi-temporal extension)

```sql
-- Add gbrain-style bi-temporal columns. Append-only on update from this point.
ALTER TABLE epc_engagements
    ADD COLUMN valid_from TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN valid_until TIMESTAMPTZ,
    ADD COLUMN superseded_by UUID REFERENCES epc_engagements(id),
    ADD COLUMN expired_at TIMESTAMPTZ,
    ADD COLUMN confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    ADD COLUMN source_type TEXT,
    ADD COLUMN source_ref JSONB;

CREATE INDEX idx_epc_engagements_valid ON epc_engagements (valid_from, valid_until);
CREATE INDEX idx_epc_engagements_superseded ON epc_engagements (superseded_by)
    WHERE superseded_by IS NOT NULL;
```

### New: `entity_facts` (optional, may be deferred to v2)

A normalized typed knowledge graph alongside `epc_engagements`. Same shape as the structured-semantic rows in `agent_memory` but with a stricter foreign-key contract. **Deferred** to v2 — for v1, structured semantic lives in `agent_memory` rows with `layer='semantic_structured'`. Promote to dedicated `entity_facts` when query patterns justify it.

### `research_scratch` → Redis

Working memory migrates from the `research_scratch` Postgres table to Redis. Postgres remains the durable fallback / cold-storage tier. Migration `024_research_scratch_ttl.sql`'s TTL semantics map directly to Redis `EXPIRE`.

---

## Provenance and confidence metadata

Every memory row carries the same metadata envelope:

| Field | Always populated? | Notes |
|---|---|---|
| `id` | yes | UUID |
| `layer` | yes | Enum |
| `scope_tier` | yes | Enum |
| `tenant_id`, `workspace_id`, `user_id`, `thread_id` | per `scope_tier` | Nullable scope chain |
| `content` (existing `memory` column) | yes | Text or JSON-stringified |
| `embedding` | yes for semantic / episodic / procedural; null for working | pgvector |
| `created_at` (existing `recorded_at` semantically) | yes | Transaction time |
| `source_type` | yes | Enum |
| `source_ref` | yes | JSONB: thread+turn for utterance; tool_call_id for tool output; doc+span for document extract; parent_memory_id for promotion |
| `created_by_user_id` | yes | Audit trail + "forget me" hook |
| `confidence` | yes (default 1.0 for `user_confirmed` / `manually_verified`) | Float 0-1 |
| `confidence_source` | yes | Enum |
| `verification_status` | yes (default `unverified`) | Enum |
| `valid_from`, `valid_until` | only `layer='semantic_structured'` | Bi-temporal |
| `superseded_by`, `superseded_at` | populated on update of structured semantic | Append-only history |
| `ttl_expires_at` | only working memory + time-bounded facts | TTL |
| `entity_id`, `predicate`, `value` | only `layer='semantic_structured'` | Knowledge-graph fields |

**Confidence integration with existing `confidence.py`.** The EPC-source aggregator (`compute_confidence_upgrade`) continues to operate on `EpcSource` lists and produces a 4-level enum (`confirmed/likely/possible/unknown`). When a finding writes to memory, we map the enum to a float:

| Enum | Float |
|---|---|
| `confirmed` | 1.0 |
| `likely` | 0.75 |
| `possible` | 0.5 |
| `unknown` | 0.25 |

The float is stored on the memory row; `confidence.py` is unchanged. UI display logic re-buckets the float using its own thresholds.

---

## Storage triad

| Tier | Tech | What lives here |
|---|---|---|
| **Durable** | Supabase Postgres + `pgvector` | All five memory layers' canonical rows. Embeddings. RLS for tenant isolation (forward-looking). |
| **Hot path** | Hosted Redis (Upstash) | Working memory (replaces `research_scratch` for active sessions). Job queue (Track B candidates awaiting Haiku judge). Distributed locks (ADD/UPDATE/DELETE serialization per entity). Tool-result cache (supersedes `tool_cache` Postgres table for short-TTL hits; long-TTL cache stays in Postgres). Pub/sub for memory-event fanout to subscribers. Redis Streams for guaranteed-delivery memory events (e.g., "promoted episodic → semantic"). |
| **Cold artifacts** | Object store (Supabase Storage) | Raw scraped HTML, large tool outputs, full document content. Memory rows reference by handle (`source_ref.object_key`). |

**Operational notes on the Redis commitment:**

1. **Working-memory durability**. Working memory in Redis means an Upstash blip = ephemeral state loss. Acceptable contract: working memory is volatile by definition; on Redis unavailability, user re-asks. Postgres `research_scratch` remains as a fallback write path for >5-minute-old scratch entries (TTL'd promotion). Decision deferred to v1 implementation round.
2. **Cache invalidation**. Embedding cache keyed by content hash is immutable. LLM-response cache keyed by `(prompt_version, model, content_hash)` invalidates on prompt-version bump.
3. **Lock hygiene**. Distributed locks need timeout + fencing tokens. Use a Redlock-pattern client; don't hand-roll.
4. **Pub/sub vs Streams**. Pub/sub is fire-and-forget; use for non-critical UI notifications. Use Redis Streams for memory-promotion events that consumers need to process exactly once.

---

## Open items (next round)

The following are **not** locked. Phase 0.5 / Phase 1 design rounds address them in order:

| # | Item | Why blocking |
|---|---|---|
| **O1** | **Read path design** | How does memory get *into* the prompt at inference time? Static prefix vs dynamic top-K vs hybrid. Query rewriting. Re-ranking model (Cohere rerank-3? Cross-encoder?). System-message stitching format. KV-cache implications for the existing handwritten loop (see existing `plans/2026-03-12-agent-upgrades-5-phases.md` Phase 1 cache discipline). |
| **O2** | **Write path design** | Track A regex extractor — which tool outputs trigger? Which entity-predicate pairs are first-party? Track B Haiku judge — prompt design, NOOP gate cost, false-positive rate target. Dedup / merge strategy on write. |
| **O3** | **Compaction / promotion strategy** | When working → episodic. When episodic → semantic. Triggering thresholds. Relationship to existing `HeuristicCompactor`. |
| **O4** | **Governance UX** | Memory inspector. Forget / delete flows (incl. GDPR-style "delete all memories about me"). Permission UI for shared scopes. Export. |
| **O5** | **Evaluation framework** | LongMemEval-style benchmark + solar-gen-specific eval set (EPC-research memory recall). Regression detection. Online metrics. |
| **O6** | **Privacy / security specifics** | PII detection on Track B writes. Encryption at rest beyond Supabase defaults. RLS policy specifics for the new scope columns (current RLS is `auth.uid() IS NOT NULL` — too permissive for the new scope model). |
| **O7** | **Migration plan for existing `agent_memory` rows** | Today's rows have `importance INT` but no `confidence`, no `layer`, no `source_type`. Backfill strategy: map all existing rows to `layer='semantic_freetext'`, `scope_tier='workspace'` (if `project_id` non-null) or `'global'`, `confidence = importance / 10.0`. One-shot script. |
| **H1** | **Hermes reference confirmation** | The prior research roadmap (`research/2026-05-17-gbrain-...md` and `agentic-rag-...md`) lists "Hermes deep-dive" as the next research doc, treating Hermes as an architectural pattern (bounded markdown + pre-turn prefetch + post-turn judge). In the design conversation feeding this doc, Fisher answered "Hermes = Nous Hermes models." This doc assumes the **architectural-pattern** reading, because (a) that's what the prior research roadmap calls for and (b) the pattern itself (bounded markdown context with `<memory-context>` fences) is a useful read-path component regardless of provenance. Confirm or override on review. |

---

## Implementation phasing (sketch — refine after open items)

| Phase | Scope | Depends on |
|---|---|---|
| **P0** | This document. Design lock. | — |
| **P0.5** | Design rounds O1–O7. Output: detailed sub-specs per item. | P0 approval |
| **P1** | Schema migration. Additive ALTER on `agent_memory` + `epc_engagements`. Backfill script for existing rows. pgvector extension enabled. No code path changes yet. | P0.5 |
| **P2** | Read path. Hybrid retrieval (`pgvector` + BM25 over `memory_tsv` + rerank). New `recall` tool implementation behind a flag; old keyword-only path preserved as fallback. Read-side scope filtering. | P1, O1 |
| **P3** | Write path Track A. Deterministic regex extractor as a `post_tool` hook on `report_findings` and `related_leads`. Writes structured-semantic rows with bi-temporal columns. | P1, O2 |
| **P4** | Write path Track B (sync mode). Haiku judge runs synchronously at conversation-turn boundaries; emits ADD/UPDATE/DELETE/NOOP. Writes episodic + free-text-semantic rows. | P2, P3, O2 |
| **P5** | Redis hot path. Working memory migrated from `research_scratch` to Upstash. Job queue stub (Redis Streams) for future async Track B. Lock manager for write serialization. | P4 |
| **P6** | Track B async. Promote sync Haiku judge to async via Redis Streams. Frees the user turn from extraction latency. | P5 |
| **P7** | Compaction / promotion. LLM-aware compactor extends `HeuristicCompactor`. Promotion rules working → episodic → semantic. | P6, O3 |
| **P8** | Governance UX. Memory inspector page in frontend. Forget/edit flows. | P7, O4 |
| **P9** | Eval framework. | P8, O5 |

Each phase has its own implementation plan (`plans/2026-XX-XX-agent-memory-phaseN.md`) before code starts. Per CLAUDE.md, code changes wait for Fisher's explicit go-ahead on each phase.

---

## Not in scope

- **Re-introducing `workspaces` table**. Migration `016` dropped it; design uses `workspace_id` conceptually mapped to `project_id` for v1. A real `workspaces` table returns only if/when v3 multi-tenant lands.
- **Custom Postgres-backed job queue (gbrain's `minion_jobs`)**. Redis Streams covers v1–v2 needs. Revisit if throughput / durability constraints demand it.
- **Nightly consolidation**. Deferred to v2+ (requires job queue + meaningful fact volume).
- **Cross-tenant `global` knowledge pool**. Schema-supported, population strategy deferred — product call.
- **LangGraph / LangMem / Mem0 / Letta integration**. Explicitly rejected this round in favor of code-we-own.

---

## Review checklist for Fisher

Before approving Phase 0 and moving to P0.5:

- [ ] Confirm or override the **Hermes reference** (H1).
- [ ] Confirm the **history model split** (D3) — hybrid stands, prior gbrain-derived "soft-expire everywhere" is superseded for `agent_memory`.
- [ ] Confirm the **library stack call** (D8) — direct SDK, no LangGraph/LangMem.
- [ ] Confirm the **scope tiers** and the v1→v4 phasing (D2, D9).
- [ ] Confirm the **schema target**: additive ALTERs on `agent_memory` + `epc_engagements`, deferring `entity_facts` to v2.
- [ ] Approve sequence of design rounds for O1–O7.
- [ ] Flag anything that contradicts your read of the prior research that I should reconcile in writing.
