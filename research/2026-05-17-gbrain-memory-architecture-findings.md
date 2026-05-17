# gbrain Memory Architecture — Findings & Decisions

**Date:** 2026-05-17
**Author:** Agent-memory redesign discovery (Fisher + Claude)
**Branch:** `claude/agent-memory-design-mUZ3T`
**Status:** Discovery notes — input to upcoming redesign plan. Not an implementation spec.

---

## Why this document exists

We're redesigning solar-gen's agent memory subsystem. To avoid reinventing patterns, we surveyed three reference systems:

1. **gbrain** — Anthropic's internal long-horizon agent memory (this document)
2. **Hermes** — bounded-markdown agent memory (next deep-dive, separate doc)
3. **Letta / MemGPT** — covered at a high level only; not pursued further

This doc captures what we learned from gbrain and which patterns we've decided to adopt, defer, or reject for solar-gen.

---

## What gbrain is (briefly)

gbrain is a long-horizon agent memory system that combines:

- A **bi-temporal Postgres store** for facts with full audit trail.
- An **async job queue** (`minion_jobs`) for memory-write side effects (embedding, classification, consolidation, expiry).
- A **routing principle**: every operation is classified as either deterministic (handled by code) or judgment (handled by a model), and routed accordingly.
- A **subagent synthesis pattern**: cheap Haiku verdicts gate expensive Sonnet synthesis calls.

We did not adopt gbrain wholesale. We extracted the patterns that fit our problem (durable EPC/developer relationship knowledge that drifts over months/years) and rejected the ones that need infra we don't have yet (a robust job queue).

---

## Key findings

### 1. Bi-temporal columns are the linchpin

Every fact-bearing row carries four time columns:

| Column | Meaning |
|---|---|
| `valid_from` | When the fact became true in the real world. |
| `valid_until` | When the fact stopped being true in the real world (NULL = still true). |
| `superseded_by` | Pointer to the row that replaced this one (NULL = current). |
| `expired_at` | When the row was soft-deleted in our system (NULL = live). |

**Why it matters for us:** developer→EPC relationships drift. "Sunrun used Blattner for the Texas portfolio" was true in 2023, may not be in 2026. A flat `epc = "Blattner"` field loses that history. Bi-temporal columns let us answer "who did Sunrun use in 2024?" and "who do they use now?" with the same row, no destructive overwrites.

**Audit-trail-via-soft-expire:** rather than `DELETE`ing rows, gbrain sets `expired_at = now()`. This gives a clean audit log without a separate history table. Updates work the same way: insert the new row, set `superseded_by` on the old one, set `expired_at` on the old one, leave `valid_until` to reflect real-world validity.

### 2. Two complementary write tracks

gbrain separates *how facts get into memory*:

**Track A — Deterministic regex/parse extractor (sync).**
After certain tool outputs (e.g., research reports), a deterministic extractor pulls structured edges out of the text: `(developer, used_epc, in_state)` triples and similar. No LLM call. Same input → same edges. Runs synchronously as a post-tool hook.

**Track B — Small-model "worth remembering" judge (async).**
After conversation turns, a Haiku-class judge looks at the turn and decides whether it contains durable insight worth persisting. Runs asynchronously via the job queue so it doesn't block the user. If the verdict is "yes," it enqueues a follow-up job to extract and write the memory.

The two tracks don't compete — they handle different inputs. Structured tool output → Track A. Free-form conversation → Track B.

### 3. ADD / UPDATE / DELETE / NOOP classification

When a candidate fact arrives, gbrain doesn't just append. It compares against existing memory and classifies the operation:

- **ADD** — no matching prior fact; insert.
- **UPDATE** — matching prior fact with different value; insert new row, mark old as superseded.
- **DELETE** — prior fact contradicted; soft-expire it without a replacement.
- **NOOP** — already known; do nothing.

This classification is judgment work (it requires comparing semantics, not strings), so it runs async with a small model.

### 4. Nightly consolidation: facts → takes

Raw facts accumulate. Periodically (nightly cron job), gbrain clusters related facts and synthesizes a "take" — a higher-level claim that summarizes the cluster. Example: ten observations of "developer X delayed project Y" become one take "developer X has a pattern of schedule slippage."

Clustering is deterministic (embedding similarity + thresholds). Picking the canonical claim is judgment (Sonnet subagent). The split lands on the routing principle line.

### 5. Routing principle: deterministic → code, judgment → model

This is the gbrain design rule that surprised us most:

> Every memory operation is classified upfront as either *deterministic* (same input always produces same output — handled by regex/SQL/embedding math) or *judgment* (requires taste, comparison, or interpretation — handled by an LLM). The two paths have different infrastructure: deterministic ops are sync hooks, judgment ops are async jobs on the `minion_jobs` queue.

This forces a discipline: when you propose a new memory feature, the first question is "is this deterministic or judgment?" If deterministic, you write code, not a prompt. Every LLM call costs money and adds nondeterminism; you should be able to justify it.

### 6. Subagent synthesis pattern (Haiku verdict → Sonnet worker)

For expensive operations (consolidation, classification on large fact clusters), gbrain uses a two-stage pattern:

- A cheap Haiku call decides *whether* to do the expensive work.
- Only if Haiku says "yes" does it spawn a Sonnet subagent to do it.

This keeps the cost ceiling predictable: at scale, the dominant cost is the Haiku gate, not the Sonnet worker.

### 7. Async job queue infrastructure

The judgment-side operations all run on a Postgres-backed job queue (`minion_jobs`) with:

- `FOR UPDATE SKIP LOCKED` for safe concurrent workers.
- Parent/child chains so a "judge" job can enqueue a "write" job atomically.
- Idempotency keys to dedupe retries.

We **do not** have this infra today. Building it is non-trivial. This is the main blocker to wholesale gbrain adoption.

---

## Decisions for solar-gen

### ✅ Adopted

| Pattern | Where it lands |
|---|---|
| Bi-temporal columns (`valid_from`, `valid_until`, `superseded_by`, `expired_at`) | `epc_engagements` **and** new `agent_memory` table |
| Audit-trail-via-soft-expire | Both tables above |
| Track A: deterministic regex extractor (sync hook) | Runs after `report_findings` and `related_leads` tool calls |
| Track B: small-model "worth remembering" judge (async) | Runs on conversation turn boundaries — needs job queue (see deferred) |
| ADD / UPDATE / DELETE / NOOP classification | For memory writes |
| Routing principle (deterministic vs judgment) | **Scoped to memory subsystem only** — see "rejected/deferred" below |

### ⏸ Deferred

| Pattern | Why deferred |
|---|---|
| Full `minion_jobs` async job queue | Track B (async judge) and nightly consolidation both need this. Building a robust job queue is its own project. For v1 we can run Track B as a sync post-turn hook with a short Haiku call (acceptable latency hit) and skip nightly consolidation entirely until we have queue infra. |
| Nightly consolidation (facts → takes) | Depends on job queue + meaningful fact volume. Revisit once we have 6+ months of accumulated memory. |
| Generalizing the routing principle beyond memory | We considered making it a project-wide design rule (covering research planning, contact discovery, EPC verification). Decided not yet — without a job queue, "deterministic → put on queue" has no queue to target. We'll let it extend organically as infra fills in. The `TODO.md` note about deprecating `notify_progress` is already an independent instance of this principle in action. |

### ❌ Rejected

Nothing outright rejected from gbrain so far. The deferred items are "yes, but later."

---

## Open questions (to resolve before writing the implementation plan)

1. **Where does conversation-turn memory live vs. EPC-relationship memory?** Likely two tables (`agent_memory` for free-form takes, `epc_engagements` for structured relationships) but the read path needs to query both transparently.
2. **What's the read path?** Vector search? Recency-weighted? Filter by `valid_until IS NULL`? Probably all three composed, but we haven't designed it yet.
3. **How does Track A's regex extractor handle ambiguous parses?** E.g., text says "Sunrun is reportedly evaluating Blattner" — is that an `engaged` edge or a `considering` edge? Probably needs a confidence column.
4. **Does the small-model judge in Track B run on every turn or only when a tool was called?** Per-turn is expensive; per-tool may miss insights from pure-chat turns.
5. **Cold start: how do we backfill the memory tables from existing `report_findings` rows?** One-time deterministic extraction pass over historical data.

These feed into the Hermes deep-dive and ultimately the implementation plan.

---

## What's next

1. **Hermes deep-dive** (next research doc). Hermes is much smaller scope than gbrain. Two patterns matter:
   - Pre-turn background prefetch with `<memory-context>` fences injected into the user message (KV-cache friendly, keeps history clean).
   - Bounded markdown store with hard char limits that forces the agent to self-consolidate when full.
2. **Composite design** combining gbrain's bi-temporal Postgres + Hermes's prefetch injection, scoped to what we can ship without a job queue.
3. **Implementation plan** under `plans/2026-05-XX-agent-memory-redesign.md` once Hermes is digested and the open questions above are answered.

---

## Plain English

We looked at how a much more sophisticated agent memory system (gbrain) works, and pulled out the ideas worth copying.

The most important idea is **time stamps on everything we remember**. Today, if our agent learns "Sunrun uses Blattner," it overwrites whatever it knew before. With gbrain's pattern, we never overwrite — we just mark the old fact as "this used to be true until last March" and add the new one. That gives us a full history for free, which matters because EPC relationships shift constantly in this industry.

The second idea is **two different ways to write memories**, used for different inputs:
- For structured research output, dumb regex code pulls out relationships — fast, cheap, predictable.
- For free-form chat, a small AI model decides if the conversation contained something worth remembering — slower but smarter.

The third idea is a **design discipline**: every time we add a memory feature, we ask "does this need an AI call, or could plain code do it?" If plain code works, we use plain code. AI calls cost money and are unpredictable — we should only spend them on tasks that genuinely need judgment.

We chose **not** to adopt gbrain's heavy background-job machinery yet, because building it is a whole project on its own, and our memory volume is still small enough that we can get away with simpler approaches.

Next, we dig into a smaller, simpler memory system called Hermes to see what *it* gets right, then combine the best of both into a concrete implementation plan.
