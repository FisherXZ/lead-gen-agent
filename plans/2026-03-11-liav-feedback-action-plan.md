# Liav Feedback Action Plan

**Date:** 2026-03-11
**Source:** Liav's testing feedback + patterns from the-hog competitive intelligence platform
**Goal:** Address all feedback items, improve reliability and trust, formalize next steps

---

## Context

Liav tested the application and provided feedback across five areas: research button failures, data accuracy concerns, data source transparency, agent chat potential, and business structure. This plan addresses each item with concrete technical work inspired by proven patterns from the-hog project.

---

## Phase 1: Critical Fixes (March 11–14)

### 1.1 Fix Research Button (P0)
**Problem:** Research button returns "research failed" or error when clicked.
**Actions:**
- [ ] Diagnose root cause — check API key configuration, tool execution errors, Tavily/Brave API availability
- [ ] Add structured error handling per tool (wrap each tool with try/catch, return `{ success: false, error_type, message }` instead of silent failures)
- [ ] Add error categorization: "api_unavailable" vs "no_results" vs "malformed_response" vs "timeout"
- [ ] Surface meaningful error messages in the UI (not just "research failed")
- [ ] Verify end-to-end: click Research → agent runs → result appears in panel

**Inspired by:** the-hog's `withToolTracking()` wrapper pattern — every tool call caught, categorized, and reported.

### 1.2 Surface Source URLs on All Research Results (P0)
**Problem:** Liav wants to verify data accuracy but results lack clickable source links.
**Actions:**
- [ ] Audit `report_findings` tool — confirm `EpcSource.url` field is being populated by the agent
- [ ] Update system prompt to explicitly require URLs on every source
- [ ] Verify `SourceCard` component renders clickable "View Source" links when URL is present
- [ ] Add fallback: if agent didn't capture URL, show the search query used so user can verify manually
- [ ] Test with 5 real projects — confirm every result has at least one clickable source

---

## Phase 2: Trust & Transparency (March 15–21)

### 2.1 Data Source Labeling
**Problem:** Liav sees LinkedIn-looking references and wants to know how data is obtained.
**Actions:**
- [ ] Add a "How We Source Data" tooltip/info panel accessible from research results
- [ ] Label each source with its channel type: "Web Search Result", "ISO Queue Filing", "News Article", "Trade Publication", "Company Press Release"
- [ ] Clarify LinkedIn data: we use Brave Search which indexes public web pages — not direct scraping or API access
- [ ] Downweight or flag LinkedIn-sourced snippets as lower reliability
- [ ] Add `source_method` field to EpcSource model: "brave_search" | "tavily_search" | "page_fetch" | "iso_filing"

### 2.2 Confidence Aggregation
**Problem:** Some results are incorrect; no way to distinguish strong vs weak findings.
**Actions:**
- [ ] Implement source-count-based confidence upgrade: 2+ independent sources → auto-upgrade confidence level
- [ ] Add negative evidence tracking: log "searched X, found nothing" as counter-evidence
- [ ] Show source count on confidence badge: "Likely (2 sources)" vs "Possible (1 source)"
- [ ] Add "Unverified" warning label on results with only 1 low-reliability source

### 2.3 Proposal-Based Review Flow
**Problem:** Incorrect data enters the system without review friction.
**Inspired by:** the-hog's proposal → review → accept/reject → commit pattern.
**Actions:**
- [ ] Research results land as "proposed" state (already have pending/accepted/rejected — enforce the flow)
- [ ] Add a "Review Queue" view: all pending discoveries, sortable by confidence
- [ ] Require explicit accept before writing to `projects.epc_company` field
- [ ] On reject: log reason, feed back into KB as negative evidence for future research

---

## Phase 3: Agent Chat Excellence (March 22–28)

### 3.0 Architecture Fix: Projects-with-EPC Join Tool (P0 — prerequisite for 3.1)
**Root cause analysis (2026-03-11):** Traced Liav's two queries through the full stack and found three blocking gaps:
1. `search_projects` returns `epc_company` but it's NULL for all pending discoveries — only populated after acceptance
2. `query_knowledge_base(entity_name="McCarthy")` only returns accepted engagements — pending discoveries invisible
3. No tool does the JOIN that Claude needs: projects ← latest epc_discovery (including pending) ← KB engagements

**Inspired by:** the-hog's "embed workflow patterns in system prompt" and "tool descriptions as decision trees" patterns.

**Actions:**
- [ ] New tool: `search_projects_with_epc` — single tool that handles both query patterns:
  - Query 1 mode: `search_projects_with_epc(state="TX", cod_year=2026)` → projects + their latest EPC discovery (pending or accepted)
  - Query 2 mode: `search_projects_with_epc(epc_name="McCarthy")` → all projects where this EPC was discovered
  - Parameters: `state?`, `cod_year?`, `epc_name?`, `developer?`, `mw_min?`, `confidence_min?`, `include_pending=true`, `limit=30`
  - Returns: project name, developer, MW, state, COD, EPC contractor, confidence, review_status, source_count, discovery_date
- [ ] New DB function: `db.search_projects_with_epc_context()` — SQL join across `projects` + `epc_discoveries` (latest per project) + optional `epc_engagements` fallback
- [ ] Update `search_projects` tool description to clarify: "Returns project metadata. The `epc_company` field only reflects accepted discoveries. For EPC discovery status including pending research, use `search_projects_with_epc` instead."
- [ ] Update `query_knowledge_base` tool description to clarify: "Returns accepted engagements only. For all discoveries including pending, use `search_projects_with_epc(epc_name=...)`."
- [ ] Register new tool in `tools/__init__.py` and make available to chat agent

### 3.1 Make Liav's Example Queries Work Reliably
**Target queries (from Liav):**
1. *"List all solar projects expected to start in Texas in 2026 and the EPCs building them."*
2. *"For McCarthy (EPC), list all projects they are expected to build."*

**Actions:**
- [ ] Overhaul `CHAT_SYSTEM_PROMPT` with the-hog-style workflow patterns:
  - Add "## Query Patterns" section with explicit tool-use chains for common queries
  - Pattern 1: "Projects in [state] with EPCs" → call `search_projects_with_epc(state, cod_year)`
  - Pattern 2: "Projects for [EPC name]" → call `search_projects_with_epc(epc_name=...)`
  - Pattern 3: "Research EPC for [project]" → call `search_projects` to find project, then use web search tools
  - Pattern 4: "What do we know about [entity]?" → call `query_knowledge_base(entity_name=...)`
  - Each pattern: when to use, expected tool call, example output format
- [ ] Add tool-use decision tree to prompt: "If user asks about projects → search_projects_with_epc. If user asks to research/discover → web_search tools. If user asks about an entity's history → query_knowledge_base."
- [ ] Test both queries end-to-end, document actual behavior vs expected
- [ ] Validate: both queries return structured, accurate results with sources and review status

### 3.2 Context Compaction for Long Conversations
**Problem:** Long chat sessions will degrade agent performance as context fills up.
**Inspired by:** the-hog's `context-compiler.ts` — compacts tool outputs into stubs with retrieval refs.
**Actions:**
- [ ] Implement message compaction in chat_agent.py: before each turn, estimate context size
- [ ] If context exceeds `max_context_chars` (default 100K), compact tool outputs older than 3 turns:
  - Replace large outputs (>500 chars) with stubs: `{"_compacted": true, "tool": "...", "summary": "...", "result_count": N}`
  - Keep text blocks and recent tool outputs intact
- [ ] Keep last 3 turns fully uncompacted (current working context)
- [ ] Test with 20+ turn conversations — agent should remain coherent

### 3.3 Agent Memory Tools
**Inspired by:** the-hog's `remember` + `getMemory` semantic recall tools with rate limiting.
**Actions:**
- [ ] Add `remember` tool: stores key facts to an `agent_memory` table (scope: project or global)
  - Schema: `{memory: str, scope: "project"|"global", memory_key?: str, importance: 1-10}`
  - Rate limit: max 5 writes per conversation turn
- [ ] Add `recall` tool: retrieves relevant memories by keyword/scope before answering
- [ ] Use cases: "Liav confirmed McCarthy is a key EPC", "Ignore results from source X"
- [ ] Agent auto-recalls relevant context before research or answering queries
- [ ] DB migration: `agent_memory(id, memory, scope, memory_key, importance, created_at, updated_at)`

---

## Phase 4: UI Polish (March 29 – April 4)

### 4.1 Message Virtualization
**Inspired by:** the-hog's `react-virtuoso` for chat rendering.
**Actions:**
- [ ] Replace current message list with virtualized rendering
- [ ] Handles 100+ messages without performance degradation
- [ ] Maintain scroll-to-bottom behavior on new messages

### 4.2 Frozen Response Detection
**Inspired by:** the-hog's `response-analysis.ts` pattern.
**Actions:**
- [ ] Detect when SSE stream starts but never sends text/tool content
- [ ] After 30s of no content: show "Agent appears stuck — retry?" prompt
- [ ] Log frozen responses for debugging

### 4.3 Research Progress Indicators
**Actions:**
- [ ] Show real-time search progress during research: "Searching Brave for 'McCarthy solar EPC'..."
- [ ] Display tool-by-tool progress (search → fetch → analyze → report)
- [ ] Replace generic spinner with step-by-step progress

---

## Phase 5: Business & Infrastructure (Ongoing)

### 5.1 Map Imagery Limitation (Acknowledged)
- Google Maps imagery is 2–3 years outdated — known limitation
- Not actionable for code; relevant for Solar Sentinel feasibility discussions
- Consider alternative imagery sources (Sentinel-2, Planet Labs) if satellite detection moves forward

### 5.2 Usage Metering Preparation
**Inspired by:** the-hog's credit gating pattern (check → spend → refund-on-failure).
**Actions:**
- [ ] Design credit/usage model: what costs credits (research runs, agent queries, batch jobs)
- [ ] Implement usage tracking table: `usage_events(user_id, action, credits, timestamp)`
- [ ] Gate expensive operations behind balance check (not enforced yet, just tracked)
- [ ] This prepares for pricing discussions with Liav

### 5.3 Business Structure (Non-Technical)
- [ ] Schedule call with Liav to discuss internship structure
- [ ] Align on: scope of work, pricing model, contribution areas beyond this product
- [ ] Lawyer's concern: define terms before product matures and pricing becomes contentious
- [ ] Goal: formalize relationship so product development continues with clear expectations

---

## Summary Timeline

| Week | Phase | Key Deliverables |
|------|-------|-----------------|
| Mar 11–14 | Phase 1: Critical Fixes | Research button working, source URLs visible |
| Mar 15–21 | Phase 2: Trust | Source labels, confidence aggregation, review flow |
| Mar 22–28 | Phase 3: Agent Chat | Liav's queries working, context compaction, memory |
| Mar 29–Apr 4 | Phase 4: UI Polish | Virtualization, frozen detection, progress indicators |
| Ongoing | Phase 5: Business | Usage metering, Liav alignment call |

---

## Success Criteria

1. **Research button works** — 0 errors on 10 consecutive test runs
2. **Every result has source links** — clickable URLs on 100% of research outputs
3. **Liav's 2 queries work** — accurate, structured responses with sources
4. **Data transparency** — every data point labeled with source method and reliability
5. **Review flow enforced** — no unreviewed data enters production fields
