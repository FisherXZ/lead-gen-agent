# Quick Wins: Research Function Improvements

**Date:** 2026-03-11
**Status:** Approved — ready to implement

## Context

The batch research function misses results that the chat agent finds (e.g., McCarthy EPC for Lightsource bp projects). The research function runs headless with limited tools, a shallow search strategy, aggressive context compaction, and no ability to check in with the user when stuck.

Evidence: In a real test, the chat agent found McCarthy as EPC for two Lightsource bp Texas projects by searching McCarthy's portfolio site — the batch research completely missed this because it never checked EPC company websites.

## Agreed Changes

### 1. Add KB Query to Research Tools (Quick Win D)

**File:** `agent/src/research.py:31`

- Add `"query_knowledge_base"` to `RESEARCH_TOOLS` list
- One-line change, tool already exists
- Lets the research agent cross-reference developer/EPC relationships mid-research

### 2. Mandatory EPC Portfolio Sweep (Quick Win M)

**File:** `agent/src/prompts.py:123-155` (Search Strategy section)

- Rewrite search strategy into mandatory phases:
  - **Phase 1 — Direct search** (always do first): developer + project name + EPC
  - **Phase 2 — EPC portfolio sweep** (REQUIRED before reporting "unknown"): search at least 3 of the top 10 EPC company sites for the developer name
  - **Phase 3 — Broader coverage**: trade pubs, Brave fallback, regulatory filings
- Prompt-only enforcement (no code validation)
- This is the fix that would have caught the McCarthy result

### 3. Fix Compaction (Quick Win I)

**File:** `agent/src/research.py:201-205` — change params
**File:** `agent/src/compaction.py` — add `pin_first_message` parameter

- Bump `keep_recent_turns` from 4 → 6
- Bump `max_context_chars` from 60K → 80K
- Add `pin_first_message=True` param to `compact_messages` that skips index 0 during compaction
- ~5 lines of new logic in `compact_messages`
- Prevents the agent from losing track of project details and KB context during long research runs

### 4. Auto-Handoff to Chat When Stuck (Quick Win A)

**File:** `agent/src/research.py` — add reflection + handoff logic
**File:** `agent/src/main.py` — handle handoff in `/api/discover` response
**File:** `frontend/src/components/epc/ResearchButton.tsx` — detect handoff and show "Continue in chat"

- At iteration 5: inject reflection message ("are you making progress?")
- At iteration 10: inject stronger nudge ("shift to verification or report")
- Add `request_guidance` to research tools
- When the agent calls `request_guidance` during headless research: stop the loop, return a partial result with the agent's question, and signal the frontend to "continue in chat"
- Frontend detects `handoff_to_chat: true` in response and shows a "Continue in chat" link/button instead of an error

## Verification

1. Run existing tests: `cd agent && python -m pytest tests/`
2. Manual test: start agent server, click Research on a project, verify:
   - KB query tool appears in agent logs
   - Search queries include EPC portfolio site searches
   - First message (project details) survives compaction after 8+ iterations
   - If agent calls request_guidance, frontend shows "Continue in chat"

## Plain English

These four changes make the research button smarter without a full redesign. The agent gets access to our knowledge base while researching, is required to check EPC company websites before giving up, keeps its memory of the project throughout the run, and can hand off to a chat conversation if it gets stuck instead of spinning in circles. The biggest impact is the portfolio sweep — it directly fixes the class of miss where the answer was sitting on McCarthy's website but the agent never looked there.
