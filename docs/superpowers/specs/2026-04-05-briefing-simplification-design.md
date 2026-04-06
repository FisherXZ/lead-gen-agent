# Briefing + Investigate: Product Simplification

**Date:** 2026-04-05
**Status:** Design — awaiting review

---

## Plain English

Our users are relationship-driven solar sales reps, not data analysts. They hear about projects at conferences and through their network. They don't need a 1,000-row spreadsheet with 10 filters — they need a system that tells them what's new, who to contact, and what to say. This redesign replaces a 6-page dashboard with a 2-screen product: a daily briefing feed of actionable cards, and a chat agent for on-demand investigation.

---

## Problem

The current platform has 6 navigable pages (Pipeline, Agent, Review Queue, Actions, Map, Settings) built around browsing and filtering data. The actual users are marketing and sales teams who previously did outreach manually through word of mouth, conferences, and interpersonal relationships. They don't need to browse — they need:

1. A digital scraping layer that catches projects they'd miss
2. Organization of fragmented signals into one place
3. Actionable output: who to contact, outreach context, and CRM integration

The current UI forces them into a data-analyst workflow that doesn't match how they work.

---

## Design

### Information Architecture

The product collapses from 6 pages to 3 screens:

| Screen | Purpose | Replaces |
|--------|---------|----------|
| **Briefing** (home) | Daily prioritized feed of what's new + action cards | Pipeline, Review Queue, Actions, Stats |
| **Investigate** (chat) | On-demand research via the agent | Agent page (enhanced) |
| **Settings** | Account, team, HubSpot connection | Settings (unchanged) |

**Pages removed as standalone routes:**
- Pipeline table (`/` with EpcDiscoveryDashboard)
- Review Queue (`/review`)
- Actions (`/actions`)
- Map (`/map`)
- Project Detail (`/projects/[id]`)

**Capabilities preserved, relocated:**
- **Map:** Embedded widget in briefing cards or project detail panel when location is relevant. Also renderable by the agent in chat.
- **Review Queue:** Inline approve/reject buttons on briefing Review Cards. No separate page.
- **Stats:** Compact one-line summary bar at top of Briefing (e.g., "12 new leads this week · 3 awaiting review · 47 EPCs discovered").
- **Filters:** 2-3 quick filter chips on Briefing (region, time range, construction status). Advanced filtering moves to the agent via natural language.
- **Project Detail:** Slide-over panel triggered from any card, not a standalone page.

**Navigation:** Sidebar simplifies to Briefing, Investigate, Settings.

---

### Briefing Screen

The home screen is a vertically-stacked feed of prioritized event cards. Users open it like email — act on what's there, dismiss what's handled.

#### Summary Stat Bar
One line at the top: `12 new leads this week · 3 awaiting review · 47 EPCs discovered`
Glanceable, not a dashboard. Updates on each visit.

#### Quick Filters
2-3 filter chips below the stat bar:
- **Region** (ERCOT, CAISO, MISO, All)
- **Time range** (Today, This Week, This Month)
- **Construction status** (optional, if useful)

#### Card Types

Cards are ordered by priority: New Leads > Reviews > New Projects > Status Changes > Digest.

**1. New Lead Card** (highest priority)
- *Trigger:* EPC discovered + contacts found — fully actionable
- *Shows:* EPC name, project name, MW capacity, region, lead score, discovered contacts (name + title + LinkedIn). One-sentence auto-generated outreach context: "McCarthy was just awarded the 350MW Sunflower project in ERCOT. Construction expected Q2 2027."
- *Actions:* `Push to HubSpot` · `Copy Outreach` · `Expand Details`

**2. Review Card** (needs user input)
- *Trigger:* Agent discovered an EPC but confidence isn't high enough to auto-accept
- *Shows:* Project name, proposed EPC, confidence level, one-line reasoning with source link
- *Actions:* `Approve` · `Reject` · `Investigate` (opens chat with context pre-loaded)

**3. New Project Alert** (informational)
- *Trigger:* New project appears in ISO queue matching watch criteria
- *Shows:* Project name, developer, MW, region, status. No EPC yet.
- *Actions:* `Research EPC` (kicks off agent discovery) · `Dismiss`

**4. Status Change Card** (informational)
- *Trigger:* Project construction status changes, COD updates, or project withdrawn
- *Shows:* Project name, what changed (e.g., "Pre-Construction → Under Construction"), why it matters
- *Actions:* `View Details` · `Dismiss`

**5. Weekly Digest Card** (summary, Monday mornings)
- *Shows:* Rolled-up summary: X new projects, Y EPCs discovered, Z contacts found, top 3 highest-scored new leads
- *Actions:* `View All` (scrolls to cards below)

#### Dismissed Cards
Dismissed cards move to a collapsed "History" section at the bottom of the feed. Not deleted — always scrollable.

#### Project Detail Panel
When a user clicks "Expand Details" or "View Details" on any card, a slide-over panel opens (right side) showing:
- Project name, developer, MW, region, status badges
- EPC discovery details with reasoning and sources
- Contacts list
- Location (with inline mini-map if lat/lon available)
- Action buttons (Push to HubSpot, Copy Outreach, Research EPC)

This replaces the standalone `/projects/[id]` page.

---

### Investigate Screen (Chat)

The existing ChatInterface stays and is enhanced with context-awareness.

#### Entry Points
- Direct navigation via sidebar/tab
- "Investigate" button from any briefing card (pre-loads context so the user doesn't re-explain)
- Suggested prompts on empty state

#### Suggested Prompts (tuned to real use cases)
- "What's new in ERCOT this week?"
- "What do we know about Blattner Energy?"
- "Find contacts at Signal Energy"
- "Any projects over 300MW entering construction?"

#### Agent Capabilities in Chat
- Surface project tables (replaces Pipeline browse)
- Render maps when geographic context matters
- Run EPC research on a project the user mentions
- Find contacts and generate outreach copy
- Push results to HubSpot directly
- Show full project detail panel for any project

#### Context Pre-Loading
When entering chat from a briefing card's "Investigate" button, the agent receives the card's context automatically. The user never has to re-explain what they're looking at.

---

### Settings Screen

Unchanged from current implementation. Covers account, team management, HubSpot connection.

---

## Component Impact

### Removed Components
| Component | Reason |
|-----------|--------|
| `EpcDiscoveryDashboard.tsx` | Replaced by BriefingFeed |
| `FilterBar.tsx` | Replaced by QuickFilters (2-3 chips) + agent |
| `StatsCards.tsx` | Replaced by StatBar (one line) |
| `ReviewQueue.tsx` | Review actions move to briefing cards |
| `actions/page.tsx` | Merged into New Lead briefing cards |
| `projects/[id]/page.tsx` | Becomes ProjectPanel slide-over |
| `map/page.tsx` | Becomes embeddable widget |
| `review/page.tsx` | Removed |

### Kept Components
| Component | Notes |
|-----------|-------|
| `Sidebar.tsx` | Simplified to 3 items |
| `MainContent.tsx` | Simplified wrapper |
| `ChatInterface.tsx` | Enhanced with context pre-loading |
| All chat part components | Render inside chat responses as-is |
| `settings/page.tsx` | Unchanged |

### New Components to Build
| Component | Purpose |
|-----------|---------|
| `BriefingFeed.tsx` | Main feed container with priority ordering |
| `NewLeadCard.tsx` | Actionable lead card with outreach + HubSpot |
| `ReviewCard.tsx` | Inline approve/reject for EPC discoveries |
| `AlertCard.tsx` | New project / status change notifications |
| `DigestCard.tsx` | Weekly summary rollup |
| `StatBar.tsx` | Compact one-line metrics summary |
| `QuickFilters.tsx` | 2-3 filter chips |
| `ProjectPanel.tsx` | Slide-over detail view |

### Backend Changes
- **New endpoint/query:** Briefing generation — prioritized, deduplicated events since last user visit. This is a view layer over existing Supabase data (projects, discoveries, contacts, research_attempts). No data model changes required.
- **User visit tracking:** Simple `last_seen_at` timestamp per user to determine "what's new since last visit."
- **Chat context injection:** API support for passing card context into a new chat session.

---

## Product Cadence

- **Daily:** User opens Briefing, sees prioritized cards, acts on them
- **Real-time:** High-priority New Lead cards surface immediately when the agent completes a discovery with contacts
- **On-demand:** User opens Investigate to research something they heard about in the field
- **Weekly:** Digest card summarizes the past week every Monday

---

## Design Language

All new components follow `frontend/DESIGN.md`:
- Dark warm foundation (`#1C1A17` backgrounds)
- Lora serif for card headings, Geist sans for everything else
- Amber accent for actions and emphasis
- No blue anywhere
- Generous whitespace, quiet confidence aesthetic
- Harvey AI as the reference point

---

## Success Criteria

1. A sales rep can open the app, understand what needs attention, and take action in under 60 seconds
2. Zero training needed — the interface is self-evident
3. The agent chat handles any query that previously required navigating to Pipeline, Map, or Project Detail
4. No data or capability is lost — everything is still accessible, just reorganized around the user's workflow
