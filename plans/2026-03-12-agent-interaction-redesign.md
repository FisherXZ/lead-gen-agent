# Agent Interaction Redesign: Notify/Ask, Completeness Eval, Plan Mode, Extended Memory

**Date:** 2026-03-12
**Status:** Approved — Features 1 & 4 ready to implement. Features 2 & 3 need detailed design discussion with Fisher.

## Context

Research from Harvey AI, Claude Code, Manus, and Cursor revealed that top AI agents don't leave pausing up to the AI. They build structured checkpoints into workflows. Our `request_guidance` tool exists but is barely used because the prompt doesn't tell the agent when to call it, and there's no separation between "status update" and "I need your input."

This plan implements 4 features that work together to make the research flow interactive and human-guided.

**Pre-requisite already done:** `query_knowledge_base` added to `RESEARCH_TOOLS` (research.py:31).

---

## Feature 1: Separate "Notify" from "Ask" ✅ Ready to build

Split into two distinct tools following the Manus pattern.

### New file: `agent/src/tools/notify_progress.py`
```python
DEFINITION = {
    "name": "notify_progress",
    "description": "Send a one-way progress update. Does NOT pause execution. Use for status updates: search started, candidate found, verifying source, switching strategy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stage": {"type": "string", "enum": ["planning", "searching", "reading", "verifying", "analyzing", "switching_strategy"]},
            "message": {"type": "string", "description": "What you're doing now."},
            "detail": {"type": "string", "description": "Optional extra context."},
        },
        "required": ["stage", "message"],
    },
}

async def execute(tool_input: dict) -> dict:
    return {"status": "noted", **tool_input}
```

### Modify: `agent/src/tools/__init__.py`
- Import and register `notify_progress`

### Modify: `agent/src/research.py:31`
- Add `"notify_progress"` to `RESEARCH_TOOLS`

### Modify: `agent/src/prompts.py`
- Add to both prompts:
  ```
  ## Progress Updates
  Use notify_progress for one-way status updates (no response needed):
  - "planning": announcing your research plan
  - "searching": starting a web search
  - "reading": fetching and reading a page
  - "verifying": checking a candidate EPC's credentials
  - "analyzing": evaluating evidence
  - "switching_strategy": changing approach after dead ends

  Use request_guidance ONLY when you need the user to make a decision.
  ```

### New frontend: `frontend/src/components/chat/parts/ProgressNotificationCard.tsx`
- Lightweight inline card: stage badge + message text
- Muted styling (slate bg, small text), no buttons
- Collapsed by default in ToolPart — header shows the message inline

### Modify: `frontend/src/components/chat/ToolPart.tsx`
- Add `notify_progress` mapping → `ProgressNotificationCard`
- Progress label: stage + message
- Do NOT add to `EXPAND_WHEN_DONE`

### Fix: GuidanceCard button bug
**`frontend/src/components/chat/ChatInterface.tsx`**
- Add `useEffect` listener for `populate-chat-input` custom event
- On event: call `setInputValue(event.detail.text)` to populate the chat input
- This makes GuidanceCard option buttons actually work

---

## Feature 2: Completeness Evaluation — Always Require Approval ✅ Design agreed

Every research run must get human approval before finalizing findings.

### Design decisions (agreed with Fisher):
1. **Handoff creates a new chat conversation** pre-loaded with everything the agent found (project details, sources, reasoning, searches, scratchpad data)
2. **Keep `review_status = "pending"`** — no new status. The discovery lands in the review queue either way.
3. **User can approve from review queue OR from chat.** The agent can also accept on the user's behalf in chat if instructed.
4. **Full context in chat handoff:** project details, all sources/reasoning, searches performed, scratchpad data, and the agent's completeness assessment.

### Research Button flow (two checkpoints):
```
1. Click "Research EPC"
2. → Phase 1 API call: POST /api/discover/plan
   Agent plans only (no searching), returns proposed plan
3. Button shows plan inline:
   "Proposed plan:
    - Search [developer] + EPC contractor
    - Check McCarthy, Mortenson portfolios
    - Search trade publications"
   [Start Research] [Edit in Chat]
4. User clicks [Start Research]
5. → Phase 2 API call: POST /api/discover/execute
   Agent executes the plan headlessly
6. Returns results summary + discovery_id
7. Button shows: "Found [EPC] with [confidence] confidence"
   [Review in Chat]
8. User clicks [Review in Chat]
9. → Creates new chat conversation pre-loaded with all context
10. User discusses, approves, or asks for more research
```

### Implementation:

**`agent/src/models.py`**
- Add `needs_approval: bool = False` and `completeness_assessment: str | None = None` to `AgentResult`

**`agent/src/research.py`**
- New function: `async run_research_plan(project, knowledge_context) -> dict` — runs agent with planning-only prompt, returns the plan (max 3 iterations)
- Existing `run_research()`: when agent calls `report_findings`, set `result.needs_approval = True`, set `result.completeness_assessment` from reasoning

**`agent/src/main.py`**
- New endpoint: `POST /api/discover/plan` — calls `run_research_plan()`, returns plan text
- Modify `POST /api/discover` (or new `POST /api/discover/execute`): accepts optional `plan` param, stores discovery as `pending`, returns `handoff_to_chat: true` with assessment, discovery_id, and all context
- New endpoint: `POST /api/discover/handoff` — creates a new chat conversation pre-loaded with the research context, returns `conversation_id`

**`agent/src/prompts.py`**
- Chat prompt addition:
  ```
  ## Completeness Check — REQUIRED
  Before calling report_findings, you MUST call request_guidance with:
  - Summary of what you found (or didn't find)
  - Your proposed confidence level and why
  - Sources you plan to cite
  - Ask: "Should I report this finding, or should I keep searching?"
  Only call report_findings AFTER the user approves.
  ```
- Headless prompt addition:
  ```
  ## Completeness Assessment
  When ready to report findings, include a detailed assessment in your
  report_findings reasoning: what you found, confidence justification,
  sources, and gaps. Your findings will be held for human review.
  ```

**`frontend/src/components/epc/ResearchButton.tsx`**
- Complete rewrite into a multi-state component:
  - `idle` → shows "Research EPC" button
  - `planning` → shows spinner "Planning research..."
  - `plan_ready` → shows plan + [Start Research] + [Edit in Chat] buttons
  - `executing` → shows spinner "Researching..." (with progress if streaming)
  - `results_ready` → shows summary + [Review in Chat] button
  - `error` → shows error + retry

---

## Feature 3: Plan-Then-Execute Mode ✅ Design agreed

Agent proposes a research plan before executing.

### Design decisions (agreed with Fisher):
1. **Headless research button shows plan first**, user approves before execution starts
2. **Plan is high-level strategy** — not specific search queries, but categories ("check EPC portfolios", "search trade pubs")
3. **Agent can deviate** if it finds something unexpected — the plan is a starting point, not a rigid script
4. **User modifies via natural language** — types a response like "Also check Blattner" and the agent adapts

### Implementation:

**`agent/src/prompts.py`** — Rewrite `## Research Process` in both prompts:

Headless (RESEARCH_SYSTEM_PROMPT) — new planning-only variant:
```
## Research Planning
You are generating a research plan for a solar project. Do NOT search yet.
Review the project details and knowledge base context, then propose a plan:
- List 3-5 high-level search strategies and why each is relevant
- Note which EPC portfolio sites to check based on the developer/state
- Identify what the KB already tells us
- Flag any challenges (e.g., early-stage project, shell company developer)
Call report_findings with your plan in the reasoning field.
```

Headless (RESEARCH_SYSTEM_PROMPT) — execution variant:
```
## Research Process
### Phase 1: Execute Plan
You have an approved research plan. Execute it step by step.
1. Call notify_progress(stage="planning", message="Starting approved plan")
2. Execute each search strategy. Call notify_progress after each.
3. Follow promising leads with fetch_page.

### Phase 2: Adapt
4. After completing the plan, assess: did I find enough?
5. If not, formulate 1-2 additional targeted searches.
6. If an unexpected lead appears, follow it even if not in the original plan.

### Phase 3: Reporting
7. Call report_findings with verified result and detailed reasoning.
```

Interactive (CHAT_SYSTEM_PROMPT):
```
## Research Process (Interactive)
### Phase 1: Planning
1. Review project details and knowledge base context.
2. Call request_guidance with your proposed research plan:
   - List 3-5 high-level search strategies you'll use
   - Which EPC portfolio sites to check
   - What the KB already tells us
   - Ask: "Does this plan look good, or should I adjust?"
3. Wait for user approval before proceeding.

### Phase 2: Execution
4. Execute the approved plan.
5. Call notify_progress after each search to report progress.
6. Follow promising leads — you can deviate from the plan if you find something unexpected.

### Phase 3: Completeness Check
7. Call request_guidance with completeness assessment.
8. Only call report_findings after user approval.
```

**`agent/src/research.py`**
- New `PLANNING_TOOLS = ["query_knowledge_base", "report_findings"]` — planning phase only needs KB access
- New `run_research_plan()` function using `PLANNING_TOOLS` and planning-only prompt
- Existing `run_research()` accepts optional `approved_plan: str` parameter, injected into the user message

---

## Feature 4: Supabase Scratch Table for Extended Memory ✅ Ready to build

### New file: `supabase/migrations/013_create_research_scratch.sql`
```sql
CREATE TABLE IF NOT EXISTS research_scratch (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_research_scratch_session_key
    ON research_scratch (session_id, key);

ALTER TABLE research_scratch ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON research_scratch FOR SELECT USING (true);
CREATE POLICY "Service write" ON research_scratch FOR ALL USING (auth.role() = 'service_role');
```

### New file: `agent/src/tools/research_scratchpad.py`
```python
DEFINITION = {
    "name": "research_scratchpad",
    "description": "Persistent notepad for intermediate research findings. Survives context compaction. Write candidates, dead ends, sources, and assessments. Read to recover context after long runs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["write", "read"]},
            "session_id": {"type": "string"},
            "key": {"type": "string", "description": "e.g. 'candidates', 'dead_ends', 'sources', 'assessment'"},
            "value": {"type": "object", "description": "Data to write (required for write operation)."},
        },
        "required": ["operation", "session_id"],
    },
}
```
- `execute()`: write = upsert to `research_scratch`, read = select by session_id (optionally filtered by key)

### Modify: `agent/src/db.py`
- Add `upsert_scratch(session_id, key, value)` — upsert on `(session_id, key)` conflict
- Add `read_scratch(session_id, key=None)` — select with optional key filter

### Modify: `agent/src/tools/__init__.py`
- Import and register `research_scratchpad`

### Modify: `agent/src/research.py`
- Add `"research_scratchpad"` to `RESEARCH_TOOLS`
- Generate session_id at start: `session_id = f"research-{project['id']}-{uuid4().hex[:8]}"`
- Inject into user message: append `\n- **Session ID:** {session_id}` in `build_user_message`

### Modify: `agent/src/prompts.py`
- Add to both prompts:
  ```
  ## Research Scratchpad
  Use research_scratchpad to persist intermediate findings. Write to it when you:
  - Find a candidate EPC (key: "candidates")
  - Hit a dead end (key: "dead_ends")
  - Discover sources (key: "sources_found")
  - Want to save your current assessment (key: "assessment")
  Read from it if you need to recover context after long research runs.
  Use the session_id from the project details.
  ```

### Modify: `frontend/src/components/chat/ToolPart.tsx`
- Add `research_scratchpad` labels: "Saving to scratchpad..." / "Reading scratchpad..."
- Keep collapsed by default — background operation

---

## Implementation Order

1. **Feature 1** — notify_progress tool + GuidanceCard fix ✅ Ready
2. **Feature 4** — scratch table ✅ Ready
3. **Feature 3** — plan-then-execute (`run_research_plan()` + prompts) ✅ Design agreed
4. **Feature 2** — completeness eval + two-checkpoint research button ✅ Design agreed

## Files Changed Summary

| File | F1 | F2 | F3 | F4 |
|------|----|----|----|----|
| `agent/src/tools/notify_progress.py` | NEW | | | |
| `agent/src/tools/research_scratchpad.py` | | | | NEW |
| `supabase/migrations/013_create_research_scratch.sql` | | | | NEW |
| `frontend/src/components/chat/parts/ProgressNotificationCard.tsx` | NEW | | | |
| `agent/src/tools/__init__.py` | mod | | | mod |
| `agent/src/research.py` | mod | mod | | mod |
| `agent/src/models.py` | | mod | | |
| `agent/src/main.py` | | mod | | |
| `agent/src/db.py` | | | | mod |
| `agent/src/prompts.py` | mod | mod | mod | mod |
| `frontend/src/components/chat/ToolPart.tsx` | mod | | | mod |
| `frontend/src/components/chat/ChatInterface.tsx` | mod (bug fix) | | | |
| `frontend/src/components/epc/ResearchButton.tsx` | | mod | | |

## Verification

1. **Tests:** `cd agent && python -m pytest tests/`
2. **Feature 1:** In chat, research a project. See `notify_progress` cards inline. Click GuidanceCard buttons — text populates in chat input.
3. **Feature 4:** After research, check `research_scratch` table in Supabase for session data.
4. **Feature 3:** In chat, ask to research a project. Agent presents plan via `request_guidance` first. Approve → agent executes with `notify_progress` updates.
5. **Feature 2:** Click Research Button. See summary + "Review in Chat" button. Click it → chat opens with assessment. Approve → discovery finalized.

## Plain English Summary

These four features transform the agent from a black box into a collaborative research partner. Instead of pushing a button and hoping for the best, you'll see live progress updates (Feature 1), the agent will save its work so it doesn't forget mid-research (Feature 4), it'll propose a plan before diving in (Feature 3), and it'll always check with you before finalizing any finding (Feature 2). The key insight from studying Harvey, Manus, Cursor, and Claude Code: don't let the AI decide when to pause — build the pause points into the workflow.
