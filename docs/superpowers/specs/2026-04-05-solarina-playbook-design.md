# Solarina Playbook Redesign

## Problem

The agent chat page shows 6 hardcoded prompt pills ("What's new in ERCOT this week?", "Find contacts at Signal Energy", etc.) that cover a fraction of the agent's 36-tool capability set. They're static, question-phrased, flat, and don't guide users toward high-value workflows. The page title says "Solar Project Research Assistant" — generic and forgettable.

## Solution

Replace the current `SuggestedPrompts` component with a two-column hybrid playbook:

- **Left column ("Right Now")** — dynamic nudges pulled from live stats, showing what needs attention
- **Right column ("I can help you")** — static outcome-oriented cards describing the 5 main workflows
- **Header** — just "Solarina" in serif, no subtitle

The agent is named **Solarina**.

## Design References

- **Manus AI** — outcome-first cards that describe goals, not queries
- **Perplexity** — dynamic/trending content that keeps the home page feeling alive

We take the Manus approach for the right column (goal-oriented outcome cards) and the Perplexity approach for the left column (live data that changes with state).

---

## Architecture

### Component Structure

```
SuggestedPrompts (replaced by)
└── Playbook
    ├── PlaybookHeader          — "Solarina" in Lora serif
    ├── RightNowColumn          — dynamic nudges from live stats
    │   └── NudgeCard           — single stat nudge (count + label + page link)
    └── OutcomeColumn           — static workflow cards
        └── OutcomeCard         — single outcome (title + description)
```

### Data Flow

```
BriefingPage (server component, already computes stats)
    └── /api/playbook/stats (new lightweight endpoint)
            ↓
        ChatInterface
            └── Playbook (client component)
                ├── fetches stats on mount via /api/playbook/stats
                ├── RightNowColumn (renders dynamic nudges)
                └── OutcomeColumn (renders static cards)
```

The Briefing page already computes `BriefingStats` (new_leads_this_week, awaiting_review, total_epcs_discovered). The playbook needs similar but slightly different stats. Rather than coupling to the briefing page, we add a small API endpoint that queries the same tables.

---

## Left Column: "Right Now" (Dynamic)

### Stats to show

| Nudge | Query | Color | Pre-fill prompt | Page link |
|-------|-------|-------|-----------------|-----------|
| Awaiting review | `epc_discoveries` where `review_status = 'pending'`, count | amber | "Let's triage the {n} pending reviews" | → /review |
| New projects this week | `projects` where `created_at >= 7 days ago`, count | green | "What's new this week? Show me the {n} new projects" | → /briefing |
| EPCs need contacts | `epc_discoveries` where `review_status = 'accepted'` AND `entity_id IS NOT NULL` AND entity has zero rows in `contacts` table, count | ivory | "Find contacts for the {n} EPCs that need them" | → /actions |
| Leads ready for CRM | `epc_discoveries` where `review_status = 'accepted'` AND entity has ≥1 contact AND no row in `hubspot_sync_log` for that project, count | ivory | "Let's push the {n} ready leads to HubSpot" | → /actions |

### Behavior

- **Hide when zero:** If a nudge count is 0, don't render it
- **All zero state:** If every nudge is 0, show a single centered message: "You're all caught up" with a subtle "Start investigating →" link to the chat input
- **Click interaction:** Clicking the nudge card pre-fills the chat input with the templated prompt (interpolating the count). The `→ /page` link is a separate small element that navigates directly.
- **Refresh:** Stats are fetched once on mount. No polling. The page reloads stats on navigation back to the agent page.

### API Endpoint

`GET /api/playbook/stats`

Response:
```json
{
  "awaiting_review": 61,
  "new_projects_this_week": 3,
  "epcs_need_contacts": 5,
  "leads_ready_for_crm": 8
}
```

This is a server-side Next.js API route that queries Supabase directly (same pattern as the briefing page). No auth required since the data is aggregate counts only.

---

## Right Column: "I can help you" (Static)

### Outcome Cards

| Title | Description | Pre-fill prompt |
|-------|-------------|-----------------|
| Deep-dive a company | Research EPC, check filings, find contacts | "I want to deep-dive a company" |
| Batch research projects | Run EPC discovery on multiple projects at once | "Batch research unresearched projects" |
| Triage the review queue | Walk through pending discoveries one by one | "Let's triage pending reviews together" |
| Pipeline intelligence | Market trends, EPC rankings, regional activity | "Give me a pipeline intelligence briefing" |
| Export data | Download pipeline, contacts, or discoveries as CSV | "Export my pipeline data as CSV" |

### Behavior

- **Click interaction:** Clicking an outcome card pre-fills the chat input with the prompt. The agent then asks follow-up questions conversationally (e.g., "Which company?" for deep-dive).
- **No dynamic content:** These cards are hardcoded. They represent the 5 core workflows the agent supports.
- **Hover state:** Border shifts to amber-muted on hover (amber accent, not default border brightening).

---

## Visual Design

Follows `frontend/DESIGN.md` strictly:

- **Header:** "Solarina" — Lora serif, 24px, `text-text-primary`, centered, no subtitle
- **Column headers:** Geist, 10px, uppercase, `tracking-wider`, `text-text-tertiary` — "RIGHT NOW" and "I CAN HELP YOU"
- **Cards:** `bg-surface-raised`, `border border-border-subtle`, `rounded-lg`, `p-3` (12px 14px)
- **Stat numbers:** Lora serif, 18px — amber for reviews, green for new projects, ivory for others
- **Stat labels:** Geist, 12px, `text-text-secondary`
- **Page links:** Geist, 10px, `text-text-tertiary` — right-aligned, format "→ /page"
- **Outcome titles:** Geist, 13px, `font-medium`, `text-text-primary`
- **Outcome descriptions:** Geist, 11px, `text-text-tertiary`
- **Layout:** CSS grid, `grid-template-columns: 1fr 1fr`, gap 20px
- **Max width:** Same as ChatInterface container (centered, max-w-2xl or similar)
- **Responsive:** On mobile (<640px), stack columns vertically — Right Now on top, Outcomes below

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Delete | `frontend/src/components/chat/SuggestedPrompts.tsx` | Replaced by Playbook |
| Create | `frontend/src/components/chat/Playbook.tsx` | Main playbook component with both columns |
| Create | `frontend/src/app/api/playbook/stats/route.ts` | API endpoint for dynamic stats |
| Modify | `frontend/src/components/chat/ChatInterface.tsx` | Replace `<SuggestedPrompts>` with `<Playbook>`, pass `onSelect` |
| Create | `frontend/src/components/chat/Playbook.test.tsx` | Tests for playbook rendering and interactions |

---

## Scope Boundaries

### In scope
- New Playbook component replacing SuggestedPrompts
- New /api/playbook/stats endpoint
- Wiring into ChatInterface
- Tests

### Out of scope (future specs)
- **Generative UI for inline workflows** — rendering review cards, contact cards, approve/reject buttons inside chat messages. This is a separate, larger effort noted as a future direction.
- **Conversation history sidebar** — the existing sidebar stays as-is
- **Agent name change in system prompt** — "Solarina" is the UI name only for now; changing the agent's self-identification in the backend prompt is a separate change Fisher can decide on later.

---

## Plain English

**What is this?**
We're replacing the 6 random question buttons on the agent chat page with something that actually helps you. Left side shows what needs attention right now (pulled from real data — how many reviews are pending, how many new projects showed up). Right side shows the 5 main things the agent can do, phrased as goals not questions. Everything flows into the chat when you click it.

**Why does it matter?**
The current playbook barely scratches the surface of what the agent can do (36 tools across research, contacts, CRM, batch operations). Most users would never discover batch research or CSV export from the current prompts. The new design teaches users the full workflow set while also surfacing time-sensitive items.

**What's the agent name?**
Solarina. Clean, memorable, solar-themed. Shows in serif at the top of the chat page.
