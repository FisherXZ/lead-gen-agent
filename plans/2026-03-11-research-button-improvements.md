# Research Button & Discovery Flow — Improvement Plan

**Date:** 2026-03-11
**Status:** Proposed (awaiting Fisher's approval before implementation)

---

## The Core Problem (with real evidence)

In a real test session, the chat agent found **McCarthy as EPC for two Lightsource bp Texas projects** by searching McCarthy's portfolio page — something the batch research function completely missed. The chat agent outperformed the research function because:

1. It could follow leads iteratively (search → find Lightsource bp → check McCarthy portfolio → confirm)
2. It searched EPC company websites directly (the research function didn't)
3. A human could guide it ("critically look into the sources", "run web search to confirm")
4. It had access to more tools (KB queries, project search, discoveries)

**This reveals a fundamental architecture gap:** the research function is a fire-and-forget black box, while the chat agent is interactive, guidable, and more thorough. We should bring the chat agent's strengths into the research flow, and make results a living conversation instead of a binary accept/reject.

---

## Current Flow

```
ResearchButton.tsx → POST /api/discover → run_research() → Claude agent loop (25 max iterations)
  → web_search / web_search_broad / fetch_page → report_findings → parse + confidence upgrade → store_discovery()
```

---

## Part 1: Research Function Problems (existing)

### A. No Structured Research Phases — Agent Flies Blind

The agent runs in a single unstructured loop: search → get results → search more → eventually report. There is no mechanism to shift the agent from "discovery" mode to "verification" mode to "reporting" mode.

A TODO in `research.py:74-80` already acknowledges this:
```python
# TODO: Add structural reflect step every 5 iterations.
```

**Impact:** Agent can burn 15+ iterations on dead-end searches or get tunnel vision on one weak lead without pausing to evaluate whether it's making progress.

**Proposed fix:** Inject structured reflection messages at iteration boundaries:
- **Iteration 5:** "Have your last 3 searches surfaced any new EPC-specific information? If not, call report_findings now."
- **Iteration 10:** "You've used 10 of 25 iterations. Shift to verification — confirm scale, specificity, and role for any candidate."
- **Iteration 15:** "You've used 15 of 25 iterations. Call report_findings within the next 3 iterations."

---

### B. No Progress Feedback to User

The research button shows "Researching..." spinner and nothing else. A research call takes 30-90 seconds. The user has no idea what's happening.

The batch flow (`/api/discover/batch`) already streams SSE progress updates — single-project research gets nothing.

**Proposed fix:** Convert `/api/discover` to SSE streaming (or add a polling endpoint) that emits events like:
- `{ type: "searching", query: "NextEra solar TX EPC contractor", iteration: 1 }`
- `{ type: "reading", url: "https://...", iteration: 3 }`
- `{ type: "verifying", candidate: "McCarthy", iteration: 6 }`
- `{ type: "complete", discovery: {...} }`

Update `ResearchButton.tsx` to show these phases to the user.

---

### C. 409 Conflict Is a Dead End

If a project already has an accepted discovery, the API returns 409. But `ResearchButton.tsx` doesn't handle 409 — it falls through to generic "Request failed (409)". The user doesn't know why or what to do.

**Proposed fix:**
- Frontend: catch 409 and show "This project already has an accepted EPC. Reject the existing discovery first to re-research."
- Or: add a `force` parameter to `/api/discover` that auto-rejects the old discovery and starts fresh.

---

### D. Tool Set Too Limited for Standalone Research

The research runner only gets 4 tools: `web_search`, `web_search_broad`, `fetch_page`, `report_findings`.

It does NOT have access to:
- `query_knowledge_base` — can't check what's known about the developer/EPC mid-research
- `search_projects` — can't look at related projects by the same developer to find pattern evidence

Knowledge context is passed as a static text blob in the initial message. If the agent discovers a new lead mid-research, it can't query the KB for cross-references.

**Proposed fix:** Add `query_knowledge_base` to `RESEARCH_TOOLS` list in `research.py:31`:
```python
RESEARCH_TOOLS = ["web_search", "web_search_broad", "fetch_page", "query_knowledge_base", "report_findings"]
```

---

### E. `fetch_page` Keyword Filter Misses Relevant Content

`fetch_page.py:16-26` uses a hardcoded `_EPC_KEYWORDS` set to extract "relevant" paragraphs from long articles. If the page mentions an EPC by a name not in this set (e.g., "Wanzek", "Ryan Company", "Sundt"), those paragraphs get dropped. The agent then only sees a truncated head of the article and misses the key information.

**Proposed fix:** Pass the candidate EPC name (if known) and the project developer/name into `fetch_page` as optional context, and add those terms to the keyword filter dynamically. Or: always include the paragraph *before and after* any keyword-matching paragraph for context.

---

### F. Tavily Search Is Synchronous in Async Context

`web_search.py:67` calls `TavilyClient.search()` which is synchronous, blocking the event loop. Not critical for single research but bottlenecks batch.

**Proposed fix:** Wrap in `asyncio.to_thread()` or switch to Tavily's async client if available.

---

### G. No Cost Visibility

Token usage is stored in `epc_discoveries.tokens_used` but never shown to the user. With Opus pricing, a single research run can cost $0.50-2.00.

**Proposed fix:** Show token count and estimated cost in the discovery result card. Add a running total to the review queue page.

---

### H. Error Recovery Is All-or-Nothing

If 3+ consecutive tools error (`check_tool_health`), the agent gets a generic "tools are failing, bail out" message. But if only Tavily is down and Brave works, there's no nudge to switch tools — just a blanket warning.

**Proposed fix:** Make health checking per-tool. If `web_search` fails 2x, inject: "Tavily is down. Use web_search_broad (Brave) instead." If `fetch_page` times out on a URL, note the domain and suggest skipping similar URLs.

---

### I. Compaction Too Aggressive for Research

`compact_messages` is called every iteration with `max_context_chars=60_000` and `keep_recent_turns=4`. By iteration 8-10 of a 15-iteration run, the agent loses its early search results. This causes:
- Re-searching queries already tried
- Losing track of promising leads from early iterations
- Losing the original project details and knowledge context

**Proposed fix:**
- Increase `keep_recent_turns` to 6 for research (already the module default, but `research.py` overrides to 4)
- Pin the first message (project details + KB context) so it never gets compacted
- Keep a running "research state" summary that gets prepended after compaction: candidate EPC, sources found so far, searches already performed

---

## Priority Order

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 1 | A. Structured reflection phases | High — directly improves result quality | Small |
| 2 | B. Progress streaming to user | High — fixes "is it broken?" UX | Medium |
| 3 | D. Add KB query to research tools | Medium — enables cross-referencing | Small |
| 4 | C. Handle 409 in frontend | Medium — unblocks re-research | Small |
| 5 | I. Fix compaction for research | Medium — prevents context loss | Small |
| 6 | E. Dynamic keyword filter | Medium — catches more EPC mentions | Small |
| 7 | H. Per-tool error recovery | Low-Medium — smarter failover | Medium |
| 8 | G. Cost visibility | Low — nice to have | Small |
| 9 | F. Async Tavily | Low — only matters for batch | Small |

---

---

## Part 2: Architecture Redesign — Chat-First Discovery

These are new ideas inspired by the real-world thread where the chat agent outperformed batch research.

### J. Research Button Should Open a Chat, Not a Black Box

**The problem:** The research button fires a headless agent and returns a result. The user can only accept or reject. If the result is wrong or incomplete, the only option is to re-run from scratch.

**The insight:** The chat agent already does research *better* because the user can guide it, ask follow-ups, and course-correct. So why not make the research button *start a chat conversation* instead of running a headless agent?

**Proposed flow:**
1. User clicks "Research EPC" on a project
2. Instead of a black-box API call, it opens a chat panel pre-loaded with the project context
3. The agent auto-starts research (same as today's headless flow)
4. But the user can *watch* the research happen in real-time (search queries, pages read, reasoning)
5. When the agent reports findings, the user can:
   - Ask follow-up questions ("Did you check McCarthy's portfolio?")
   - Challenge the result ("That's the developer, not the EPC")
   - Ask the agent to dig deeper ("Search for [specific company]")
   - Accept the result when satisfied
6. The discovery record links to the conversation for audit trail

**Why this is better:** Combines the automation of the research function with the interactivity of the chat agent. The user doesn't have to choose between "push button and hope" vs "manually drive the agent."

---

### K. Agent Should Be Able to Edit Existing Discoveries

**The problem:** Right now, discoveries are immutable once stored. If the chat agent finds better information (like the McCarthy finding), it has no way to update the existing discovery. It can only create a new one (which rejects the old pending one).

**Proposed fix:** Add an `update_discovery` tool to the chat agent:
```python
update_discovery(discovery_id, updates={
    epc_contractor: "McCarthy Building Companies",
    confidence: "confirmed",
    add_sources: [{...new McCarthy source...}],
    reasoning: "Updated: Found McCarthy press release confirming EPC role"
})
```

This lets the agent *refine* results instead of replacing them. The audit trail shows what changed and why.

---

### L. Discovery Results Should Be a Conversation Thread, Not a Card

**The problem:** Currently, a discovery result is a static card: EPC name, confidence, sources, accept/reject buttons. There's no way to discuss it, ask questions, or request clarification.

**Proposed flow:**
- Each discovery has an associated conversation thread
- The review UI shows the discovery card PLUS a chat interface below it
- The user can ask: "Why did you pick this EPC?" / "What about [other company]?" / "This source link is dead, find another"
- The agent can respond with its reasoning and run additional searches
- When the user is satisfied, they accept from within the conversation

**Why this matters for Liav:** He said some results look incorrect. Right now his only option is reject and re-research. With this, he can say "this looks wrong because X" and the agent can investigate and self-correct.

---

### M. Research Function Search Strategy Is Too Shallow

**Evidence from the thread:** The batch research missed McCarthy for Lightsource bp projects. The chat agent found it by:
1. Searching for "Lightsource bp Texas solar EPC"
2. Following a lead to McCarthy's website
3. Reading the McCarthy press release that explicitly named both projects

The research function's prompt includes a search strategy (`prompts.py:123-134`) but it's a suggestion, not enforced. The agent often does 3-4 generic searches and gives up.

**Proposed fix — Mandatory search phases:**

Phase 1: Direct search (what we do today)
- "[developer] [project name] EPC contractor"
- "[project name] solar construction contractor"

Phase 2: EPC portfolio sweep (what the chat agent did that research missed)
- For each of the top 10 EPCs: "site:[epc-domain] [developer]" or "site:[epc-domain] [state] solar"
- This is what found the McCarthy result

Phase 3: Developer-pattern search
- "[developer] EPC contractor solar" (across all their projects)
- Check if we already know this developer's preferred EPC from the KB

Phase 4: Regulatory/filing search
- "[project name] [state] public utility commission"
- "[project name] certificate of public convenience"

The agent should be *required* to attempt at least one search from Phase 2 before reporting "unknown." The current prompt says "If Tavily returns few results, try Brave" but doesn't require portfolio site searches.

---

### N. Batch Research Should Learn from Its Failures

**The problem:** When batch research runs 5 projects and 4 come back "unknown," there's no mechanism to learn from the one that succeeded. If project #3 found that a developer uses McCarthy, projects #4 and #5 by the same developer don't benefit from that knowledge.

**Proposed fix:** After each project completes in a batch:
1. Store any `related_findings` in a shared batch context
2. Pass accumulated findings to subsequent projects as additional context
3. If the agent discovers a developer→EPC pattern, inject it into remaining projects' prompts

This makes batch research smarter as it progresses instead of treating each project as independent.

---

### O. "Verify" Button Alongside "Research" Button

**The problem:** For projects that already have a discovery, the only options are accept/reject/re-research. There's no lightweight "double-check this" action.

**Proposed fix:** Add a "Verify" button that:
1. Takes the existing discovery result
2. Runs a shorter verification-only agent (5 iterations max)
3. Specifically checks: Is the source still live? Are there newer sources? Has the EPC changed?
4. Returns a verification status: "confirmed," "still valid," "new evidence found," or "contradicted"

This is cheaper and faster than full re-research and directly addresses Liav's concern about result accuracy.

---

### P. Source Quality Dashboard

**The problem:** Liav asked how data is sourced and whether LinkedIn data is reliable. There's no aggregate view of source quality across all discoveries.

**Proposed fix:** A simple dashboard page showing:
- Total discoveries by confidence level
- Source breakdown by channel (press release vs. trade pub vs. LinkedIn vs. etc.)
- % of sources with real URLs vs. `search:` fallbacks
- Average source count per discovery
- Discoveries with only low-reliability sources (flagged for review)

---

## Updated Priority Order

| # | Issue | Impact | Effort | Category |
|---|-------|--------|--------|----------|
| 1 | J. Research button opens chat (not black box) | **Very High** — solves the core UX gap | Large | Architecture |
| 2 | M. Mandatory EPC portfolio sweep in search | **High** — directly fixes missed results (McCarthy case) | Small | Research quality |
| 3 | A. Structured reflection phases | High — improves result quality | Small | Research quality |
| 4 | K. Agent can edit existing discoveries | High — enables iterative refinement | Medium | Architecture |
| 5 | L. Discovery as conversation thread | High — enables discuss-then-accept flow | Medium | Architecture |
| 6 | B. Progress streaming to user | High — fixes "is it broken?" UX | Medium | UX |
| 7 | N. Batch research learns from successes | Medium-High — smarter batch runs | Medium | Research quality |
| 8 | D. Add KB query to research tools | Medium — enables cross-referencing | Small | Research quality |
| 9 | O. Lightweight "Verify" button | Medium — cheaper than full re-research | Medium | UX |
| 10 | C. Handle 409 in frontend | Medium — unblocks re-research | Small | UX |
| 11 | I. Fix compaction for research | Medium — prevents context loss | Small | Research quality |
| 12 | E. Dynamic keyword filter in fetch_page | Medium — catches more EPC mentions | Small | Research quality |
| 13 | P. Source quality dashboard | Medium — builds trust with stakeholders | Medium | Trust/transparency |
| 14 | H. Per-tool error recovery | Low-Medium — smarter failover | Medium | Reliability |
| 15 | G. Cost visibility | Low — nice to have | Small | Transparency |
| 16 | F. Async Tavily | Low — only matters for batch | Small | Performance |

---

## Suggested Implementation Phases

### Phase 1: Quick Wins (improve research quality now)
- M. Add mandatory EPC portfolio sweep to search strategy
- A. Add reflection checkpoints at iteration 5/10/15
- D. Add `query_knowledge_base` to research tools
- I. Fix compaction (pin first message, increase keep_recent_turns)

### Phase 2: Interactive Research (the big architectural shift)
- J. Research button opens a chat conversation with auto-start
- K. Agent can update/edit existing discoveries
- B. Progress streaming (now built into the chat UI naturally)

### Phase 3: Review & Trust
- L. Discovery conversation threads (discuss before accepting)
- O. Verify button for existing discoveries
- P. Source quality dashboard
- N. Batch learning from successes

---

## Plain English Summary

**What we learned:** When a human can guide the AI agent interactively (through chat), it finds better results than when the AI runs on its own (through the research button). The chat agent found McCarthy as the EPC for two Texas projects that the batch research completely missed — because a human said "check the sources critically" and the agent dug deeper.

**The big idea:** Stop treating research as a black box ("push button, get answer"). Instead, make it a conversation. The research button should open a chat where the user watches the agent work and can guide it. The result should be something you can discuss and refine, not just accept or reject.

**The quick wins:** Even before the big redesign, we can make the existing research function smarter by (1) requiring it to check EPC company portfolios (not just generic Google searches), (2) adding checkpoints where it pauses to evaluate progress, and (3) giving it access to our knowledge base so it doesn't ignore what we already know.

**Why this matters for Liav:** He said some results look incorrect and he wants to understand how data is sourced. The conversation-based approach lets him ask "why did you pick this EPC?" and get an answer, instead of just seeing a card he has to blindly trust or reject.
