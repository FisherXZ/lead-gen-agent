# Agentic RAG Memory Architecture — Findings

**Date:** 2026-05-17
**Author:** Agent-memory redesign discovery (Fisher + Claude)
**Branch:** `claude/agent-memory-design-mUZ3T`
**Status:** Discovery notes — third of three reference-system surveys feeding the upcoming redesign plan. Not an implementation spec.

---

## Why this document exists

We're redesigning solar-gen's agent memory subsystem. Three reference systems are being surveyed before we design our own:

1. **gbrain** — Anthropic's internal long-horizon Postgres memory with bi-temporal columns and an async job queue. See `research/2026-05-17-gbrain-memory-architecture-findings.md`.
2. **Hermes** — bounded-markdown agent memory with pre-turn prefetch + post-turn judge. Separate doc.
3. **Agentic RAG** — the public consensus pattern that has consolidated across Mem0, LangGraph/LangMem, LlamaIndex's agent-memory module, Letta/MemGPT, Zep/Graphiti, and several recent papers (e.g., the "A-Mem"/"agentic memory" line of work). **This document.**

"Agentic RAG" is not a single library — it's a *shape* that converged through 2024–2025 once teams started treating long-running agents as something other than chatbots. The components have become stable enough that you can describe them generically. This doc captures the canonical version.

---

## 1. What "agentic RAG" means as a memory architecture

Most introductions to RAG describe it as a retrieval pattern: take a user query, embed it, look up similar chunks, stuff them into the prompt, generate. That framing is one-shot and stateless. **Agentic RAG** keeps the retrieval machinery but inverts the role of memory: the agent is the long-lived entity, the corpus is *the agent's own history plus what it has learned*, and retrieval is a normal step inside an action loop rather than the front door.

Concretely, the canonical agentic-RAG memory stack has six moving parts, glued together by an action loop:

1. **A four-layer cognitive store** (working / episodic / semantic / procedural — section 2).
2. **A hybrid retrieval index** over each persistent layer: BM25 (lexical), dense vector (semantic), and a cross-encoder reranker on the merged candidate set (section 3).
3. **An auto-extraction pipeline** that fires after each turn — or on a configurable cadence — and decides whether what just happened contains a *durable* fact, then classifies that fact as ADD / UPDATE / DELETE / NOOP against existing memory (section 4).
4. **Bi-temporal validity** (`valid_from`, `valid_until`) on every fact-bearing row so contradictions become supersessions instead of overwrites.
5. **A compaction step** that doesn't just shrink the context but *promotes* durable insights into long-term memory before producing the working-context summary (section 5).
6. **Tool-use surface**: the agent gets `recall` / `search_memory` / `add_memory` / `forget` as first-class tools, alongside the more familiar retrieval-over-documents tools. Memory is something the agent can *act on*, not just something the system injects.

The end-to-end loop on a single user turn looks like this (with the variant names different libraries use in parentheses):

```
user turn arrives
   │
   ▼
[pre-turn assemble]   ── working memory (live conversation + scratchpad)
   │                  ── retrieval over episodic + semantic + procedural
   │                     • embed query → ANN top-K
   │                     • BM25 top-K on same query
   │                     • merge → cross-encoder rerank → top-N
   │                     • filter: valid_until IS NULL (or "as-of" timestamp)
   ▼
[LLM call]   tools available: recall, add_memory, forget, ...
   │
   ▼
[tool loop]  agent may call recall again with refined queries,
             may write add_memory mid-turn for things it discovers,
             may call forget on contradicted facts
   │
   ▼
[post-turn extract]   small-model judge: "is there a durable fact here?"
   │                  if yes → candidate fact(s) extracted
   ▼
[ADD/UPDATE/DELETE/NOOP]  candidate fact vs. retrieved neighbors
   │                       → write to episodic and/or semantic
   ▼
[compact if needed]   working memory exceeds budget?
                       → promote insights into LTM
                       → emit summary block
                       → preserve last K turns verbatim
```

Two things are non-obvious in this picture and worth calling out before the layer-by-layer breakdown:

- **Retrieval and writes touch the same store.** A naive reading separates "vector DB" from "agent memory." In agentic RAG they're the same set of tables, with the four layers as logical categories and a single hybrid index serving them. The corpus grows from the agent's own activity.
- **The model is on both sides of the boundary.** It calls memory tools during a turn (a *judgment* use of memory) and is also called *by* the memory pipeline after the turn (a *judgment* operation on memory). Same model, different roles. This is where "agentic" earns the name — memory is no longer passive.

The system flow above is the part that's load-bearing. Everything else — exact rerank model, exact extraction prompt, exact compaction threshold — varies between implementations without breaking the design.

---

## 2. The four cognitive layers

The four-layer taxonomy (working / episodic / semantic / procedural) is borrowed from cognitive science but has become specific enough in agentic-RAG implementations that the categories have concrete schemas. The split matters because each layer has a different *retrieval profile*, a different *write trigger*, and a different *decay behavior*. Conflating them is the most common shape of weak implementation.

### 2.1 Working memory

**What it stores.** The live conversation: messages on the current turn, the in-flight scratchpad the agent uses to track sub-goals, the current plan/todo list, and any "session state" the harness injects (entity IDs in scope, active filters, etc.). Volatile.

**How it's written.** Implicitly by the conversation itself (every message appends), explicitly by the agent through scratchpad/todo tools. Not subject to the extraction pipeline — working memory is by definition not yet promoted.

**How it's read.** Always fully in-context up to a budget. Once the budget is hit, compaction (section 5) runs, which is the *only* time working memory interacts with the rest of the system.

**Characteristic operations.** Append, mutate-scratch, mark-todo-done, compact. No retrieval — it's already in the prompt.

**Strong vs. weak.**
- Strong: working memory is *structured* (todo list with status, scratchpad as keyed JSON, named slots for IDs in scope) so the agent can reliably refer to it by key. Compaction is structure-aware — it knows which scratch keys to preserve verbatim and which to summarize.
- Weak: working memory is just "the message list." When compaction fires, key IDs (entity IDs, contact IDs) disappear because the compactor sees them as ordinary tokens.

### 2.2 Episodic memory

**What it stores.** "Events that happened": a research session and its outcome, a conversation turn that resolved a user request, a tool call that produced something noteworthy. Each row is *narrative* — it has a time, an actor, an object, and a context.

The unit is typically one of:
- A summarized conversation segment ("user asked about Sunrun's Texas projects, agent found 4, user accepted 2 and rejected the rest with reason X").
- A research session with its query, sources visited, and outcome.
- A user preference *statement* (the act of stating, with timestamp), distinct from the semantic fact that gets distilled out of it.

**How it's written.** Two patterns coexist:
- *On the boundary* (end of turn or end of session) by the auto-extraction pipeline — the small-model judge looks at the turn and writes a single episodic row summarizing it.
- *Mid-turn* by the agent itself, when it has metacognitive reason to mark something as worth remembering ("I tried OSHA for McCarthy and got nothing — record this dead end so I don't repeat it").

**How it's read.** Retrieved by hybrid search with a strong recency bias. Episodes are dated; queries often have an implicit "what happened recently about X" intent that pure vector similarity will miss. Most implementations apply an exponential recency weight on top of the rerank score.

**Characteristic operations.** ADD (almost always — episodes are immutable events). UPDATE is rare. DELETE happens only for redaction. The dominant write is just append-with-embed.

**Strong vs. weak.**
- Strong: each episode is self-contained — has its own embedding-friendly summary, a structured tag set (`actor`, `tool_used`, `outcome`, `entities_referenced`), and links to the raw turn it came from. Hybrid retrieval works because the summary is rich enough for BM25 to hit *and* dense enough for vector to score.
- Weak: episodes are dumped tool-result transcripts. Embeddings are noisy because the text is dominated by tool boilerplate. BM25 hits on the wrong tokens (tool names, URLs). Recency weighting compensates only partially.

### 2.3 Semantic memory

**What it stores.** Distilled, atemporal-ish *facts*. "Sunrun used Blattner as EPC on their 2023 Texas portfolio." "User prefers field-leader contacts over PMs." "ENR Top-400 ranks Mortenson #3 in solar." Each fact ideally has: a subject, a predicate-ish relation, an object, a source pointer back to the episode it was distilled from, a confidence, and bi-temporal columns.

This is the layer most often visualized as a knowledge graph; in practice it's usually stored as triples or short claims in a table with a vector index, *plus* an optional graph projection (Graphiti, A-Mem, LightRAG, GraphRAG-style) for edge-walk queries.

**How it's written.** Strictly through the extraction pipeline. Raw conversations and tool results are too noisy to dump into semantic memory directly; a model has to *abstract* them into a claim. The ADD/UPDATE/DELETE/NOOP classifier (section 4) runs against semantic memory specifically — this is where contradiction resolution lives.

**How it's read.** Hybrid retrieval with a temporal filter — at minimum `valid_until IS NULL`, often "as of `timestamp`" for historical queries. The agent's `recall` tool typically targets semantic memory by default; episodic search is a separate code path.

**Characteristic operations.** All four CRUD operations are real here. ADD for novel facts, UPDATE when a relation changes (Sunrun switched EPCs), DELETE when a fact is contradicted with no replacement, NOOP when re-extraction yields a known fact.

**Strong vs. weak.**
- Strong: facts are atomic ("Sunrun engaged Blattner for project X in 2023"), each carries provenance (episode ID), confidence, and bi-temporal columns. Conflict resolution is *judgment*-classified (small model decides UPDATE vs. ADD), not string-matched. The extraction prompt is structured (output a typed triple, not free text), so downstream code can index reliably.
- Weak: semantic memory is a pile of free-text "memories" with no structure. New extractions never UPDATE existing rows because there's no notion of *which* prior fact this contradicts — every extraction becomes an ADD. Over months, the same fact is stored 20 times in slightly different phrasings, retrieval scores get noisy, and contradictions accumulate silently.

### 2.4 Procedural memory

**What it stores.** Learned *how-to*: workflows that worked, tool sequences that produced results, prompt patterns that the agent (or its operators) found effective, domain heuristics ("for Texas projects, always check ERCOT interconnection queue first"). This is the layer most agentic-RAG systems implement last and most thinly.

The unit is usually a *recipe*: a short, named, parameterized procedure with a trigger condition. Sometimes stored as structured JSON, sometimes as a markdown skill file that the agent's harness loads when the trigger matches.

**How it's written.** Three patterns in the wild:
- *Operator-authored* — humans write recipes into a `skills/` directory or a `procedures` table. Most production systems start (and often stay) here.
- *Self-authored* — the agent, after a successful multi-step task, summarizes "the procedure I just used" and writes it. Requires a metacognitive prompt; most systems don't do this reliably.
- *Distilled from episodes* — a background job clusters successful episodes and synthesizes the common procedure. Same shape as gbrain's facts→takes consolidation, but targeting workflows instead of facts.

**How it's read.** Triggered, not searched. A procedural memory's value is that the *system* finds the relevant recipe before the agent has to ask. Retrieval is typically by trigger condition (entity type, intent classification, task category), not by free-text similarity. When semantic-similarity retrieval is used at all, it's against the procedure's trigger description, not its body.

**Characteristic operations.** ADD for new recipes. UPDATE when a recipe is refined. DELETE when a procedure becomes obsolete. Procedural memory tolerates explicit human curation more than the other layers — it's the layer where "the agent wrote this itself and we kept it" is the exception, not the rule.

**Strong vs. weak.**
- Strong: procedures are named, parameterized, and *trigger-routed* — the system injects the relevant ones before the agent has to think about them. The agent can read them at runtime but doesn't have to remember to.
- Weak: procedural memory is "system prompt instructions" wearing a different hat — it's just a static prompt file, not retrieved or updated, not distinguishable from a hardcoded instruction.

---

## 3. Hybrid retrieval

The single most repeated finding across agentic-RAG implementations is that **no individual retrieval signal is sufficient** — and that the failure modes of each signal are *complementary*, not overlapping. Hybrid retrieval is the standard answer.

### 3.1 The three signals

**BM25 (lexical, sparse).** A classic TF-IDF variant. Scores by term overlap, with frequency normalization. Implementations: Postgres `tsvector` + GIN, OpenSearch/Elasticsearch, `rank_bm25` in-process for small corpora. Cheap to compute, no model needed, deterministic.

What it captures that vector search misses:
- Exact identifiers ("EPC-2023-0471", entity IDs, error codes, names with unusual spellings).
- Rare technical terms (the embedding model has averaged them away).
- Negation patterns ("not found", "rejected") that change meaning entirely but barely move embeddings.

**Dense vectors (semantic).** Each memory and the query are embedded into a fixed-dimensional space; ANN search returns the K nearest neighbors. Implementations: pgvector, Pinecone, Weaviate, Qdrant, in-process FAISS. Embedding model is usually `text-embedding-3-small` / `bge-small` / similar 384–1536-dim model.

What it captures that BM25 misses:
- Paraphrase ("solar contractor" vs. "PV installer" vs. "EPC firm").
- Cross-language and across-domain synonymy.
- Conceptual proximity when no words overlap ("the user is frustrated" matching a turn full of "this is broken").

**Cross-encoder reranker.** A small transformer that takes (query, candidate) pairs *together* and outputs a relevance score. Implementations: `bge-reranker-base`, Cohere's rerank API, Voyage's rerank, smaller `ms-marco-MiniLM` checkpoints. 10–100× more expensive than vector search per pair, so it runs on a small candidate set (typically top-50 from the merge step) and outputs top-5 to top-10.

What it captures that the other two miss:
- *Joint* interpretation of query and candidate. BM25 and dense vectors both score in isolation — they assume the candidate text "looks like" the query text. Cross-encoders read both together, so they can identify candidates that *answer* the query rather than merely *resemble* it.
- Hard negatives — candidates that share vocabulary with the query but are about the wrong subject (the classic "Apple the company vs. Apple the fruit" case).

### 3.2 How the three compose

The canonical pipeline runs all three in a fixed order:

```
query
  │
  ├──► BM25 top-K  ──┐
  │                  ├──► merge → cross-encoder rerank → top-N
  └──► vector top-K ─┘
       (cosine or dot-product on ANN)
```

K is typically 20–50 on each side; N is 5–10 after rerank. The merge step is where the literature has converged but with two competing formulas:

**Reciprocal Rank Fusion (RRF):**

```
score(doc) = Σ over retrievers  1 / (k + rank_in_retriever(doc))
```

with `k` typically 60. RRF doesn't need score calibration between retrievers — it only looks at rank position. This is the most common merge today because it Just Works without tuning, even when BM25 returns scores in a totally different range than cosine similarity.

**Weighted-sum (convex combination):**

```
score(doc) = α · normalize(bm25_score) + (1−α) · normalize(vector_score)
```

with α often 0.3–0.5 in favor of vectors. Requires per-corpus calibration. Used when both retrievers' scores can be reliably normalized (typically min-max within the candidate set).

After merge, the cross-encoder rerank is the closing step. Many implementations *also* apply post-rerank filters here: bi-temporal (`valid_until IS NULL`), scope (project vs. global), confidence threshold, recency decay. The rerank score is preserved through these filters so the final top-N is still relevance-ordered.

### 3.3 Failure modes when one signal is missing

These are the empirical "you'll notice this is broken" signatures:

| Missing signal | Symptom |
|---|---|
| **No BM25 (vector-only)** | Queries with specific IDs, error codes, or exact names return semantically-similar-but-wrong results. "What did we find about entity abc-123?" returns memories about other entities that *talk about* "entity" and "123." User experience: "why is it ignoring the literal thing I asked?" |
| **No vectors (BM25-only)** | Queries that paraphrase what's in memory return nothing. User asks "did we try the regulatory angle for Sunrun?" — the stored memory says "checked FERC and state PUC filings" — zero overlap, zero results. User experience: "it doesn't remember anything I didn't say verbatim." |
| **No reranker** | Top-K is full of *plausibly-related* but off-topic candidates. The agent's `recall` returns 10 memories, 7 of them about adjacent entities or wrong time periods. The agent either gets confused or wastes a turn re-querying with refined terms. User experience: latency and hallucinated cross-references. |

The "all three" architecture isn't dogma — there are scales (very small corpora) where any single signal suffices. But once an agent has been running for weeks, the failure modes show up. The reranker in particular is the difference between memory that feels reliable and memory that feels guess-y.

---

## 4. Auto-extraction pipeline: ADD / UPDATE / DELETE / NOOP

After each turn (or session, depending on cadence), the system has to decide what — if anything — in the conversation is worth promoting from working/episodic memory into semantic memory. This is the auto-extraction pipeline. The defining feature of the agentic-RAG version is that extracted candidate facts are *compared against existing memory* before being written, and the comparison resolves into one of four operations.

### 4.1 The operations

- **ADD** — no semantically near neighbor exists. Insert a new fact row.
- **UPDATE** — a neighbor exists with the same subject+relation but a different object (e.g., we knew "Sunrun used Blattner"; new fact says "Sunrun uses Mortenson"). Insert the new row; mark the old row's `valid_until` to the new fact's `valid_from`; link them via `supersedes` / `superseded_by`.
- **DELETE** — a prior fact is now contradicted with no replacement (e.g., user says "actually we never confirmed that Sunrun used Blattner"). Soft-expire the old row (`valid_until` = now, no replacement).
- **NOOP** — a near-identical fact already exists. Do nothing. Optionally bump a `last_confirmed_at` column on the existing row.

### 4.2 The standard pipeline

```
candidate fact (from extractor)
   │
   ▼
embed → ANN top-K neighbors in semantic memory  (typical K = 5–10)
   │
   ▼
classifier prompt: "given this new fact and these existing facts,
                    output one of {ADD, UPDATE <id>, DELETE <id>, NOOP <id>}"
   │
   ▼
write path:
   ADD     → INSERT new row, valid_from = now, valid_until = NULL
   UPDATE  → INSERT new row; UPDATE old row SET valid_until = now, superseded_by = new.id
   DELETE  → UPDATE old row SET valid_until = now
   NOOP    → UPDATE existing row SET last_confirmed_at = now (optional)
```

The classifier is almost always a small/cheap model (Haiku-class, GPT-4o-mini-class, Llama-3-8B-class). Two reasons: (1) it runs on every extracted candidate, so cost adds up; (2) the task is bounded enough that a small model can do it reliably given a structured prompt. The extractor that *produces* the candidate fact upstream is sometimes the same model, sometimes one tier larger.

### 4.3 Where this is identical to gbrain, and where it diverges

gbrain (per `research/2026-05-17-gbrain-memory-architecture-findings.md`, section "ADD / UPDATE / DELETE / NOOP classification") uses literally the same four-operation taxonomy. Both systems were converging on the same answer to the same problem: *how do you write to memory in a way that survives contradiction over months without bloating into a forest of redundant rows?*

**Identical:**

- Four operations, same semantics.
- Bi-temporal columns underneath, with UPDATE materialized as "insert new + supersede old" rather than mutating in place. Soft-expire on DELETE.
- The classification is treated as *judgment* — neither system tries to do this with rule-based heuristics. A small model is the right tool because the task is "are these two facts semantically the same claim?", which is exactly what LLMs are good at.
- The classifier runs against a *retrieved neighborhood* of candidate matches, not the whole memory. Retrieval gates the comparison.

**Divergent:**

- **Trigger.** gbrain has *two write tracks*: Track A (deterministic regex over structured tool output, sync hook) and Track B (small-model "worth remembering" judge on conversational turns, async via the `minion_jobs` queue). The classifier sits at the end of Track B. Canonical agentic RAG typically has only one track — an extraction pass on every turn or on a fixed cadence — and treats deterministic-regex extraction as an optional optimization rather than a separate first-class path. The agentic-RAG framing assumes the model judges everything; gbrain explicitly routes deterministic work away from the model.
- **Async vs. sync.** gbrain runs the entire write path asynchronously through `minion_jobs` with `FOR UPDATE SKIP LOCKED` worker semantics. Agentic-RAG implementations vary: Mem0 has a fire-and-forget background extractor, LangMem runs in-process post-turn, Letta runs it in a dedicated worker. The agentic-RAG consensus doesn't *require* a job queue — it requires that the extraction step doesn't block the user-facing turn. Several implementations achieve this with a sync post-turn hook that simply runs after the response is streamed.
- **Granularity of the fact unit.** gbrain's Track A extracts structured edges (`developer used_epc in_state`) — narrow domain triples. Agentic-RAG implementations more often extract free-form claims and let the embedding handle semantic equivalence. Both work; the structured version is harder to retrieve flexibly but easier to validate, while the free-form version is easier to write but harder to deduplicate cleanly.
- **What kicks off classification.** In gbrain, the small-model judge first decides "worth remembering at all?" — many turns produce no candidate. In agentic-RAG canonical form, an *extractor* tries to produce zero-or-more facts per turn, and NOOP is the equivalent of "nothing worth keeping." Mathematically the same outcome; operationally, gbrain's gate-then-extract uses fewer LLM calls when most turns are noise, while agentic RAG's extract-then-classify produces cleaner observability (you can always count extracted-but-NOOP'd candidates).

The convergence is the headline. Two independently-designed systems landed on the same four-operation taxonomy because the underlying problem is the same: memory needs CRUD with contradiction handling, and the C/U/D decisions are judgments.

---

## 5. Compaction → LTM promotion

Compaction is the operation that runs when working memory exceeds a budget. The agentic-RAG version of compaction has one feature that distinguishes it from naive summarization: **the act of compacting is also the act of writing to long-term memory.** A turn that gets compacted has its durable content extracted into episodic and/or semantic memory *first*, and only then is replaced by a short summary in the working context.

### 5.1 Naive summarization (the contrast)

The chat-app pattern most people have seen:

```
when context > N tokens:
    summary = LLM("summarize this transcript")
    new_context = [system_prompt, summary, last K messages]
```

Two failure modes:
- **Compounding loss.** Each compaction summarizes the previous summary. Information decays geometrically. After three compactions, you're summarizing summaries of summaries.
- **No durable trace.** Anything that falls out of the summary is gone. The system has no second chance to recover it.

Naive summarization treats memory as a sliding window. It's fine for short tasks; it's catastrophic for long-running agents.

### 5.2 The agentic-RAG compaction step

The replacement, run when working memory exceeds budget:

```
1. Identify the segment to compact (everything older than the preserve-recent window).
2. Run the auto-extraction pipeline (section 4) over that segment:
     - extract candidate facts → ADD/UPDATE/DELETE/NOOP into semantic memory
     - write one or more episodic rows summarizing what happened in the segment
3. Generate a short working-context summary that references the just-promoted memory
   by ID rather than restating it.
4. Replace the segment with [continuation preamble + summary + recent K verbatim].
```

The crucial difference is step 2. Before the working context drops the older turns, those turns have *already had their durable content promoted into LTM*. The summary in the working context is a pointer, not a lossy copy — the agent can `recall` against semantic memory to retrieve the original detail at any point.

Several real implementations:

- **LangGraph + LangMem.** `summarize_messages` calls into the memory store as a side effect; a `SummarizationNode` produces both the in-context summary and a set of extracted facts written through the store.
- **Mem0's procedural memory consolidation.** When the buffer fills, Mem0 runs `extract` over the buffered messages, classifies each candidate against existing memory, then emits a compressed summary that lists what was learned.
- **Letta/MemGPT's archival memory paging.** When core memory fills, the "evicted" content is paged out to archival memory (a vector store), not deleted. The summary in core memory points at the archival store.
- **A-Mem / agentic-memory papers.** Same pattern formalized: a "memory note" is generated per compaction event, embedded, and stored alongside the summary that goes into context.

### 5.3 What "promotion" means concretely

If a 20-turn segment is being compacted:

- The extractor walks each turn and emits zero-or-more candidate facts. Out of 20 turns, maybe 6 produce candidates and 14 are NOOPs.
- The 6 candidates run through ADD/UPDATE/DELETE/NOOP; perhaps 4 are ADDs into semantic memory, 1 is an UPDATE (supersedes an older fact), 1 is a NOOP (already known).
- One or two episodic rows are written summarizing the *narrative* of the segment ("during turns 12–32 the agent researched Sunrun's Texas portfolio and concluded X with confidence Y").
- The working-context replacement is a short paragraph that mentions "see semantic memory rows {ids…} for the durable findings; see episodic row {id} for the session narrative." Or, in implementations that don't expose IDs in-prompt, just a short summary the agent can re-query.

The summary that ends up in working context is therefore *recoverable* — at any future point, the agent can `recall` to get back what was compacted. Naive summarization loses information; agentic-RAG compaction relocates it.

### 5.4 Why this is load-bearing

The compaction-as-promotion step is the only thing that makes the four-layer split *work as a system*. Without it, working memory and LTM are two separate stores that don't interact, and durable facts can only enter LTM through explicit `remember`-style tool calls — which the agent forgets to make. With it, every compaction event is a chance for the system to write what the agent didn't think to write itself.

---

## 6. How this compares to solar-gen's existing four-layer implementation

solar-gen already has all four cognitive layers in some form. Fisher's intuition — "the shape is right, the quality is behind the standard" — checks out. Layer by layer:

### 6.1 Working memory

**Where it lives in code:**
- The message list inside `agent/src/runtime/agent_runtime.py` `AgentRuntime.run_turn` (lines 69–236). This is the actual live conversation buffer.
- `agent/src/tools/manage_todo.py` (171 lines) — agent-managed todo list, persisted to the `research_scratch` table by session.
- `agent/src/tools/research_scratchpad.py` — keyed JSON scratchpad, also on `research_scratch`.
- `agent/src/tools/think.py` — recorded-in-context-only reasoning blocks, no DB.
- `agent/src/hooks/inject_context.py` (lines 7–18) — auto-injects `_conversation_id` and `session_id` into tool inputs so working-memory tools can find their row.
- `supabase/migrations/013_create_research_scratch.sql` — the table.

**Assessment.** Closest to consensus. The structured-scratchpad pattern (keyed JSON, persisted by `session_id`, recoverable across compaction) and a separate structured todo list both match what strong agentic-RAG implementations do. The `think` tool is the standard Anthropic reasoning-pause pattern. The major gap is that there's no first-class "session working state" injection — the spec at `docs/superpowers/specs/2026-04-06-agent-context-management-design.md` describes a hot/warm/on-demand tiered SWS block intended to be prepended to every turn, but no migration 028 was ever created (latest migration is 030, and a quick search finds no `build_session_state_block` anywhere in `agent/src/`). The design was sketched and not implemented. So working memory today is: live messages + agent-driven scratchpad/todo, but no DB-authoritative state injection. That puts us at the "structured working memory exists" tier but not at the "system actively manages what the agent sees each turn" tier.

### 6.2 Episodic memory

**Where it lives in code:**
- `research_attempts` table — recorded via `process_discovery_into_kb` in `agent/src/knowledge_base.py` lines 277–331. Each row is a research session for a project with `outcome`, `searches_performed`, `reasoning`, `negative_evidence`. This is the closest thing we have to a true episodic row.
- `chat_messages` and `chat_events` tables (see `agent/src/db.py` lines 605–660 and migration `026_chat_events.sql`) — the raw audit trail of conversation turns. Not retrievable by similarity; only by `conversation_id`.
- Compactor in `agent/src/runtime/compactor.py` produces a `<summary>` block that includes a per-message timeline — this is *inside-context* summarization, not a written-out episodic row.

**Assessment.** Weakest of the four layers. `research_attempts` is genuinely episodic in shape — typed columns, source attribution, outcome classification — but it's keyed to *projects*, not to *conversations* or *sessions* generally. A free-form chat about preferences or a session where the user explained their persona doesn't produce an episodic row anywhere. `chat_messages` exists but isn't indexed for retrieval (no embedding column, no `tsvector` for chat content as a unit). There is no hybrid retrieval path that would surface "the time we researched McCarthy and the user rejected Brion." Compaction discards this content rather than promoting it. The shape exists for one narrow case (project research); the general episodic store does not.

### 6.3 Semantic memory

**Where it lives in code:**
- `agent_memory` table (`supabase/migrations/011_create_agent_memory.sql`): free-text `memory` column, `scope` of `project`/`global`, optional `memory_key` for upsert dedup, `importance` 1–10, `conversation_id`, `project_id`, and a generated `tsvector` column with a GIN index for full-text search. No vector column. No bi-temporal columns.
- `agent/src/db.py` `save_memory` (lines 495–524) and `search_memories` (lines 527–553). Search uses `ilike` substring matching, not the `tsv` index, ordered by `importance DESC, created_at DESC`. Hard limit on memory length: 2000 chars.
- The `entities` and `epc_engagements` tables (with `confidence`, `sources`, `state` columns) — these are the *structured* form of semantic memory. Updated by `promote_discovery_to_kb` (`agent/src/knowledge_base.py` lines 333–390) and read via `build_knowledge_context` (lines 126–269) which produces a markdown block injected before research.
- Agent-facing tools: `agent/src/tools/remember.py` (writes free-form memory) and `agent/src/tools/recall.py` (reads by keyword/scope/project_id with `limit`).
- `entities.profile` text field, rebuilt lazily by `rebuild_profile_if_stale` (`knowledge_base.py` lines 548–668) from joined engagements + research attempts — this is a kind of materialized semantic view.

**Assessment.** Bifurcated. The *structured* semantic store (`entities` + `epc_engagements`) is strong: typed, deduplicated via upsert, confidence-tracked, source-tracked, and read through a thoughtful aggregation (`build_knowledge_context` does loyalty stats, state-level rollups, and negative-evidence summaries). The *unstructured* semantic store (`agent_memory`) is weak relative to consensus:
- No vector embedding column despite the rest of the schema being prepared for it (the `tsvector` is there but unused by `search_memories`, which falls back to `ilike`).
- No reranker.
- No bi-temporal columns. The upsert on `(memory_key, scope)` overwrites; the prior row is gone.
- No ADD/UPDATE/DELETE/NOOP classification — `remember` is purely additive, and the only dedup is when the agent happens to remember to pass the same `memory_key`.
- `search_memories` is keyword-substring + importance-sort. No hybrid retrieval, no semantic similarity.

The structured side is roughly at consensus quality. The free-text side has the shape (a memory store, scoped, importance-weighted, tool-accessible) but none of the retrieval-or-write sophistication.

### 6.4 Procedural memory

**Where it lives in code:**
- `agent/src/prompts.py` — the static system prompt. Lines 274–323 contain a "Query Patterns" section (13 numbered if-then mappings) and a "Tool Selection Decision Tree" with hardcoded routing rules. This is procedural knowledge as static prompt.
- The tool registry in `agent/src/tools/__init__.py` — tool selection rules are encoded as tool descriptions, not as retrievable recipes.
- No `procedures` / `skills` / `recipes` table. No trigger-based procedure injection. The skills directory `agent/src/skills/` contains code modules (CSV processor, PDF extractor) — these are *capabilities*, not stored procedures.

**Assessment.** Effectively absent as a memory layer. What looks like procedural memory in the codebase is just the system prompt. The agent doesn't have a way to write down "this workflow worked, save it for next time," and the system doesn't have a way to surface "for this kind of query, here's the proven recipe" beyond what's hardcoded in the static prompt. The compaction step doesn't extract procedures; the auto-extraction pipeline doesn't have a procedural branch. This is the layer farthest from consensus.

### 6.5 Summary of where each layer sits

| Layer | Solar-gen artifact | Distance from consensus |
|---|---|---|
| Working | structured scratchpad + todo + think; no SWS injection | Closest. Missing the always-injected DB-authoritative state block. |
| Episodic | `research_attempts` (project-only); no general session episodes; no embedded retrieval | Mid-distance for the project case, absent for the general case. |
| Semantic (structured) | `entities` + `epc_engagements` + `build_knowledge_context` | Close to consensus quality for the domain it covers. Missing bi-temporal columns. |
| Semantic (free-text `agent_memory`) | scoped store + `remember`/`recall`; keyword search; no embeddings; no bi-temporal; no UPDATE/DELETE classification | Significantly behind. Has the shape, not the substance. |
| Procedural | static system prompt only | Furthest. Layer exists in name only. |

The two layers most plausibly worth investing in based on this gap analysis (without making implementation recommendations) are the free-text semantic store and the general-purpose episodic store — both because they're behind the consensus and because they're the layers that most directly affect "does the agent remember the user across sessions."

---

## 7. Load-bearing vs. incidental design choices

What the agentic-RAG design genuinely depends on, vs. what could vary without breaking it:

### 7.1 Load-bearing

- **The four-layer split.** Conflating episodic and semantic ruins both. Episodes need recency-weighted retrieval over narratives; semantic facts need contradiction-resolved retrieval over claims. A single "memories" table makes both worse.
- **Hybrid retrieval.** At any non-toy scale, removing BM25 *or* dense vectors *or* the reranker produces a distinct, visible failure mode (section 3.3). You can't pick two and expect the third's coverage to be optional.
- **Bi-temporal columns on the fact layer.** Without `valid_from`/`valid_until`, UPDATE has to be destructive, and "what did we believe last month?" is unanswerable. This is the structural prerequisite for the ADD/UPDATE/DELETE classifier to be safe.
- **ADD/UPDATE/DELETE/NOOP as a *classifier against retrieved neighbors*.** The combination of "retrieve first, then classify" is what makes the write side coherent over time. Drop either half and you regress to either append-everything (no UPDATE) or destructive-overwrite (no audit).
- **Compaction-as-promotion.** This is the seam between working memory and LTM. Without it, the layers don't actually compose; you have a context window and a vector store sitting next to each other.
- **The agent has memory tools as first-class actions.** `recall` / `add_memory` / `forget` in the tool surface. If memory is only system-injected, the agent can't refine queries mid-turn, can't write things it discovers, and the system has to guess what to inject.

### 7.2 Incidental — could vary without breaking the design

- **Choice of vector store.** pgvector, Pinecone, Qdrant, Weaviate, FAISS-in-process. All work. The choice changes ops cost and scaling characteristics, not the architecture.
- **Choice of reranker.** Cohere, Voyage, `bge-reranker-base`, `ms-marco-MiniLM`. Quality varies; presence-vs-absence is load-bearing, brand isn't.
- **RRF vs. weighted-sum merge.** Both work. RRF needs less tuning; weighted-sum can be tuned higher when you do.
- **Whether procedural memory is operator-authored or self-authored.** Most production systems start operator-authored and stay there. Self-authoring is a nice-to-have, not a requirement of the architecture.
- **Cadence of the extraction pipeline (per-turn vs. per-session vs. nightly).** Per-turn produces fresher memory and higher LLM cost; nightly is cheaper and less responsive. The architecture works at any cadence.
- **Sync post-turn hook vs. async job queue.** The constraint is "don't block the user-facing response." Either implementation satisfies it. gbrain went async; LangMem can run sync.
- **Whether the semantic store is stored as triples or as free-text claims.** Both retrieve fine with hybrid search; triples are stricter, free-text is more flexible. Choice depends on the domain's structurability.
- **Embedding dimension and model.** 384-dim vs. 1536-dim, OpenAI vs. open-source. Affects retrieval quality at the margins but not the architecture.
- **Exposing memory IDs in-prompt to the agent.** Some systems do (so the agent can reference specific memories); some don't (so the agent treats memory as opaque). Both work.

---

## 8. Plain English

We looked at how the rest of the industry — Mem0, LangMem, Letta, Zep, and several recent papers — has converged on building memory for long-running AI agents. They've all landed on roughly the same shape, which is what people call "agentic RAG memory." Three points are worth understanding without any of the technical detail.

First, **there are four kinds of memory and they each need to be stored differently.** *Working memory* is the live conversation and the agent's scratch notes — it's in the chat window and gets thrown away when the chat ends. *Episodic memory* is "what happened in past sessions" — like a journal entry the agent wrote about its own work. *Semantic memory* is "what's true in the world" — durable facts like "Sunrun used Blattner for their 2023 Texas projects." *Procedural memory* is "what worked last time" — recipes for how to handle recurring kinds of work. Most weak systems collapse all four into a single pile of "memories"; strong systems keep them separate because each needs different storage, different write rules, and different retrieval.

Second, **good memory search uses three signals at once.** Pure keyword search (the old-fashioned kind) misses paraphrases — if the user asks about "the contractor we found" and the memory says "the EPC we identified," keyword search returns nothing. Pure semantic search (the modern "embedding" kind) misses exact IDs, names, and codes — it returns vaguely-related but wrong results. So the consensus is to do both, merge the results, and then send the top candidates through a small specialized model called a reranker that re-scores them based on whether they actually answer the question. Skipping any one of the three signals produces a specific kind of failure that's easy to spot once you know what to look for.

Third — and this is the part Fisher's intuition correctly flagged — **we have all four memory layers in solar-gen already, but most of them are behind the standard.** Our working memory (scratchpad, todo list) is in solid shape. Our structured semantic memory (the `entities` and `epc_engagements` tables, with the rich knowledge-base context builder) is roughly at the industry standard for the domain it covers. But our free-text memory store (`agent_memory`, where `remember` and `recall` write) is missing the modern retrieval stack — no embeddings, no reranker, no contradiction-handling — and is essentially doing 2018-style keyword substring search. Our episodic memory only really exists for one narrow case (project research attempts) and is missing for general conversations. And our procedural memory is effectively just the system prompt — there's no mechanism for the agent to learn or for the system to file away "this workflow worked, use it next time." The shape of what we have is right. The quality of the individual layers ranges from competitive to significantly behind, and the variance is what gives us a clear picture of where the gap actually is.
