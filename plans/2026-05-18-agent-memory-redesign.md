# Agent Memory Redesign — Phase 0 + 0.5 Design Lock

**Date:** 2026-05-18
**Status:** Phase 0 + Phase 0.5 design locked. Awaiting Fisher review of the consolidated document. Phase 1 (schema migration code) and beyond gated on this review.
**Branch:** `claude/agent-memory-design-mUZ3T`
**References:**
- `research/2026-05-17-gbrain-memory-architecture-findings.md`
- `research/2026-05-17-agentic-rag-memory-findings.md`
- NousResearch/hermes-agent (https://github.com/NousResearch/hermes-agent) — the architectural reference for file-based memory, agent-curated writes with periodic nudges, FTS5+summarization, skills-as-procedural-memory, Honcho user modeling. Replaces the placeholder "Hermes deep-dive" doc from the prior research roadmap.

---

## Plain English

Solar-gen's agent already has a memory system — a `agent_memory` table, `remember` and `recall` tools, a compactor, a scratchpad. It works but it's thin: keyword search only, two scopes, "importance" integer instead of confidence, no time semantics, no embeddings. This document locks the design for a deeper memory subsystem that will replace the thin one over the coming weeks.

The shape: **five layers** of memory (working, episodic, two flavors of semantic, procedural), **five scopes** of sharing (global → tenant → workspace → user → thread), **bi-temporal time tracking** on structured-semantic rows only, **hybrid history** (append-only for structured facts, in-place for everything else), and **float 0–1 confidence** on every row. The hot path runs on **hosted Redis (Upstash)**; durable storage is **Supabase Postgres + pgvector**; raw artifacts go to **Supabase Storage**.

We're not adopting LangGraph or LangMem as libraries — same call gbrain made. The agent stays on the direct Anthropic SDK, and the memory subsystem is code we own. Three things flow into the prompt at inference time: a small always-on "memory context" block in the system message, dynamic retrieval results from a hybrid vector+BM25+rerank pipeline, and whatever the agent fetches mid-turn via the `recall` tool. Three things write to memory: the agent's `remember` tool, a deterministic regex/structured-output extractor on key tool calls, and a Haiku judge that runs on tool-call turns. All three writes converge on one common pipeline that handles dedup and classification.

The Hermes (Nous Research) framework provides the operational patterns we're adopting: file-shaped persistent memory, agent-curated writes with periodic consolidation nudges, skills as autonomous procedural-memory artifacts, and FTS-plus-summarization for cross-session episodic search.

Roughly **28 design decisions** are locked across this document, covering Phase 0 (architecture, schema, scoping, storage) and Phase 0.5 (read path, write path, compaction, migration plan, privacy). Three things remain explicitly open: a research round on revamping the current heuristic compactor (O3.1), governance UX (memory inspector, edit/forget flows — O4), and the evaluation framework (O5). All three are best tackled once code is in motion.

---

## What this document is (and isn't)

**It is**: a Phase 0 + Phase 0.5 design lock. Phase 0 captures the architectural decisions made across two prior research rounds (gbrain, agentic-RAG) and a design conversation. Phase 0.5 captures the sub-spec decisions for read path, write path, compaction, migration, and privacy/security. Together they're enough to start writing implementation code.

**It isn't**: a line-by-line implementation spec. Specific embedding model choice, cross-encoder model choice, exact regex/JSON-schema content for Track A extractors, and the heuristic-compactor revamp are all explicitly deferred to per-phase implementation plans. Code changes wait for Fisher's go-ahead on each phase.

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
| `HeuristicCompactor` | `agent/src/runtime/compactor.py` | Zero-LLM string-extraction compactor. Preserves last N messages, summarizes older ones heuristically. **Immature — flagged for revamp (open item O3.1).** |
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

### Phase 0 — locked architecture

| # | Decision | Source |
|---|---|---|
| D1 | **Five cognitive layers**: working, episodic, semantic_structured, semantic_freetext, procedural. Splits the prior research's "semantic" into structured (knowledge-graph) and free-text (preferences/insights). | This round; extends agentic-RAG four-layer model |
| D2 | **Five scope tiers**: `global` / `tenant` / `workspace` / `user` / `thread`. All four scope columns nullable on every row; `scope` enum declares intended sharing level. | This round |
| D3 | **Hybrid history model**: append-only with `superseded_by` for **structured semantic only**. In-place mutation for working / episodic / free-text-semantic / procedural. Overrides the prior gbrain-derived "soft-expire everywhere" call. | This round; supersedes gbrain finding §1 application to `agent_memory` |
| D4 | **Bi-temporal columns** (`valid_from`, `valid_until`) populated only on structured semantic rows. Other layers leave them null. | This round; refines gbrain finding §1 |
| D5 | **Confidence as float 0–1** stored on every row. UI buckets at display time. The EPC-source aggregator in `confidence.py` produces the float that gets written to memory. | This round |
| D6 | **Storage triad**: Postgres + pgvector (durable) / Redis (working memory hot path + job queue + locks + caches + pubsub) / Supabase Storage (raw artifacts). | This round |
| D7 | **Redis hosted**: managed service (Upstash leaning). | This round |
| D8 | **Library stack**: direct Anthropic SDK, no LangGraph, no LangMem, no Mem0/Letta dependency. Memory subsystem built in new `agent/src/memory/` module. | This round |
| D9 | **Phased rollout** of scope tiers: v1 single-tenant → v2 deals/pipeline/portfolios → v3 multi-tenant SaaS → v4 curated cross-tenant pool. Schema fixed from v1; columns populated over time. | This round |

### Phase 0 — retained from prior research

| # | Decision | Source |
|---|---|---|
| R1 | Two write tracks: Track A (deterministic post-tool extractor) + Track B (small-model judge on conversation turns). | gbrain findings §2 |
| R2 | `ADD` / `UPDATE` / `DELETE` / `NOOP` classification on every candidate write. | gbrain findings §3 |
| R3 | Routing principle: deterministic ops → code; judgment ops → model. Scoped to memory subsystem. | gbrain findings §5 |
| R4 | Subagent synthesis pattern: cheap Haiku verdict gates expensive Sonnet synthesis. | gbrain findings §6 |
| R5 | Hybrid retrieval: BM25 + dense vector + cross-encoder rerank. | agentic-RAG findings §3 |
| R6 | Compaction *promotes* durable insights into long-term memory before producing the working-context summary. | agentic-RAG findings §5 |
| R7 | Memory is a first-class tool surface (`recall`, `remember`, `forget`). | agentic-RAG findings §1 + existing tools |

### Phase 0 — deferred from prior research

| # | Item | Why deferred |
|---|---|---|
| F1 | Full async job queue (gbrain's `minion_jobs` pattern) | Redis Streams covers v1–v2 needs. Full Postgres-backed queue is its own project. |
| F2 | Nightly consolidation (facts → "takes") | Depends on F1 + meaningful fact volume. |
| F3 | Generalizing routing principle beyond memory | Stays scoped to memory subsystem for now. |
| F4 | Cross-tenant global knowledge pool | Product call, not v1. |

### Phase 0.5 — locked sub-specs

| # | Decision | Detail section |
|---|---|---|
| RP1 | **Hybrid injection** — always-on prefix + dynamic recall via `recall` tool | §Read path |
| RP2 | **System-message fences** for stitching: `<memory-context>...</memory-context>` block in system prompt | §Read path |
| RP3 | **1.5K + 3K token budget** (prefix + dynamic) | §Read path |
| RP4 | **Vector + BM25 + cross-encoder rerank** retrieval | §Read path |
| RP5 | **Prefix composition**: persona + top-5 user prefs + active todos + workspace summary (all four) | §Read path |
| RP6 | **Heuristic-gated auto-retrieval**: regex entity-mention pre-gate decides whether to auto-retrieve | §Read path |
| RP7 | **Multi-query expansion** via Haiku (literal + expanded + HyDE-style) for retrieval queries | §Read path |
| RP8 | **Full scope chain participation** in retrieval with scope-weighted rerank | §Read path |
| WP1 | **One pipeline, three triggers**: `remember` tool + Track A + Track B all funnel through `memory_write()` | §Write path |
| WP2 | **Track A triggers**: `report_findings` (primary) + known-URL `fetch_page` + `save_contact`/`push_to_hubspot` + `approve_discovery` | §Write path |
| WP3 | **Track A pattern source**: structured outputs / JSON schemas (no regex; LLM produces typed JSON) | §Write path |
| WP4 | **Track B cadence**: only on tool-call turns; pure-chat turns covered by Hermes-style periodic nudges at thread-end | §Write path |
| WP5 | **Track B strictness**: high NOOP bar — extract only clearly durable + non-trivial facts | §Write path |
| WP6 | **Track B first-party predicates**: dev→EPC→project triples + entity attributes + contract/engagement terms + contact relationships | §Write path |
| WP7 | **Dedup**: embedding similarity (cosine ≥ 0.92 → UPDATE; 0.85–0.92 → ADD/UPDATE classifier; < 0.85 → ADD) | §Write path |
| WP8 | **`remember` migration**: `importance` → `confidence` (i/10.0); `memory_key` retained as dedup hint alongside embedding similarity | §Write path |
| CP1 | **Working → Episodic**: Haiku summarization at thread-end (or N-hour idle) → episodic row(s) | §Compaction |
| CP2 | **Episodic → Semantic**: agent-driven nudge at thread-end ("anything worth promoting?") — Hermes pattern | §Compaction |
| CP3 | **Two-stage compaction**: non-LLM pre-pass + LLM pass. **Current `HeuristicCompactor` needs revamp** before becoming the pre-pass (new item O3.1). | §Compaction |
| CP4 | **Storage budgets**: 5K working (Redis TTL) / 10K episodic (FTS-pruned to top relevant) / ∞ semantic | §Compaction |
| MG1 | **Layer assignment for existing rows**: all → `semantic_freetext` | §Migration |
| MG2 | **Embedding backfill**: one-shot batch embed all existing rows immediately post-migration | §Migration |
| MG3 | **Migration mechanics**: single migration file `031_agent_memory_redesign.sql` | §Migration |
| MG4 | **`importance` column**: dropped after backfill | §Migration |
| PR1 | **PII detection**: deferred to v2 (multi-tenant). Solar-gen handles contacts intentionally in v1. | §Privacy |
| PR2 | **RLS**: per-scope policies from day 1, replacing the current permissive `auth.uid() IS NOT NULL` | §Privacy |
| PR3 | **Forget mechanics**: soft-expire only, no hard delete. **Non-GDPR-compliant — acceptable for current 2-user allowlist; blocks v3 multi-tenant.** | §Privacy |
| PR4 | **Encryption**: Supabase defaults only (TLS in transit, AES-256 disk-level at rest). | §Privacy |

---

## The five cognitive layers

| Layer | What it stores | Write trigger | Read profile | Decay | Current solar-gen location |
|---|---|---|---|---|---|
| **Working** | Live conversation, current todos, scratchpad, in-flight entity IDs | Implicit (message append) + explicit (`research_scratchpad`, `manage_todo`) | Always fully in-context up to budget | Volatile — Redis TTL (5K row cap per user) | `research_scratch` table today; migrates to Redis. |
| **Episodic** | Summarized conversation segments, research session outcomes, notable tool calls | Thread-end Haiku summarization | Top-K vector search filtered by user + recency | FTS-pruned at 10K rows per user; oldest+lowest-confidence trimmed first | New — `agent_memory` rows with `layer='episodic'` |
| **Semantic-structured** | Typed entity-attribute facts: `(entity, predicate, value)` — EPC relationships, entity attributes (HQ, founding year, employee count), contract/engagement terms, contact relationships | Track A structured-output extractor on key tools; promotions from episodic via Track B | Filter by entity + predicate + validity window; vector fallback | None — append-only with `valid_from`/`valid_until` | Lives in **`epc_engagements`** (bi-temporal extension) + `agent_memory` rows with `layer='semantic_structured'` |
| **Semantic-freetext** | Insights, preferences, "Acme delivers fast on residential but slow on utility" — assertions that don't fit a typed predicate | Track B Haiku judge; agent `remember` calls | Vector + BM25 hybrid retrieval filtered by user/workspace scope | In-place mutation on update | New — `agent_memory` rows with `layer='semantic_freetext'`. Existing free-form rows migrate here. |
| **Procedural** | "How to" knowledge: research playbooks, contact-discovery sequences, templates the agent has learned. Hermes-style **skills** as autonomous artifacts. | Track B + agent-driven nudge; future: usage-driven self-improvement (Hermes pattern) | Filter by task type + retrieval-by-similarity | Low decay; usage-counter for relevance | New — `agent_memory` rows with `layer='procedural'`. Future: dedicated `skills` table modeled on Hermes's skills system. |

---

## The five scope tiers

Every memory row carries four nullable scope columns plus a `scope_tier` enum declaring intended sharing:

| Scope | tenant_id | workspace_id | user_id | thread_id | Example |
|---|---|---|---|---|---|
| `global` | null | null | null | null | "EPCs typically structure POs as X." Objective facts. |
| `tenant` | set | null | null | null | "Civ Robotics's installs are 6 weeks faster than industry avg." |
| `workspace` | set | set | null | null | "Project #4291: customer wants Tier 1 panels only." Maps to current `project_id`. |
| `user` | set | (any) | set | null | "Fisher prefers concise responses." |
| `thread` | set | (any) | set | set | Working memory only. Conversation-scoped. |

**Phased population:**

| Phase | tenant_id | workspace_id | user_id | thread_id |
|---|---|---|---|---|
| **v1 (now)** | `'default'` | = current `project_id` | = `auth.uid()` | per-conversation |
| **v2** (deals / pipeline / portfolios) | `'default'` | per-deal / per-pipeline / per-portfolio | set | set |
| **v3** (multi-tenant SaaS) | per-customer | per-deal within customer | set | set |
| **v4** (curated cross-tenant) | `global` populated by curation rules | n/a | n/a | n/a |

---

## Schema target

### `agent_memory` — additive migration (`031_agent_memory_redesign.sql`)

```sql
-- Single migration file. Additive ALTERs preserve existing rows.
ALTER TABLE agent_memory
    ADD COLUMN layer TEXT NOT NULL DEFAULT 'semantic_freetext'
        CHECK (layer IN ('working', 'episodic', 'semantic_structured',
                         'semantic_freetext', 'procedural')),
    ADD COLUMN scope_tier TEXT NOT NULL DEFAULT 'workspace'
        CHECK (scope_tier IN ('global', 'tenant', 'workspace', 'user', 'thread')),
    ADD COLUMN tenant_id TEXT,
    ADD COLUMN workspace_id UUID,  -- backfilled from project_id
    ADD COLUMN user_id UUID REFERENCES auth.users(id),
    ADD COLUMN thread_id UUID,  -- backfilled from conversation_id

    -- Provenance
    ADD COLUMN source_type TEXT
        CHECK (source_type IN ('user_utterance', 'agent_inference',
                               'tool_output', 'document_extract',
                               'promoted_from_lower_layer', 'agent_remember')),
    ADD COLUMN source_ref JSONB,
    ADD COLUMN created_by_user_id UUID REFERENCES auth.users(id),

    -- Confidence (replaces importance after backfill)
    ADD COLUMN confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    ADD COLUMN confidence_source TEXT
        CHECK (confidence_source IN ('extractor_llm', 'retrieval_match',
                                     'user_confirmed', 'manually_verified',
                                     'agent_remember')),
    ADD COLUMN verification_status TEXT DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'acknowledged', 'verified')),

    -- Bi-temporal (populated only when layer = 'semantic_structured')
    ADD COLUMN valid_from TIMESTAMPTZ,
    ADD COLUMN valid_until TIMESTAMPTZ,
    ADD COLUMN superseded_by UUID REFERENCES agent_memory(id),
    ADD COLUMN superseded_at TIMESTAMPTZ,
    ADD COLUMN expired_at TIMESTAMPTZ,  -- soft-delete (PR3)

    -- TTL for working memory + time-bounded facts
    ADD COLUMN ttl_expires_at TIMESTAMPTZ,

    -- Structured-semantic extras (nullable, populated only when applicable)
    ADD COLUMN entity_id UUID REFERENCES entities(id),
    ADD COLUMN predicate TEXT,
    ADD COLUMN value JSONB,

    -- Embedding (pgvector)
    ADD COLUMN embedding vector(1536);

-- Backfill: existing rows get confidence from importance, then drop importance
UPDATE agent_memory
SET confidence = importance / 10.0,
    confidence_source = 'agent_remember',
    source_type = 'agent_remember',
    workspace_id = project_id,
    thread_id = conversation_id,
    tenant_id = 'default'
WHERE confidence IS NULL;

ALTER TABLE agent_memory DROP COLUMN importance;

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
CREATE INDEX idx_agent_memory_expired ON agent_memory (expired_at)
    WHERE expired_at IS NOT NULL;
-- Existing memory_tsv FTS index is preserved.

-- Embedding backfill is a separate one-shot Python script run after this migration:
-- agent/scripts/backfill_memory_embeddings.py
```

### `epc_engagements` — bi-temporal extension

```sql
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

### `research_scratch` → Redis

Working memory migrates from the Postgres `research_scratch` table to Redis. Postgres remains the durable fallback for >5-minute-old scratch entries. Migration `024`'s TTL semantics map directly to Redis `EXPIRE`.

### Future: `skills` table (Hermes-pattern procedural memory)

Deferred to a later phase. Hermes-style autonomous skill creation needs its own design round. v1 procedural memory lives in `agent_memory` rows.

---

## Provenance and confidence metadata

Every memory row carries the same metadata envelope:

| Field | Always populated? | Notes |
|---|---|---|
| `id` | yes | UUID |
| `layer` | yes | Enum |
| `scope_tier` | yes | Enum |
| `tenant_id`, `workspace_id`, `user_id`, `thread_id` | per `scope_tier` | Nullable scope chain |
| `memory` (content) | yes | Text or JSON-stringified |
| `embedding` | yes for semantic / episodic / procedural; null for working | pgvector(1536) |
| `created_at` | yes | Transaction time |
| `source_type` | yes | Enum: `user_utterance`, `agent_inference`, `tool_output`, `document_extract`, `promoted_from_lower_layer`, `agent_remember` |
| `source_ref` | yes | JSONB: thread+turn for utterance; tool_call_id for tool output; doc+span for document extract; parent_memory_id for promotion |
| `created_by_user_id` | yes | Audit trail + "forget me" hook |
| `confidence` | yes | Float 0–1 |
| `confidence_source` | yes | Enum |
| `verification_status` | yes (default `unverified`) | Enum |
| `valid_from`, `valid_until` | only `layer='semantic_structured'` | Bi-temporal |
| `superseded_by`, `superseded_at` | populated on update of structured semantic | Append-only history |
| `expired_at` | populated on soft-expire (forget) | Soft-delete |
| `ttl_expires_at` | only working memory + time-bounded facts | TTL |
| `entity_id`, `predicate`, `value` | only `layer='semantic_structured'` | Knowledge-graph fields |
| `memory_key` (existing) | optional | Retained as a dedup hint alongside embedding similarity |

**Confidence integration with existing `confidence.py`.** The EPC-source aggregator (`compute_confidence_upgrade`) continues to operate on `EpcSource` lists and produces a 4-level enum. When a finding writes to memory, we map the enum to a float:

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
| **Durable** | Supabase Postgres + `pgvector` | All five memory layers' canonical rows. Embeddings. RLS for tenant isolation. |
| **Hot path** | Hosted Redis (Upstash) | Working memory (replaces `research_scratch` for active sessions). Job queue stub (Redis Streams) for future async Track B. Distributed locks (write serialization per entity). Tool-result cache (short-TTL). Pub/sub + Redis Streams for memory-event fanout. |
| **Cold artifacts** | Supabase Storage | Raw scraped HTML, large tool outputs, full document content. Memory rows reference by handle (`source_ref.object_key`). |

**Operational notes:**

1. **Working-memory durability**. Redis blip = ephemeral state loss. Acceptable contract: working memory is volatile; on Redis unavailability, user re-asks. Postgres `research_scratch` remains as fallback for >5-minute-old scratch.
2. **Cache invalidation**. Embedding cache keyed by content hash is immutable. LLM-response cache keyed by `(prompt_version, model, content_hash)` invalidates on prompt-version bump.
3. **Lock hygiene**. Distributed locks need timeout + fencing tokens. Use a Redlock-pattern client; don't hand-roll.
4. **Pub/sub vs Streams**. Pub/sub for non-critical UI notifications. Redis Streams for memory-promotion events that consumers need to process exactly once.

---

## Read path (O1 sub-spec)

The read path produces a prompt that combines: (a) a small always-on memory context block, (b) optionally injected dynamic retrieval results, and (c) on-demand mid-turn retrievals the agent triggers via the `recall` tool.

### Pre-turn assembly

```
1. Build the memory context block (always-on, ~1.5K tokens)
   ├─ Persona / USER.md block (~300-500 tokens)
   │    Fixed across sessions: name, role, communication preferences,
   │    permanent context. Stored at scope=user, layer=semantic_freetext,
   │    marked verification_status='manually_verified'. Hermes USER.md analog.
   │
   ├─ Top-5 user-scoped semantic facts (~250-400 tokens)
   │    SELECT * FROM agent_memory
   │    WHERE scope_tier='user' AND user_id=auth.uid()
   │      AND layer IN ('semantic_freetext','semantic_structured')
   │      AND expired_at IS NULL
   │    ORDER BY confidence DESC, created_at DESC
   │    LIMIT 5
   │
   ├─ Active todos (~200-300 tokens)
   │    From manage_todo for the current thread.
   │    Existing infrastructure from plans/2026-03-29-agent-self-management.md.
   │
   └─ Workspace summary (~200-300 tokens)
        1-2 sentences about the current project/deal + key entities in scope.
        Auto-generated from workspace metadata + recent activity. Stored as a
        scope_tier='workspace' row, regenerated on workspace event triggers.

2. Heuristic-gated auto-retrieval
   ├─ Run cheap regex over user message: extract entity-name candidates,
   │   project IDs (UUID format), known patterns (EPC names, dev names from
   │   `entities` table). If matches found → proceed to retrieval.
   │
   ├─ If no matches → skip auto-retrieval. Save the 3K dynamic budget for
   │   agent-triggered recall calls.

3. Multi-query Haiku expansion (only if auto-retrieval fires)
   ├─ Single Haiku call generates 3 retrieval queries from the user message:
   │   - Literal (user's message, lightly preprocessed)
   │   - Expanded (synonyms, related entities)
   │   - HyDE (a hypothetical answer to the user's question)
   │
   └─ Merge results across all three queries via reciprocal rank fusion.

4. Hybrid retrieval
   ├─ Vector ANN top-20 over embedding column (pgvector cosine, HNSW index)
   ├─ BM25 top-20 over memory_tsv (existing FTS GIN index)
   ├─ RRF merge → 30-40 candidates
   └─ Cross-encoder rerank → top-5 (final result, ~3K tokens)

5. Scope filtering with weighted rerank
   ├─ Retrieval pulls from FULL scope chain (thread ∪ user ∪ workspace ∪
   │   tenant ∪ global) — no scope-level exclusion at the query layer
   │
   └─ Scope weights applied during rerank: lower-scope facts surface first.
       Suggested weights: thread=1.0, user=0.95, workspace=0.85, tenant=0.7,
       global=0.5. (Calibrated against eval set in P9.)

6. Stitching: insert into system message
   System prompt structure (preserved KV-cache prefix from existing work):

   <role instructions>
   <memory-context>
   ## Persona
   {persona_block}

   ## Your remembered preferences
   {top_5_user_prefs}

   ## Active todos
   {active_todos}

   ## Workspace context
   {workspace_summary}

   ## Retrieved memory (only present if auto-retrieval fired)
   {top_5_retrieval_results}
   </memory-context>
   <tool definitions>
```

The `<memory-context>` fences are the Hermes pattern. Stable structural placement maximizes KV-cache hit rate per `plans/2026-03-12-agent-upgrades-5-phases.md` Phase 1 discipline.

### Dynamic recall (agent-triggered, mid-turn)

The existing `recall` tool is rebuilt:

- Takes `query` (free text), optional `scope_chain` (defaults to full chain), optional `layer_filter`, optional `entity_id` for structured-fact lookup.
- Runs the same hybrid retrieval pipeline as auto-retrieval (vector + BM25 + rerank).
- Returns top-5 results with confidence + source attribution.
- Token cost: ~0.5K–1K per call. Agent can call multiple times in a turn; total dynamic budget across all calls capped at 3K (enforced at the tool layer).

### What's deferred (read-path implementation details)

- Cross-encoder model choice (BGE-reranker-v2 vs Cohere rerank-3 vs in-process MiniLM). Decided at P2 implementation.
- Embedding model choice (text-embedding-3-small vs voyage-3 vs Cohere embed-v3). Decided at P2.
- Exact entity-name regex patterns for heuristic gate. Decided at P2.
- Scope-weight calibration. Done during P9 eval.

---

## Write path (O2 sub-spec)

### Architecture: one pipeline, three triggers

```
                  TRIGGER SURFACES                         COMMON PIPELINE                STORAGE
   ┌──────────────────────────────────────┐    ┌────────────────────────────────┐    ┌──────────┐
   │ 1. Agent's `remember` tool           │    │  memory_write(candidate):      │    │          │
   │    source_type='agent_remember'      ├───►│   1. Validate envelope         ├───►│  agent_  │
   │                                      │    │   2. Embed if needed           │    │  memory  │
   │ 2. Track A: structured-output        │    │   3. Top-3 nearest neighbors   │    │          │
   │    extractor on key tool outputs     ├───►│      in same scope + layer     │    └──────────┘
   │    source_type='tool_output'         │    │   4. Cosine sim check:         │
   │                                      │    │      ≥0.92 → UPDATE existing   │    ┌──────────┐
   │ 3. Track B: Haiku judge on           │    │      0.85–0.92 → classifier    │    │  epc_    │
   │    tool-call turns                   ├───►│      <0.85 → ADD               ├───►│ engage-  │
   │    source_type='agent_inference'     │    │   5. Run ADD/UPDATE/DELETE/    │    │  ments   │
   │                                      │    │      NOOP classifier (Haiku)   │    │          │
   └──────────────────────────────────────┘    │   6. Attach scope + provenance │    └──────────┘
                                               │   7. Acquire entity-level lock │
                                               │      (Redis Redlock)           │
                                               │   8. INSERT or supersede       │
                                               │   9. Release lock              │
                                               │  10. Emit memory-event         │
                                               │      (Redis Stream)            │
                                               └────────────────────────────────┘
```

Single function in `agent/src/memory/write.py`. Triggers are thin adapters that build the candidate envelope and call `memory_write()`.

### Trigger 1: agent `remember` tool

`agent/src/tools/remember.py` updated:
- `importance` parameter deprecated in tool input schema. Agent supplies optional `confidence` (float 0–1) instead. Default 0.7 if omitted.
- `scope` parameter expanded from 2-tier (`project`/`global`) to 5-tier enum.
- `layer` parameter added (default `semantic_freetext`).
- `memory_key` retained as optional dedup hint.

On call: assemble candidate envelope (content, scope, layer, confidence=user-supplied, confidence_source='agent_remember', source_type='agent_remember', source_ref={turn_id, tool_call_id}) → call `memory_write()`.

### Trigger 2: Track A — structured-output extractor

A `post_tool` hook in `agent/src/hooks/track_a_extract.py`. Fires on:

| Tool | Extraction target | Predicate set |
|---|---|---|
| `report_findings` | Developer → EPC → project relationships, sources, confidence | `(developer, used_epc_for, project)`, `(project, has_developer, dev)`, `(project, has_epc, epc)`, `(project, source_url, url)` |
| `fetch_page` on `sec.gov`, `osha.gov`, `enr.com`, `solarpowerworldonline.com` | Entity attributes (parsed from structured pages) | `(entity, headquartered_in, location)`, `(entity, employee_count, n)`, `(entity, ticker, sym)`, `(entity, founded, year)`, `(entity, parent_company, ref)`, `(project, contract_value, $)`, `(project, ntp_date, date)`, `(project, cod_date, date)` |
| `save_contact`, `push_to_hubspot` | Contact relationships | `(person, works_at, org)`, `(person, role, title)`, `(person, email, addr)`, `(person, phone, num)` |
| `approve_discovery` | Verification status upgrade | Promotes prior `report_findings` row to `verification_status='verified'` |

**Pattern source: structured outputs / JSON schemas, not regex.** Each Track A tool is updated so its return value is already a typed JSON object matching a Pydantic schema (e.g., `ReportFindings`, `FetchedSECFiling`). The hook reads the typed JSON; no regex parsing. New parsers for `fetch_page` on known URLs use Claude with `response_format` set to a JSON schema for that source type.

Track A writes are sync (post_tool hook, no Haiku call). Confidence on the row comes from `confidence.py`'s aggregator for `report_findings` outputs; for other tools, defaults are calibrated per-tool (e.g., SEC filing fact = 0.9, HubSpot contact = 1.0, fetched-page extraction = 0.7).

### Trigger 3: Track B — Haiku judge on tool-call turns

A `post_turn` hook that runs only when the just-completed turn included one or more tool calls. Pure-chat turns are skipped (Hermes periodic-nudge pattern at thread-end backfills them).

**Judge prompt design:**
- Haiku 4.5 model
- Input: the just-completed turn (user message + assistant reply + tool calls + tool results)
- Output: JSON `{ "verdict": "ADD" | "NOOP", "candidates": [...], "rationale": "..." }`
- **High NOOP bar**: prompt explicitly defaults to NOOP. Only extracts when something is durable and non-trivial. Examples in the prompt: extract `"customer confirmed Tier 1 panel requirement"`; skip `"agent ran a search for Acme Solar"`.
- Each candidate has: content, suggested_layer, suggested_scope_tier, suggested_confidence, rationale.
- Target extract rate: ~20–30% of tool-call turns produce ≥1 candidate.

Candidates feed into `memory_write()` with `source_type='agent_inference'`, `confidence_source='extractor_llm'`.

### Dedup pipeline

`memory_write()` calls dedup *before* the ADD/UPDATE/DELETE/NOOP classifier:

```python
def dedup_and_classify(candidate):
    # 1. Find top-3 nearest neighbors in same (scope_tier, layer)
    neighbors = vector_search(candidate.embedding, scope=candidate.scope,
                              layer=candidate.layer, top_k=3)

    if not neighbors:
        return ADD

    top_sim = neighbors[0].cosine_sim
    if top_sim >= 0.92:
        return UPDATE, neighbors[0]
    if top_sim >= 0.85:
        # Borderline — let the classifier decide
        return haiku_classify(candidate, neighbors)
    return ADD
```

The ADD/UPDATE/DELETE/NOOP classifier is a Haiku call that takes the candidate + top-3 neighbors and returns one of the four verdicts plus the target row for UPDATE/DELETE.

### Hermes periodic-nudge pattern

At thread-end (or every N tool-call turns within a long thread), the system injects a synthetic user message: *"Before we close this conversation — is there anything from today you should remember for future sessions? Use the `remember` tool to save anything important."* This is the procedural pattern that backfills pure-chat learnings and gives the agent explicit attention on consolidation. Frequency tuned in P9.

### Memory key (existing dedup hint) handling

The existing `memory_key` field is retained but its role shifts:
- Embedding similarity is the primary dedup signal.
- `memory_key` is a secondary hint: if the candidate's `memory_key` matches an existing row in the same scope, the classifier treats it as a strong UPDATE signal even if embedding similarity is below 0.85.
- Existing rows' `memory_key` values are preserved through migration.

---

## Compaction & promotion (O3 sub-spec)

### Working → Episodic (thread-end)

Triggered by:
- Explicit thread close (user starts a new conversation, or hits "end conversation" in UI)
- N-hour idle (default: 24 hours since last message)

Pipeline:
1. Two-stage compaction (see below) produces a single narrative summary of the thread.
2. Summary becomes one episodic row: `layer='episodic'`, `scope_tier='thread'`, `source_type='promoted_from_lower_layer'`, `source_ref={thread_id, message_count, started_at, ended_at}`.
3. If the thread contained Track A extractions (semantic_structured rows already written during the thread), they remain at their scope tiers; the episodic row references them via `source_ref.linked_facts`.
4. Working memory in Redis is allowed to TTL out (no explicit deletion needed).

### Episodic → Semantic (agent-driven nudge, Hermes pattern)

At thread-end (immediately before working→episodic compaction), the agent receives the Hermes periodic-nudge prompt: *"What from this conversation should be remembered permanently? Promote facts via `remember`."*

Agent-driven, not auto. Quality is higher because the agent has the reasoning context for what mattered. Cost is one extra Haiku turn at thread-end.

Auto-promotion based on episodic clustering (e.g., "agent saw this pattern 3+ times") is **deferred to v2** — requires the async job queue (F1 deferred).

### Two-stage compaction architecture

```
   thread messages
        │
        ▼
   ┌─────────────────────┐
   │ Stage 1: Heuristic  │   <-- non-LLM, structure-aware
   │  (REVAMP — O3.1)    │       preserves: entity IDs, file paths,
   └──────────┬──────────┘       active todos, tool_call_ids, key
              │                  scratchpad slots
              ▼
   ┌─────────────────────┐
   │ Stage 2: LLM pass   │   <-- Haiku call
   │ (LlmCompactor)      │       takes heuristic output + preserved
   └──────────┬──────────┘       structured slots, produces narrative
              │                  summary that retains key entities
              ▼
       episodic row written
```

**Current `HeuristicCompactor` (`agent/src/runtime/compactor.py`) is immature.** The current implementation does string-extraction with limited structure preservation. Before it becomes the Stage 1 pre-pass, it needs a dedicated research round. Tracked as **open item O3.1**.

Until O3.1 lands, the existing `HeuristicCompactor` is the Stage 1 fallback — runs, produces a heuristic summary, Stage 2 LLM pass takes that summary as input. Output quality is limited by Stage 1; expect to revisit.

### Storage budgets (per user, v1)

| Layer | Cap | Eviction strategy |
|---|---|---|
| Working | 5K rows | Redis TTL (default 1 hour, extended on access) |
| Episodic | 10K rows | At 10K, oldest+lowest-confidence rows pruned to FTS-only access (vector index entries dropped); below 8K threshold, fully evicted |
| Semantic-structured | ∞ | Append-only with supersession; supersededs not counted toward live total |
| Semantic-freetext | ∞ | In-place mutation; soft-expired rows count toward total until hard-cleanup (currently never, per PR3) |
| Procedural | ∞ | In-place; manual lifecycle for now |

Budgets re-evaluated in P9 eval phase based on actual growth + retrieval-latency curves.

---

## Migration plan (O7 sub-spec)

### Single migration file: `031_agent_memory_redesign.sql`

Contains all ALTER TABLE statements + the in-SQL backfill (importance → confidence, project_id → workspace_id, conversation_id → thread_id, tenant_id = 'default'). Reversible via `032_agent_memory_redesign_rollback.sql` if needed within 7 days of deploy.

### Embedding backfill: separate one-shot Python script

`agent/scripts/backfill_memory_embeddings.py`:
- Reads all rows where `embedding IS NULL`
- Batches in groups of 100 (OpenAI / chosen embedding API supports batching)
- Writes embeddings back via UPDATE
- Estimated cost at current volume: <$1 total

Runs once after `031` migration deploys. Idempotent — safe to re-run.

### Existing-rows treatment

All existing `agent_memory` rows are assigned:
- `layer='semantic_freetext'` (default per CHECK constraint)
- `scope_tier='workspace'` if `project_id` is non-null, else `'global'`
- `confidence = importance / 10.0`
- `confidence_source='agent_remember'`
- `source_type='agent_remember'` (best approximation; we don't have real source info on these)
- `created_by_user_id=NULL` (we don't know who wrote them — pre-multiuser)
- `tenant_id='default'`
- `workspace_id = project_id` (in addition to keeping project_id as alias — `project_id` column retained as-is, `workspace_id` is the new canonical)
- `thread_id = conversation_id` (similarly)

### Column drops

- `importance` dropped after backfill (in the same migration).
- `project_id` and `conversation_id` retained as aliases. Application code reads/writes from the new `workspace_id` / `thread_id` columns going forward.

### Deploy sequence

1. Deploy code that **reads** from both old and new column names (compat shim in `db.py`).
2. Run `031_agent_memory_redesign.sql`.
3. Run `backfill_memory_embeddings.py`.
4. Deploy code that **writes** only to new column names.
5. After 7-day stability window, drop the old `project_id` / `conversation_id` columns in `033_drop_aliases.sql`.

---

## Privacy & security (O6 sub-spec)

### PII detection: deferred to v2

Solar-gen handles contacts intentionally — emails, phones, names are first-class data, not contamination. PII detection adds complexity without clear v1 benefit. Revisit when multi-tenant lands (v3) and tenant isolation makes PII boundary-crossing a real risk.

### RLS policies (per-scope, from day 1)

Replace the current `auth.uid() IS NOT NULL` policy with scope-aware policies:

```sql
-- Drop old permissive policy
DROP POLICY "Authenticated read" ON agent_memory;

-- New read policy
CREATE POLICY "Scope-aware read" ON agent_memory FOR SELECT USING (
    expired_at IS NULL AND (
        scope_tier = 'global'
        OR (scope_tier IN ('tenant', 'workspace')
            AND tenant_id = current_setting('app.current_tenant', true))
        OR (scope_tier = 'user' AND user_id = auth.uid())
        OR (scope_tier = 'thread' AND user_id = auth.uid()
            AND thread_id::text = current_setting('app.current_thread', true))
    )
);

-- Write policy — agent service-role bypasses RLS; user-driven writes
-- (forget, edit via UI) constrained to own rows
CREATE POLICY "Owner write" ON agent_memory FOR UPDATE USING (
    created_by_user_id = auth.uid()
);
```

Application sets `app.current_tenant` and `app.current_thread` session variables on each request. For v1, `current_tenant = 'default'` always.

### Forget mechanics: soft-expire only

The `forget` tool (new) sets `expired_at = now()` on the target row. Reads filter `expired_at IS NULL` so expired rows are invisible. **No hard delete.**

**GDPR caveat — explicit limitation of v1**: this means "delete all my data" requests cannot be honored. Acceptable for the current 2-user allowlist (where data subject = the team itself). **This blocks v3 multi-tenant launch** — before going multi-tenant we must add a hard-delete path. The migration for that work will: (a) cascade-delete soft-expired rows older than N days for the requesting user, (b) anonymize remaining rows by clearing `created_by_user_id` and stripping content where appropriate, (c) preserve aggregated counts only.

Tracked as a pre-v3 release blocker.

### Encryption

Supabase defaults only:
- TLS in transit (managed by Supabase)
- AES-256 disk-level at rest (managed by Supabase)

No column-level encryption — would break FTS and vector search (encrypted bytes don't embed). No row-level audit logging beyond what Supabase provides. Revisit if/when a customer compliance ask lands.

---

## Hermes pattern integration (H1 confirmed)

Hermes = NousResearch/hermes-agent (https://github.com/NousResearch/hermes-agent). The relevant patterns we adopt:

| Hermes pattern | Solar-gen integration |
|---|---|
| `USER.md` / `MEMORY.md` / `SOUL.md` file-based persistent memory | Persona block + top-5 user prefs in the always-on memory context (RP5). Same shape, DB-backed instead of file-backed. |
| Agent-curated writes with periodic nudges | `remember` tool as first-class write surface (WP1). Periodic nudge prompt at thread-end (CP2). |
| FTS5 session search + LLM summarization for cross-session recall | BM25 over `memory_tsv` + multi-query Haiku expansion (RP4, RP7). |
| Skills as autonomous procedural-memory artifacts | Procedural layer (D1) in v1; dedicated `skills` table modeled on Hermes in a future phase. |
| Honcho dialectic user modeling | Out-of-scope for v1; future consideration for the persona block evolution. |

Hermes also uses MCP for tool surfaces; solar-gen continues to use direct Anthropic-SDK tool definitions. Not changing that.

---

## Open items

### Resolved this round

| # | Item | Where it landed |
|---|---|---|
| H1 | Hermes reference confirmation | §Hermes pattern integration |
| O1 | Read path | §Read path |
| O2 | Write path | §Write path |
| O3 | Compaction / promotion | §Compaction & promotion |
| O6 | Privacy / security specifics | §Privacy & security |
| O7 | Migration plan for existing rows | §Migration plan |

### Still open

| # | Item | Why blocked / deferred |
|---|---|---|
| **O3.1** | **Heuristic compactor revamp** (NEW) | Current `HeuristicCompactor` is immature. Needs its own research round on what structure-aware non-LLM compaction should preserve (entity IDs, todo slots, scratchpad keys, tool_call_id chains). Required before Stage 1 of two-stage compaction (CP3) can be considered production-grade. |
| O4 | Governance UX (memory inspector, edit/forget flows, export) | Backend lock first; UI design follows. Estimated 4–5 questions in a dedicated round once P6 (write path async) is in. |
| O5 | Evaluation framework | Designed alongside implementation. LongMemEval-style benchmark + solar-gen-specific eval set covering EPC-research memory recall, scope-isolation correctness, dedup behavior, and confidence calibration. ~3 questions in a dedicated round in P9. |

### Implementation-detail items (intentionally not in this design lock)

These are decided at the relevant implementation phase, not now:
- Cross-encoder reranker model (BGE-reranker-v2 vs Cohere rerank-3 vs in-process MiniLM) → P2
- Embedding model (text-embedding-3-small vs voyage-3 vs Cohere embed-v3) → P2
- Heuristic auto-retrieval entity-regex patterns → P2
- Track B judge prompt exact wording → P4
- Scope-weight calibration values → P9
- Storage budget tuning → P9

### Pre-v3 release blockers (must be resolved before multi-tenant)

- **GDPR hard-delete path** (currently `forget` is soft-expire only per PR3). Required for tenant-isolated "delete all my data" support.
- **PII detection** (currently deferred per PR1). Required to keep tenant boundaries from leaking PII-rich content across scopes.
- **Cross-tenant retrieval safety**. RLS policies as specified in PR2 cover the read path; write-side enforcement needs an audit before multi-tenant.

---

## Implementation phasing

| Phase | Scope | Depends on |
|---|---|---|
| **P0** | This document. Design lock. | — |
| **P1** | Schema migration. `031_agent_memory_redesign.sql` runs. Embedding backfill script runs. pgvector extension enabled. New scope/layer columns populated for existing rows. No code path changes yet — old `recall`/`remember` continue to work against the new schema via compat shim. | P0 |
| **P2** | New read path. Hybrid retrieval (`pgvector` + BM25 + cross-encoder rerank). New `recall` tool implementation behind a feature flag; old keyword-only path preserved as fallback. Memory context block injected into system prompt with `<memory-context>` fences. Heuristic-gated auto-retrieval. Multi-query Haiku expansion. Scope-weighted rerank. | P1 |
| **P3** | Write path Track A. Structured-output extractors as `post_tool` hooks on `report_findings`, known-URL `fetch_page`, `save_contact`/`push_to_hubspot`, `approve_discovery`. Writes structured-semantic rows with bi-temporal columns into `agent_memory` (and updates `epc_engagements` with bi-temporal columns). `memory_write()` pipeline with embedding dedup + ADD/UPDATE/DELETE/NOOP classifier. | P1, P2 |
| **P4** | Write path Track B (sync). Haiku judge as `post_turn` hook on tool-call turns. High NOOP bar. Writes via `memory_write()`. Agent `remember` tool migrated to new schema (importance → confidence). | P3 |
| **P5** | Redis hot path. Upstash connection wired. Working memory migrated from `research_scratch` Postgres to Redis with TTL. Job queue stub (Redis Streams) for future async work. Distributed locks for `memory_write()` entity serialization. | P4 |
| **P6** | Track B async. Promote sync Haiku judge to async via Redis Streams. Frees the user turn from extraction latency. | P5 |
| **P6.5** | **O3.1 research round**: structure-aware heuristic compactor revamp. Decide what slots Stage 1 preserves verbatim. Reimplement `HeuristicCompactor`. | P5 (independent of P6) |
| **P7** | Compaction & promotion. Two-stage compactor (revamped Stage 1 + new LlmCompactor Stage 2). Working → episodic at thread-end. Episodic → semantic via agent nudge. Storage-budget enforcement. | P6, P6.5 |
| **P8** | Governance UX (O4 round). Memory inspector page in frontend. Forget/edit flows. RLS policy audit. | P7, O4 design round |
| **P9** | Evaluation framework (O5 round). LongMemEval-style benchmark + solar-gen-specific eval set. Calibrate scope weights, storage budgets, dedup thresholds. | P8, O5 design round |
| **Pre-v3** | GDPR hard-delete path + PII detection. Required before multi-tenant launch. | P9 |

Each phase has its own implementation plan (`plans/2026-XX-XX-agent-memory-phaseN.md`) before code starts. Per CLAUDE.md, code changes wait for Fisher's explicit go-ahead on each phase.

---

## Not in scope

- **Re-introducing `workspaces` table**. Migration `016` dropped it; design uses `workspace_id` conceptually. Real `workspaces` table returns only if/when v3 multi-tenant lands.
- **Custom Postgres-backed job queue (gbrain's `minion_jobs`)**. Redis Streams covers v1–v2.
- **Nightly consolidation**. Deferred to v2+ (requires job queue + meaningful fact volume).
- **Cross-tenant `global` knowledge pool population**. Schema-supported; populating it is a v4 product call.
- **LangGraph / LangMem / Mem0 / Letta integration**. Explicitly rejected.
- **Hard-delete for `forget`**. Soft-expire only in v1 (PR3). Hard-delete required pre-v3.
- **PII detection on writes**. Deferred to v2 (PR1).
- **Column-level encryption**. Defer until compliance asks (PR4).
- **Honcho user-modeling integration**. Future consideration, not v1.
- **Skills as a dedicated table** (Hermes-style). Procedural layer in `agent_memory` for v1; dedicated `skills` table is a future phase.

---

## Review checklist for Fisher

Phase 0 + 0.5 lock review:

- [ ] Confirm the **Hermes pattern integration** (H1 resolved to NousResearch/hermes-agent — adopting file-shape persona, agent-curated writes with nudges, FTS+summarization, skills-as-procedural).
- [ ] **Read path** (§Read path, RP1–RP8): hybrid injection, system-message fences, 1.5K + 3K budget, vector+BM25+rerank, prefix composition, heuristic-gated auto-retrieval, multi-query Haiku expansion, scope-weighted rerank.
- [ ] **Write path** (§Write path, WP1–WP8): one pipeline three triggers; Track A structured-outputs on four trigger surfaces; Track B Haiku on tool-call turns with high NOOP bar; embedding-similarity dedup; `remember` migration.
- [ ] **Compaction** (§Compaction, CP1–CP4): thread-end Haiku for working→episodic; agent-nudge for episodic→semantic; two-stage compaction (acknowledging O3.1 revamp as a new open item); storage budgets.
- [ ] **Migration** (§Migration, MG1–MG4): single migration file, all rows → semantic_freetext, one-shot embedding backfill, drop importance.
- [ ] **Privacy** (§Privacy, PR1–PR4): PII deferred, per-scope RLS, soft-expire only **(acknowledge GDPR caveat blocks v3)**, Supabase encryption defaults.
- [ ] Confirm the **revised implementation phasing** P1 → Pre-v3.
- [ ] Flag anything that contradicts your read of the prior research that I should reconcile in writing.

After this review, P0.5 is complete and we move to:
- O3.1 research round (heuristic compactor revamp) — can happen in parallel with P1/P2 implementation
- P1 implementation plan (`plans/2026-XX-XX-agent-memory-p1-schema.md`)
- O4 design round (governance UX) — paced to land before P8
- O5 design round (eval framework) — paced to land before P9
