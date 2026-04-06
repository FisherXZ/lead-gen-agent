# Briefing Command Center Redesign

## Problem

The Briefing page is a narrow (`max-w-2xl`) passive event feed that shows "You're all caught up" even when there are 61 pending reviews. It looks like text on blank paper — no cards, no visual density, no hover states, no inline actions. Every other page in the app (Pipeline, Review Queue, Actions) uses full-width layouts with `bg-surface-raised` cards, badges, expandable rows, and interactive buttons. The Briefing should match that standard and become the primary command center for the product.

## Solution

Replace the current event-feed Briefing with a full-width command center dashboard:

1. **Pipeline funnel** — horizontal progress tracker showing the entire pipeline flow with counts at each stage. Bottleneck stage auto-highlighted in amber.
2. **Quick nav strip** — links to Pipeline, Review Queue, Actions, Map, Solarina.
3. **2×2 action grid** — four stacked panels showing what needs attention, with inline actions:
   - **Needs Review** — pending discoveries with inline approve/reject
   - **Needs Investigation** — unresearched projects sorted by lead score with "Research" button
   - **Contacts** — EPCs needing contact discovery + EPCs ready for CRM push
   - **Recently Completed** — accepted discoveries and HubSpot syncs

---

## Architecture

### Page Structure

```
BriefingPage (server component — fetches all data)
└── BriefingDashboard (client component — renders all panels)
    ├── PipelineFunnel        — horizontal stage tracker
    ├── QuickNav              — page links strip
    ├── NeedsReviewPanel      — mini review queue with approve/reject
    ├── NeedsInvestigationPanel — unresearched projects with Research button
    ├── ContactsPanel         — EPCs needing contacts + CRM-ready leads
    └── RecentlyCompletedPanel — accepted discoveries, HubSpot syncs
```

### Data Flow

The server component (`briefing/page.tsx`) fetches all data from Supabase in a single `Promise.all`, then passes it as props to the client component. No additional API endpoints needed — the existing Supabase queries are sufficient. The client component handles local state for approve/reject/dismiss interactions.

---

## Pipeline Funnel

A horizontal bar showing 5 stages with counts and arrows between them.

### Stages

| Stage | Label | Query | Color logic |
|-------|-------|-------|-------------|
| 1 | Projects | `projects` total count | `text-text-primary` |
| 2 | Researched | `epc_discoveries` distinct project count | `text-text-secondary` |
| 3 | Pending Review | `epc_discoveries` where `review_status = 'pending'` count | Amber if > 0 (bottleneck highlight) |
| 4 | Accepted | `epc_discoveries` where `review_status = 'accepted'` count | `text-status-green` |
| 5 | In CRM | `hubspot_sync_log` distinct project count | `text-text-primary` or `text-text-tertiary` if 0 |

### Visual Treatment

- Container: `bg-surface-raised border border-border-subtle rounded-lg` spanning full width
- Each stage: serif number (Lora, 26px) + uppercase label (Geist, 9px)
- Arrows: `→` in `text-text-tertiary` between stages
- **Bottleneck highlight:** "Pending Review" stage gets `bg-accent-amber-muted border border-accent-amber-muted` treatment and amber text whenever its count is > 0. This is hardcoded to stage 3, not dynamically calculated — pending reviews are always the bottleneck in this pipeline.
- Each stage is clickable — navigates to the relevant page (/projects for Projects, /review for Pending Review, /actions for Accepted, etc.)
- Hover: subtle `bg-surface-overlay` on the stage cell

### Responsive

On mobile (<640px), the funnel wraps to 2 rows or switches to a vertical list. Stages collapse to `number + label` without arrows.

---

## Quick Nav Strip

A row of small link pills below the funnel, providing one-click access to every page.

| Link | Target |
|------|--------|
| Pipeline → | `/projects` (the EPC discovery dashboard) |
| Review Queue → | `/review` |
| Actions → | `/actions` |
| Map → | `/map` |
| Solarina → | `/agent` |

### Visual Treatment

- Each pill: `text-xs text-text-tertiary border border-border-subtle rounded-md px-3 py-1`
- Hover: `border-border-default text-text-secondary`
- No active state — these are outbound links, not filters

---

## Needs Review Panel

Shows the most recent pending discoveries with inline approve/reject.

### Data

From the server component query: `epc_discoveries` where `review_status = 'pending'`, joined with `projects`, ordered by `created_at DESC`, limited to 5.

### Card Layout

Each card shows:
- **EPC name** in serif (13px, `text-text-primary`)
- **Confidence badge** — `confirmed` (green), `likely` (amber), `possible` (neutral)
- **Project context** — name + MW + ISO region in `text-text-tertiary` (10px)
- **Approve (✓) / Reject (✕) buttons** — same styling as Review Queue page: green-muted and red-muted backgrounds

### Interactions

- **Click card body** → expands to show reasoning summary (like Review Queue's expandable row)
- **Click ✓ (Approve)** → `PATCH /api/discover/{discovery_id}/review` with `{ action: "accepted" }`. Card animates out. Funnel counts update locally.
- **Click ✕ (Reject)** → same endpoint with `{ action: "rejected" }`. Card animates out.
- **"View all →"** link in header → navigates to `/review`
- **"+ N more"** indicator at bottom when there are more than 5

### Visual Treatment

- Cards: `bg-surface-raised border border-accent-amber-muted rounded-lg px-4 py-3`
- Hover: `border-accent-amber/30`
- Section header: `text-[10px] uppercase tracking-widest text-text-tertiary` + amber count badge

---

## Needs Investigation Panel

Shows unresearched projects sorted by lead score.

### Data

From server component: `projects` where NOT IN (select project_id from epc_discoveries), ordered by `lead_score DESC`, limited to 5.

### Card Layout

Each card shows:
- **Project name** (13px, `text-text-primary`)
- **ISO region + state + lead score** in `text-text-tertiary` (10px)
- **"Research" button** — amber-muted background, triggers EPC research

### Interactions

- **Click "Research"** → calls the existing 2-step plan/execute flow: `POST /api/discover/plan` then `POST /api/discover`. Button shows spinner during research.
- **Click card body** → navigates to `/projects/[id]`
- **"View pipeline →"** link → navigates to `/projects`
- **"Top by lead score · N more"** indicator at bottom

### Visual Treatment

- Cards: `bg-surface-raised border border-border-subtle rounded-lg px-4 py-3`
- Hover: `border-border-default`
- Research button: `bg-accent-amber-muted text-accent-amber rounded-md px-3 py-1 text-xs`

---

## Contacts Panel

Shows EPCs that need contact discovery and EPCs ready for CRM push.

### Data

Two queries from server component:
1. **Need contacts:** `epc_discoveries` where `review_status = 'accepted'` AND `entity_id IS NOT NULL`, joined with entities, where entity has 0 contacts. Limited to 5.
2. **Ready for CRM:** `epc_discoveries` where `review_status = 'accepted'` AND entity has ≥1 contact AND no `hubspot_sync_log` entry. Limited to 3.

Cards are interleaved: CRM-ready items show first (they're further along), then contact-needed items.

### Card Layout

**Need contacts card:**
- EPC name (13px) + "0 contacts" in `text-text-tertiary`
- Source project context
- **"Find" button** — amber-muted, triggers contact discovery

**CRM-ready card:**
- EPC name + amber badge showing contact count (e.g., "3 contacts")
- "Ready for CRM push" in `text-text-tertiary`
- **"Push to HS" button** — solid amber (`bg-accent-amber text-surface-primary`), triggers HubSpot push

### Interactions

- **"Find"** → `POST /api/contacts/discover` with `{ entity_id }`. Button shows spinner.
- **"Push to HS"** → `POST /api/hubspot/push` with `{ project_id }`. Button shows spinner, then green "Synced" badge.
- **"Actions →"** link → navigates to `/actions`

### Visual Treatment

Same card pattern as other panels. CRM-ready cards use solid amber button (primary CTA) to visually distinguish from the amber-muted "Find" button.

---

## Recently Completed Panel

Shows accepted discoveries and HubSpot syncs.

### Data

From server component: `epc_discoveries` where `review_status = 'accepted'`, joined with `hubspot_sync_log` (left join), ordered by most recent activity, limited to 5.

### Card Layout

Each card shows:
- **Green dot** (6px circle, `bg-status-green`) as status indicator
- **EPC name** (13px, `text-text-primary`)
- **Status badge** — "In HubSpot" (green) or "Accepted" (green-muted)
- **Context line** — project name + MW + contact count + time since action

### Interactions

- **Click card** → navigates to `/projects/[project_id]`
- No action buttons — this section is informational

### Visual Treatment

- Cards: `bg-surface-raised border border-border-subtle rounded-lg px-4 py-3`
- No hover border change (informational, not actionable)
- Green dot + badge give visual confirmation of completed status

---

## Full-Width Layout

### Page width

Change from `max-w-2xl` to `max-w-7xl px-6 lg:px-8`. This matches the Map page's width and gives the 2×2 grid room to breathe.

### Grid structure

```
┌─────────────────────────────────────────────────┐
│  Briefing (header)                              │
├─────────────────────────────────────────────────┤
│  [423] → [64] → [61] → [3] → [0]  (funnel)    │
├─────────────────────────────────────────────────┤
│  Pipeline → | Review → | Actions → | Map → ... │
├───────────────────────┬─────────────────────────┤
│  Needs Review (61)    │  Needs Investigation    │
│  ┌─ card ─┐           │  ┌─ card ─┐            │
│  ├─ card ─┤           │  ├─ card ─┤            │
│  └─ card ─┘           │  └─ card ─┘            │
├───────────────────────┼─────────────────────────┤
│  Contacts (5 need)    │  Recently Completed (3) │
│  ┌─ card ─┐           │  ┌─ card ─┐            │
│  ├─ card ─┤           │  ├─ card ─┤            │
│  └─ card ─┘           │  └─ card ─┘            │
└───────────────────────┴─────────────────────────┘
```

Grid: `grid grid-cols-1 lg:grid-cols-2 gap-5` for the 2×2 section. On mobile, panels stack vertically in order: Review → Investigation → Contacts → Completed.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Rewrite | `frontend/src/app/briefing/page.tsx` | Server component with all Supabase queries, pass props to dashboard |
| Create | `frontend/src/components/briefing/BriefingDashboard.tsx` | Client shell — renders funnel, nav, and 4 panels |
| Create | `frontend/src/components/briefing/PipelineFunnel.tsx` | Horizontal progress tracker |
| Create | `frontend/src/components/briefing/QuickNav.tsx` | Page links strip |
| Create | `frontend/src/components/briefing/NeedsReviewPanel.tsx` | Mini review queue with approve/reject |
| Create | `frontend/src/components/briefing/NeedsInvestigationPanel.tsx` | Unresearched projects with Research button |
| Create | `frontend/src/components/briefing/ContactsPanel.tsx` | EPCs needing contacts + CRM-ready leads |
| Create | `frontend/src/components/briefing/RecentlyCompletedPanel.tsx` | Accepted discoveries + HubSpot syncs |
| Delete | `frontend/src/components/briefing/BriefingFeed.tsx` | Replaced by BriefingDashboard |
| Delete | `frontend/src/components/briefing/StatBar.tsx` | Replaced by PipelineFunnel |
| Delete | `frontend/src/components/briefing/QuickFilters.tsx` | No longer needed — dashboard shows everything |
| Delete | `frontend/src/components/briefing/cards/*.tsx` | All 4 card types replaced by panel-specific cards |
| Delete | `frontend/src/components/briefing/ProjectPanel.tsx` | Click-through to /projects/[id] replaces slide-over |
| Delete | `frontend/src/lib/briefing-types.ts` | Types replaced by new panel-specific interfaces |

---

## Scope Boundaries

### In scope
- Full rewrite of Briefing page and all briefing components
- Pipeline funnel with clickable stages
- 4 action panels with inline interactions (approve/reject, research, find contacts, push to HubSpot)
- Quick nav strip
- Full-width responsive layout
- Tests for each panel component

### Out of scope
- Changing the Review Queue, Actions, or Pipeline pages — those stay as-is
- Real-time updates / WebSocket — stats refresh on page load only
- Batch operations from the Briefing page (batch research, batch approve) — future enhancement
- Generative UI in the Briefing — this is a traditional dashboard, not chat

---

## Plain English

**What is this?**
We're turning the Briefing page from a passive news feed into the main control panel for the product. Instead of "You're all caught up" (while 61 discoveries sit unreviewed), you see a pipeline funnel showing exactly where everything stands, plus four action panels where you can approve/reject discoveries, kick off EPC research, find contacts, and push leads to HubSpot — all without leaving the page.

**Why does it matter?**
The current Briefing is the landing page (/ redirects to /briefing) but it's the least useful page in the app. Pipeline, Review Queue, and Actions all have dense, interactive UIs. The Briefing should be the hub that ties them together — one glance tells you what needs attention, one click takes action.

**What changes visually?**
The page goes from a narrow text column to a full-width dashboard. Cards get backgrounds, borders, hover states, and inline action buttons — matching the visual density of every other page. The pipeline funnel replaces the bare stat bar with a visual flow that shows bottlenecks at a glance.
