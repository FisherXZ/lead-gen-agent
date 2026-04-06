# Briefing + Investigate: Product Simplification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 6-page dashboard with a 2-screen product: a daily Briefing feed of prioritized action cards + an enhanced Investigate (chat) screen.

**Architecture:** The Briefing screen is a new Next.js page that fetches prioritized events from a new backend endpoint (`/api/briefing`). Events are rendered as typed cards (NewLead, Review, Alert, StatusChange, Digest) with inline actions. The chat screen gets context pre-loading via URL search params. All removed pages' capabilities are absorbed into these two screens.

**Tech Stack:** Next.js 14 (App Router), React, Tailwind CSS, Supabase (SSR + browser clients), existing `agentFetch` wrapper, Radix UI tooltips, Sonner toasts. Design tokens from `frontend/DESIGN.md`.

**Worktree:** `.worktrees/briefing-simplification` (branch: `feature/briefing-simplification`)

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/app/briefing/page.tsx` | Briefing page — server component, fetches data, renders feed |
| `frontend/src/components/briefing/BriefingFeed.tsx` | Client component — manages card list, filters, dismiss state |
| `frontend/src/components/briefing/StatBar.tsx` | One-line summary metrics bar |
| `frontend/src/components/briefing/QuickFilters.tsx` | 2-3 filter chips (region, time range) |
| `frontend/src/components/briefing/cards/NewLeadCard.tsx` | Actionable lead card with outreach + HubSpot actions |
| `frontend/src/components/briefing/cards/ReviewCard.tsx` | Inline approve/reject for EPC discoveries |
| `frontend/src/components/briefing/cards/AlertCard.tsx` | New project + status change notifications |
| `frontend/src/components/briefing/cards/DigestCard.tsx` | Weekly summary rollup |
| `frontend/src/components/briefing/ProjectPanel.tsx` | Slide-over detail panel (replaces `/projects/[id]`) |
| `frontend/src/lib/briefing-types.ts` | TypeScript interfaces for briefing events |

### Modified Files
| File | Change |
|------|--------|
| `frontend/src/components/Sidebar.tsx` | Reduce nav to 3 items: Briefing, Investigate, Settings |
| `frontend/src/app/page.tsx` | Redirect `/` to `/briefing` |
| `frontend/src/app/agent/page.tsx` | Rename route conceptually to "Investigate", add context pre-loading from search params |
| `frontend/src/components/chat/ChatInterface.tsx` | Accept optional `initialContext` prop for pre-loaded card context |
| `frontend/src/components/chat/SuggestedPrompts.tsx` | Update prompts to match real sales use cases |

### Removed (not deleted — just unlinked from navigation)
| File | Reason |
|------|--------|
| `frontend/src/app/actions/page.tsx` | Merged into NewLeadCard |
| `frontend/src/app/review/page.tsx` | Merged into ReviewCard |
| `frontend/src/app/map/page.tsx` | Available via chat agent on demand |
| `frontend/src/app/projects/[id]/page.tsx` | Replaced by ProjectPanel slide-over |

---

## Task 1: Briefing Types

**Files:**
- Create: `frontend/src/lib/briefing-types.ts`

- [ ] **Step 1: Create the briefing event type definitions**

```typescript
// frontend/src/lib/briefing-types.ts
import { Project, EpcDiscovery, ConstructionStatus } from "./types";

export type BriefingEventType =
  | "new_lead"
  | "review"
  | "new_project"
  | "status_change"
  | "digest";

export interface BriefingContact {
  id: string;
  full_name: string;
  title: string | null;
  linkedin_url: string | null;
  outreach_context: string | null;
}

export interface BriefingEvent {
  id: string;
  type: BriefingEventType;
  priority: number; // 1 = highest (new_lead), 5 = lowest (digest)
  created_at: string;
  dismissed: boolean;
}

export interface NewLeadEvent extends BriefingEvent {
  type: "new_lead";
  priority: 1;
  project_id: string;
  project_name: string;
  developer: string | null;
  mw_capacity: number | null;
  iso_region: string;
  state: string | null;
  lead_score: number;
  epc_contractor: string;
  confidence: EpcDiscovery["confidence"];
  discovery_id: string;
  entity_id: string | null;
  contacts: BriefingContact[];
  outreach_context: string; // Auto-generated one-liner
}

export interface ReviewEvent extends BriefingEvent {
  type: "review";
  priority: 2;
  project_id: string;
  project_name: string;
  mw_capacity: number | null;
  iso_region: string;
  epc_contractor: string;
  confidence: EpcDiscovery["confidence"];
  discovery_id: string;
  reasoning_summary: string;
  source_url: string | null;
}

export interface NewProjectEvent extends BriefingEvent {
  type: "new_project";
  priority: 3;
  project_id: string;
  project_name: string;
  developer: string | null;
  mw_capacity: number | null;
  iso_region: string;
  state: string | null;
  status: string | null;
}

export interface StatusChangeEvent extends BriefingEvent {
  type: "status_change";
  priority: 4;
  project_id: string;
  project_name: string;
  previous_status: ConstructionStatus;
  new_status: ConstructionStatus;
  expected_cod: string | null;
}

export interface DigestEvent extends BriefingEvent {
  type: "digest";
  priority: 5;
  period_start: string;
  period_end: string;
  new_projects_count: number;
  epcs_discovered_count: number;
  contacts_found_count: number;
  top_leads: Array<{
    project_name: string;
    epc_contractor: string;
    lead_score: number;
  }>;
}

export type AnyBriefingEvent =
  | NewLeadEvent
  | ReviewEvent
  | NewProjectEvent
  | StatusChangeEvent
  | DigestEvent;

export type BriefingTimeFilter = "today" | "this_week" | "this_month";
export type BriefingRegionFilter = "all" | "ERCOT" | "CAISO" | "MISO";

export interface BriefingFilters {
  region: BriefingRegionFilter;
  timeRange: BriefingTimeFilter;
}

export interface BriefingStats {
  new_leads_this_week: number;
  awaiting_review: number;
  total_epcs_discovered: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/briefing-types.ts
git commit -m "feat: add briefing event type definitions"
```

---

## Task 2: StatBar Component

**Files:**
- Create: `frontend/src/components/briefing/StatBar.tsx`

- [ ] **Step 1: Create the StatBar component**

```tsx
// frontend/src/components/briefing/StatBar.tsx
"use client";

import { BriefingStats } from "@/lib/briefing-types";

interface StatBarProps {
  stats: BriefingStats;
}

export function StatBar({ stats }: StatBarProps) {
  return (
    <div className="flex items-center gap-3 text-sm font-sans text-[--text-secondary]">
      <span>
        <strong className="text-[--text-primary] font-medium">
          {stats.new_leads_this_week}
        </strong>{" "}
        new leads this week
      </span>
      <span className="text-[--border-default]">·</span>
      <span>
        <strong className="text-[--accent-amber] font-medium">
          {stats.awaiting_review}
        </strong>{" "}
        awaiting review
      </span>
      <span className="text-[--border-default]">·</span>
      <span>
        <strong className="text-[--text-primary] font-medium">
          {stats.total_epcs_discovered}
        </strong>{" "}
        EPCs discovered
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/StatBar.tsx
git commit -m "feat: add StatBar component for briefing summary metrics"
```

---

## Task 3: QuickFilters Component

**Files:**
- Create: `frontend/src/components/briefing/QuickFilters.tsx`

- [ ] **Step 1: Create the QuickFilters component**

```tsx
// frontend/src/components/briefing/QuickFilters.tsx
"use client";

import { BriefingFilters, BriefingRegionFilter, BriefingTimeFilter } from "@/lib/briefing-types";

interface QuickFiltersProps {
  filters: BriefingFilters;
  onChange: (filters: BriefingFilters) => void;
}

const REGIONS: { value: BriefingRegionFilter; label: string }[] = [
  { value: "all", label: "All Regions" },
  { value: "ERCOT", label: "ERCOT" },
  { value: "CAISO", label: "CAISO" },
  { value: "MISO", label: "MISO" },
];

const TIME_RANGES: { value: BriefingTimeFilter; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "this_week", label: "This Week" },
  { value: "this_month", label: "This Month" },
];

export function QuickFilters({ filters, onChange }: QuickFiltersProps) {
  return (
    <div className="flex items-center gap-2">
      {REGIONS.map((r) => (
        <button
          key={r.value}
          onClick={() => onChange({ ...filters, region: r.value })}
          className={`px-3 py-1.5 rounded-full text-xs font-sans font-medium transition-colors ${
            filters.region === r.value
              ? "bg-[--accent-amber-muted] text-[--accent-amber]"
              : "bg-[--surface-overlay] text-[--text-secondary] hover:text-[--text-primary]"
          }`}
        >
          {r.label}
        </button>
      ))}
      <div className="w-px h-4 bg-[--border-subtle] mx-1" />
      {TIME_RANGES.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange({ ...filters, timeRange: t.value })}
          className={`px-3 py-1.5 rounded-full text-xs font-sans font-medium transition-colors ${
            filters.timeRange === t.value
              ? "bg-[--accent-amber-muted] text-[--accent-amber]"
              : "bg-[--surface-overlay] text-[--text-secondary] hover:text-[--text-primary]"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/QuickFilters.tsx
git commit -m "feat: add QuickFilters chip component for briefing"
```

---

## Task 4: NewLeadCard Component

**Files:**
- Create: `frontend/src/components/briefing/cards/NewLeadCard.tsx`

- [ ] **Step 1: Create the NewLeadCard component**

```tsx
// frontend/src/components/briefing/cards/NewLeadCard.tsx
"use client";

import { useState } from "react";
import { NewLeadEvent } from "@/lib/briefing-types";
import { agentFetch } from "@/lib/agent-fetch";
import { toast } from "sonner";

interface NewLeadCardProps {
  event: NewLeadEvent;
  onExpand: (projectId: string) => void;
  onDismiss: (eventId: string) => void;
}

export function NewLeadCard({ event, onExpand, onDismiss }: NewLeadCardProps) {
  const [pushing, setPushing] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handlePushToHubspot() {
    setPushing(true);
    try {
      const res = await agentFetch("/api/hubspot/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: event.project_id }),
      });
      if (!res.ok) throw new Error("Push failed");
      toast.success("Pushed to HubSpot");
    } catch {
      toast.error("Failed to push to HubSpot");
    } finally {
      setPushing(false);
    }
  }

  function handleCopyOutreach() {
    navigator.clipboard.writeText(event.outreach_context);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("Outreach copied to clipboard");
  }

  return (
    <div className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-5">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-[--status-green]/15 text-[--status-green]">
              New Lead
            </span>
            <span className="text-xs font-mono text-[--text-tertiary]">
              {event.iso_region}
            </span>
          </div>
          <h3 className="font-serif text-lg text-[--text-primary]">
            {event.epc_contractor}
          </h3>
          <p className="text-sm text-[--text-secondary]">
            {event.project_name}
            {event.mw_capacity && ` · ${event.mw_capacity} MW`}
            {event.state && ` · ${event.state}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-sm font-mono font-medium ${
              event.lead_score >= 70
                ? "text-[--status-green]"
                : event.lead_score >= 40
                ? "text-[--accent-amber]"
                : "text-[--status-red]"
            }`}
          >
            {event.lead_score}
          </span>
        </div>
      </div>

      {/* Outreach context */}
      <p className="text-sm text-[--text-secondary] mb-4 leading-relaxed italic">
        &ldquo;{event.outreach_context}&rdquo;
      </p>

      {/* Contacts */}
      {event.contacts.length > 0 && (
        <div className="mb-4 space-y-2">
          {event.contacts.slice(0, 3).map((c) => (
            <div
              key={c.id}
              className="flex items-center gap-3 text-sm"
            >
              <span className="text-[--text-primary] font-medium">
                {c.full_name}
              </span>
              {c.title && (
                <span className="text-[--text-tertiary]">{c.title}</span>
              )}
              {c.linkedin_url && (
                <a
                  href={c.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[--accent-amber] hover:underline text-xs"
                >
                  LinkedIn
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-3 border-t border-[--border-subtle]">
        <button
          onClick={handlePushToHubspot}
          disabled={pushing}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--accent-amber] text-[--surface-primary] hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {pushing ? "Pushing…" : "Push to HubSpot"}
        </button>
        <button
          onClick={handleCopyOutreach}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--surface-overlay] text-[--text-secondary] hover:text-[--text-primary] transition-colors"
        >
          {copied ? "Copied!" : "Copy Outreach"}
        </button>
        <button
          onClick={() => onExpand(event.project_id)}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--surface-overlay] text-[--text-secondary] hover:text-[--text-primary] transition-colors ml-auto"
        >
          Details
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/cards/NewLeadCard.tsx
git commit -m "feat: add NewLeadCard with HubSpot push and outreach copy"
```

---

## Task 5: ReviewCard Component

**Files:**
- Create: `frontend/src/components/briefing/cards/ReviewCard.tsx`

- [ ] **Step 1: Create the ReviewCard component**

```tsx
// frontend/src/components/briefing/cards/ReviewCard.tsx
"use client";

import { useState } from "react";
import { ReviewEvent } from "@/lib/briefing-types";
import { agentFetch } from "@/lib/agent-fetch";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface ReviewCardProps {
  event: ReviewEvent;
  onDismiss: (eventId: string) => void;
}

export function ReviewCard({ event, onDismiss }: ReviewCardProps) {
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  async function handleReview(action: "accepted" | "rejected") {
    setSubmitting(true);
    try {
      const res = await agentFetch(`/api/discoveries/${event.discovery_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: action }),
      });
      if (!res.ok) throw new Error("Review failed");
      toast.success(action === "accepted" ? "Discovery approved" : "Discovery rejected");
      onDismiss(event.id);
    } catch {
      toast.error("Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  }

  function handleInvestigate() {
    const context = `Tell me more about ${event.epc_contractor} and their involvement with ${event.project_name}`;
    router.push(`/agent?context=${encodeURIComponent(context)}`);
  }

  const confidenceColor = {
    confirmed: "text-[--status-green]",
    likely: "text-[--accent-amber]",
    possible: "text-[--text-tertiary]",
    unknown: "text-[--text-tertiary]",
  }[event.confidence];

  return (
    <div className="bg-[--surface-raised] border border-[--accent-amber-muted] rounded-lg p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-[--accent-amber-muted] text-[--accent-amber]">
              Needs Review
            </span>
            <span className={`text-xs font-sans font-medium capitalize ${confidenceColor}`}>
              {event.confidence}
            </span>
          </div>
          <h3 className="font-serif text-lg text-[--text-primary]">
            {event.epc_contractor}
          </h3>
          <p className="text-sm text-[--text-secondary]">
            {event.project_name}
            {event.mw_capacity && ` · ${event.mw_capacity} MW`}
          </p>
        </div>
      </div>

      <p className="text-sm text-[--text-secondary] mb-4">
        {event.reasoning_summary}
        {event.source_url && (
          <>
            {" "}
            <a
              href={event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[--accent-amber] hover:underline"
            >
              Source
            </a>
          </>
        )}
      </p>

      <div className="flex items-center gap-3 pt-3 border-t border-[--border-subtle]">
        <button
          onClick={() => handleReview("accepted")}
          disabled={submitting}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--status-green]/15 text-[--status-green] hover:bg-[--status-green]/25 disabled:opacity-50 transition-colors"
        >
          Approve
        </button>
        <button
          onClick={() => handleReview("rejected")}
          disabled={submitting}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--status-red]/15 text-[--status-red] hover:bg-[--status-red]/25 disabled:opacity-50 transition-colors"
        >
          Reject
        </button>
        <button
          onClick={handleInvestigate}
          className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--surface-overlay] text-[--text-secondary] hover:text-[--text-primary] transition-colors ml-auto"
        >
          Investigate
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/cards/ReviewCard.tsx
git commit -m "feat: add ReviewCard with inline approve/reject and investigate"
```

---

## Task 6: AlertCard Component (New Project + Status Change)

**Files:**
- Create: `frontend/src/components/briefing/cards/AlertCard.tsx`

- [ ] **Step 1: Create the AlertCard component**

```tsx
// frontend/src/components/briefing/cards/AlertCard.tsx
"use client";

import { useState } from "react";
import { NewProjectEvent, StatusChangeEvent } from "@/lib/briefing-types";
import { agentFetch } from "@/lib/agent-fetch";
import { toast } from "sonner";

type AlertEvent = NewProjectEvent | StatusChangeEvent;

interface AlertCardProps {
  event: AlertEvent;
  onExpand: (projectId: string) => void;
  onDismiss: (eventId: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  unknown: "Unknown",
  pre_construction: "Pre-Construction",
  under_construction: "Under Construction",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function AlertCard({ event, onExpand, onDismiss }: AlertCardProps) {
  const [researching, setResearching] = useState(false);

  async function handleResearchEpc() {
    setResearching(true);
    try {
      const planRes = await agentFetch("/api/discover/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: event.project_id }),
      });
      if (!planRes.ok) throw new Error("Plan failed");
      const { plan } = await planRes.json();

      const execRes = await agentFetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: event.project_id, plan }),
      });
      if (!execRes.ok) throw new Error("Research failed");
      toast.success("EPC research started");
    } catch {
      toast.error("Failed to start research");
    } finally {
      setResearching(false);
    }
  }

  if (event.type === "new_project") {
    return (
      <div className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-4">
        <div className="flex items-start justify-between">
          <div>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-[--surface-overlay] text-[--text-tertiary] mb-1">
              New Project
            </span>
            <h3 className="font-serif text-base text-[--text-primary]">
              {event.project_name}
            </h3>
            <p className="text-sm text-[--text-secondary]">
              {event.developer && `${event.developer} · `}
              {event.mw_capacity && `${event.mw_capacity} MW · `}
              {event.iso_region}
              {event.state && ` · ${event.state}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleResearchEpc}
              disabled={researching}
              className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--accent-amber-muted] text-[--accent-amber] hover:bg-[--accent-amber]/25 disabled:opacity-50 transition-colors"
            >
              {researching ? "Researching…" : "Research EPC"}
            </button>
            <button
              onClick={() => onDismiss(event.id)}
              className="px-2 py-1.5 text-xs text-[--text-tertiary] hover:text-[--text-secondary] transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Status change card
  return (
    <div className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-[--surface-overlay] text-[--text-tertiary] mb-1">
            Status Change
          </span>
          <h3 className="font-serif text-base text-[--text-primary]">
            {event.project_name}
          </h3>
          <p className="text-sm text-[--text-secondary]">
            {STATUS_LABELS[event.previous_status] || event.previous_status}
            {" → "}
            <span className="text-[--text-primary] font-medium">
              {STATUS_LABELS[event.new_status] || event.new_status}
            </span>
            {event.expected_cod && ` · COD: ${event.expected_cod}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onExpand(event.project_id)}
            className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--surface-overlay] text-[--text-secondary] hover:text-[--text-primary] transition-colors"
          >
            Details
          </button>
          <button
            onClick={() => onDismiss(event.id)}
            className="px-2 py-1.5 text-xs text-[--text-tertiary] hover:text-[--text-secondary] transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/cards/AlertCard.tsx
git commit -m "feat: add AlertCard for new projects and status changes"
```

---

## Task 7: DigestCard Component

**Files:**
- Create: `frontend/src/components/briefing/cards/DigestCard.tsx`

- [ ] **Step 1: Create the DigestCard component**

```tsx
// frontend/src/components/briefing/cards/DigestCard.tsx
"use client";

import { DigestEvent } from "@/lib/briefing-types";

interface DigestCardProps {
  event: DigestEvent;
}

export function DigestCard({ event }: DigestCardProps) {
  return (
    <div className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-5">
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-[--surface-overlay] text-[--text-tertiary] mb-3">
        Weekly Digest
      </span>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <div className="text-2xl font-serif text-[--text-primary]">
            {event.new_projects_count}
          </div>
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider">
            New Projects
          </div>
        </div>
        <div>
          <div className="text-2xl font-serif text-[--text-primary]">
            {event.epcs_discovered_count}
          </div>
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider">
            EPCs Discovered
          </div>
        </div>
        <div>
          <div className="text-2xl font-serif text-[--text-primary]">
            {event.contacts_found_count}
          </div>
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider">
            Contacts Found
          </div>
        </div>
      </div>

      {event.top_leads.length > 0 && (
        <div className="pt-3 border-t border-[--border-subtle]">
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider mb-2">
            Top Leads
          </div>
          <div className="space-y-1.5">
            {event.top_leads.map((lead, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-[--text-primary]">
                  {lead.epc_contractor}
                  <span className="text-[--text-tertiary]">
                    {" "}— {lead.project_name}
                  </span>
                </span>
                <span
                  className={`font-mono text-xs ${
                    lead.lead_score >= 70
                      ? "text-[--status-green]"
                      : "text-[--accent-amber]"
                  }`}
                >
                  {lead.lead_score}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/cards/DigestCard.tsx
git commit -m "feat: add DigestCard for weekly summary"
```

---

## Task 8: ProjectPanel Slide-Over

**Files:**
- Create: `frontend/src/components/briefing/ProjectPanel.tsx`

- [ ] **Step 1: Create the ProjectPanel slide-over component**

This replaces the standalone `/projects/[id]` page. It fetches project + discovery data on open.

```tsx
// frontend/src/components/briefing/ProjectPanel.tsx
"use client";

import { useEffect, useState } from "react";
import { Project, EpcDiscovery } from "@/lib/types";
import { createBrowserClient } from "@supabase/ssr";
import { useRouter } from "next/navigation";

interface ProjectPanelProps {
  projectId: string | null;
  onClose: () => void;
}

export function ProjectPanel({ projectId, onClose }: ProjectPanelProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [discovery, setDiscovery] = useState<EpcDiscovery | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);

    const supabase = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );

    Promise.all([
      supabase.from("projects").select("*").eq("id", projectId).single(),
      supabase
        .from("epc_discoveries")
        .select("*")
        .eq("project_id", projectId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle(),
    ]).then(([projectRes, discoveryRes]) => {
      setProject(projectRes.data as Project | null);
      setDiscovery(discoveryRes.data as EpcDiscovery | null);
      setLoading(false);
    });
  }, [projectId]);

  if (!projectId) return null;

  function handleInvestigate() {
    const name = project?.project_name || "this project";
    const context = `Tell me everything about ${name}`;
    router.push(`/agent?context=${encodeURIComponent(context)}`);
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-[--surface-primary] border-l border-[--border-subtle] z-50 overflow-y-auto">
        <div className="p-6">
          {/* Close */}
          <button
            onClick={onClose}
            className="mb-4 text-sm text-[--text-tertiary] hover:text-[--text-secondary] transition-colors"
          >
            ← Back to Briefing
          </button>

          {loading ? (
            <div className="text-sm text-[--text-tertiary]">Loading…</div>
          ) : project ? (
            <div className="space-y-6">
              {/* Header */}
              <div>
                <h2 className="font-serif text-xl text-[--text-primary] mb-1">
                  {project.project_name || project.queue_id}
                </h2>
                <div className="flex items-center gap-2 flex-wrap text-xs font-sans text-[--text-tertiary]">
                  <span>{project.iso_region}</span>
                  {project.developer && (
                    <>
                      <span>·</span>
                      <span>{project.developer}</span>
                    </>
                  )}
                  {project.mw_capacity && (
                    <>
                      <span>·</span>
                      <span>{project.mw_capacity} MW</span>
                    </>
                  )}
                  {project.state && (
                    <>
                      <span>·</span>
                      <span>{project.state}</span>
                    </>
                  )}
                </div>
              </div>

              {/* Project details */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">
                    Status
                  </div>
                  <div className="text-[--text-primary]">
                    {project.construction_status?.replace(/_/g, " ") || "Unknown"}
                  </div>
                </div>
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">
                    Expected COD
                  </div>
                  <div className="text-[--text-primary]">
                    {project.expected_cod || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">
                    Lead Score
                  </div>
                  <div className="text-[--text-primary] font-mono">
                    {project.lead_score}
                  </div>
                </div>
                <div>
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-1">
                    Fuel Type
                  </div>
                  <div className="text-[--text-primary]">
                    {project.fuel_type || "—"}
                  </div>
                </div>
              </div>

              {/* EPC Discovery */}
              {discovery && (
                <div className="pt-4 border-t border-[--border-subtle]">
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-2">
                    EPC Discovery
                  </div>
                  <div className="text-[--text-primary] font-medium mb-1">
                    {discovery.epc_contractor}
                  </div>
                  <div className="text-sm text-[--text-secondary]">
                    Confidence:{" "}
                    <span className="capitalize">{discovery.confidence}</span>
                    {" · "}
                    Review:{" "}
                    <span className="capitalize">{discovery.review_status}</span>
                  </div>
                </div>
              )}

              {/* Location */}
              {(project.latitude || project.longitude) && (
                <div className="pt-4 border-t border-[--border-subtle]">
                  <div className="text-[--text-tertiary] text-xs uppercase tracking-wider mb-2">
                    Location
                  </div>
                  <p className="text-sm text-[--text-secondary]">
                    {project.county && `${project.county}, `}
                    {project.state}
                  </p>
                  {project.latitude && project.longitude && (
                    <a
                      href={`https://www.google.com/maps?q=${project.latitude},${project.longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-[--accent-amber] hover:underline mt-1 inline-block"
                    >
                      View on Google Maps
                    </a>
                  )}
                </div>
              )}

              {/* Actions */}
              <div className="pt-4 border-t border-[--border-subtle] flex gap-3">
                <button
                  onClick={handleInvestigate}
                  className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-[--accent-amber] text-[--surface-primary] hover:opacity-90 transition-opacity"
                >
                  Investigate in Chat
                </button>
              </div>
            </div>
          ) : (
            <div className="text-sm text-[--text-tertiary]">
              Project not found.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/ProjectPanel.tsx
git commit -m "feat: add ProjectPanel slide-over to replace project detail page"
```

---

## Task 9: BriefingFeed Container

**Files:**
- Create: `frontend/src/components/briefing/BriefingFeed.tsx`

- [ ] **Step 1: Create the BriefingFeed container component**

This is the main client component that manages card list, filters, dismiss state, and the project panel.

```tsx
// frontend/src/components/briefing/BriefingFeed.tsx
"use client";

import { useState, useMemo } from "react";
import {
  AnyBriefingEvent,
  BriefingFilters,
  BriefingStats,
} from "@/lib/briefing-types";
import { StatBar } from "./StatBar";
import { QuickFilters } from "./QuickFilters";
import { NewLeadCard } from "./cards/NewLeadCard";
import { ReviewCard } from "./cards/ReviewCard";
import { AlertCard } from "./cards/AlertCard";
import { DigestCard } from "./cards/DigestCard";
import { ProjectPanel } from "./ProjectPanel";

interface BriefingFeedProps {
  events: AnyBriefingEvent[];
  stats: BriefingStats;
}

function getTimeRangeStart(range: BriefingFilters["timeRange"]): Date {
  const now = new Date();
  switch (range) {
    case "today":
      return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    case "this_week": {
      const d = new Date(now);
      d.setDate(d.getDate() - d.getDay());
      d.setHours(0, 0, 0, 0);
      return d;
    }
    case "this_month":
      return new Date(now.getFullYear(), now.getMonth(), 1);
  }
}

export function BriefingFeed({ events: initialEvents, stats }: BriefingFeedProps) {
  const [filters, setFilters] = useState<BriefingFilters>({
    region: "all",
    timeRange: "this_week",
  });
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const filteredEvents = useMemo(() => {
    const rangeStart = getTimeRangeStart(filters.timeRange);

    return initialEvents.filter((e) => {
      // Time filter
      if (new Date(e.created_at) < rangeStart) return false;

      // Region filter
      if (filters.region !== "all") {
        if ("iso_region" in e && e.iso_region !== filters.region) return false;
      }

      return true;
    });
  }, [initialEvents, filters]);

  const activeEvents = filteredEvents.filter((e) => !dismissedIds.has(e.id));
  const dismissedEvents = filteredEvents.filter((e) => dismissedIds.has(e.id));

  // Sort by priority then created_at desc
  const sortedActive = [...activeEvents].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  function handleDismiss(eventId: string) {
    setDismissedIds((prev) => new Set([...prev, eventId]));
  }

  function renderCard(event: AnyBriefingEvent) {
    switch (event.type) {
      case "new_lead":
        return (
          <NewLeadCard
            key={event.id}
            event={event}
            onExpand={setExpandedProjectId}
            onDismiss={handleDismiss}
          />
        );
      case "review":
        return (
          <ReviewCard
            key={event.id}
            event={event}
            onDismiss={handleDismiss}
          />
        );
      case "new_project":
      case "status_change":
        return (
          <AlertCard
            key={event.id}
            event={event}
            onExpand={setExpandedProjectId}
            onDismiss={handleDismiss}
          />
        );
      case "digest":
        return <DigestCard key={event.id} event={event} />;
    }
  }

  return (
    <div className="space-y-6">
      <StatBar stats={stats} />
      <QuickFilters filters={filters} onChange={setFilters} />

      {/* Active cards */}
      <div className="space-y-3">
        {sortedActive.length === 0 ? (
          <div className="text-center py-16">
            <h3 className="font-serif text-lg text-[--text-primary] mb-2">
              You&apos;re all caught up
            </h3>
            <p className="text-sm text-[--text-tertiary]">
              No new events for the selected filters. Try expanding the time range.
            </p>
          </div>
        ) : (
          sortedActive.map(renderCard)
        )}
      </div>

      {/* Dismissed / History */}
      {dismissedEvents.length > 0 && (
        <div className="pt-4 border-t border-[--border-subtle]">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-xs font-sans text-[--text-tertiary] hover:text-[--text-secondary] transition-colors"
          >
            {showHistory ? "Hide" : "Show"} dismissed ({dismissedEvents.length})
          </button>
          {showHistory && (
            <div className="mt-3 space-y-3 opacity-60">
              {dismissedEvents.map(renderCard)}
            </div>
          )}
        </div>
      )}

      {/* Project detail slide-over */}
      <ProjectPanel
        projectId={expandedProjectId}
        onClose={() => setExpandedProjectId(null)}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/BriefingFeed.tsx
git commit -m "feat: add BriefingFeed container with filtering, dismiss, and card rendering"
```

---

## Task 10: Briefing Page + Backend Endpoint

**Files:**
- Create: `frontend/src/app/briefing/page.tsx`
- Modify: `frontend/src/app/page.tsx` (redirect to `/briefing`)

- [ ] **Step 1: Create the briefing page (server component)**

The briefing page fetches data from Supabase and assembles briefing events. This is a temporary client-side assembly approach — a proper backend endpoint can be built later for better performance.

```tsx
// frontend/src/app/briefing/page.tsx
import { createClient } from "@/lib/supabase/server";
import { BriefingFeed } from "@/components/briefing/BriefingFeed";
import {
  AnyBriefingEvent,
  BriefingStats,
  NewLeadEvent,
  ReviewEvent,
  NewProjectEvent,
} from "@/lib/briefing-types";

export const revalidate = 300; // 5 minutes

export default async function BriefingPage() {
  const supabase = await createClient();

  // Fetch data in parallel
  const [projectsRes, discoveriesRes] = await Promise.all([
    supabase
      .from("projects")
      .select("*")
      .order("lead_score", { ascending: false })
      .limit(500),
    supabase
      .from("epc_discoveries")
      .select("*, projects!inner(id, project_name, developer, mw_capacity, iso_region, state, lead_score, construction_status, expected_cod)")
      .order("created_at", { ascending: false })
      .limit(200),
  ]);

  const projects = projectsRes.data || [];
  const discoveries = discoveriesRes.data || [];

  // Assemble briefing events
  const events: AnyBriefingEvent[] = [];

  // New Lead events: accepted discoveries
  for (const d of discoveries) {
    if (d.review_status === "accepted" && d.projects) {
      const p = d.projects as any;
      const newLead: NewLeadEvent = {
        id: `lead-${d.id}`,
        type: "new_lead",
        priority: 1,
        created_at: d.updated_at || d.created_at,
        dismissed: false,
        project_id: p.id,
        project_name: p.project_name || p.id,
        developer: p.developer,
        mw_capacity: p.mw_capacity,
        iso_region: p.iso_region,
        state: p.state,
        lead_score: p.lead_score,
        epc_contractor: d.epc_contractor,
        confidence: d.confidence,
        discovery_id: d.id,
        entity_id: null,
        contacts: [], // Contacts fetched on-demand via actions API
        outreach_context: `${d.epc_contractor} was identified as the EPC for ${p.project_name || "this project"}${p.mw_capacity ? ` (${p.mw_capacity} MW)` : ""} in ${p.iso_region}.${p.expected_cod ? ` Expected COD: ${p.expected_cod}.` : ""}`,
      };
      events.push(newLead);
    }

    // Review events: pending discoveries
    if (d.review_status === "pending" && d.projects) {
      const p = d.projects as any;
      const reasoning = typeof d.reasoning === "object" && d.reasoning
        ? (d.reasoning as any).summary || JSON.stringify(d.reasoning).slice(0, 150)
        : String(d.reasoning || "").slice(0, 150);
      const firstSource = Array.isArray(d.sources) && d.sources[0]?.url;

      const review: ReviewEvent = {
        id: `review-${d.id}`,
        type: "review",
        priority: 2,
        created_at: d.created_at,
        dismissed: false,
        project_id: p.id,
        project_name: p.project_name || p.id,
        mw_capacity: p.mw_capacity,
        iso_region: p.iso_region,
        epc_contractor: d.epc_contractor,
        confidence: d.confidence,
        discovery_id: d.id,
        reasoning_summary: reasoning,
        source_url: firstSource || null,
      };
      events.push(review);
    }
  }

  // New Project events: projects created in the last 30 days without discoveries
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
  const discoveredProjectIds = new Set(discoveries.map((d: any) => d.project_id));

  for (const p of projects) {
    if (
      new Date(p.created_at) > thirtyDaysAgo &&
      !discoveredProjectIds.has(p.id)
    ) {
      const alert: NewProjectEvent = {
        id: `project-${p.id}`,
        type: "new_project",
        priority: 3,
        created_at: p.created_at,
        dismissed: false,
        project_id: p.id,
        project_name: p.project_name || p.queue_id,
        developer: p.developer,
        mw_capacity: p.mw_capacity,
        iso_region: p.iso_region,
        state: p.state,
        status: p.status,
      };
      events.push(alert);
    }
  }

  // Stats
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
  const stats: BriefingStats = {
    new_leads_this_week: events.filter(
      (e) => e.type === "new_lead" && new Date(e.created_at) > oneWeekAgo
    ).length,
    awaiting_review: events.filter((e) => e.type === "review").length,
    total_epcs_discovered: discoveries.length,
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="font-serif text-3xl text-[--text-primary] mb-2">
          Briefing
        </h1>
        <p className="text-sm text-[--text-secondary]">
          Your prioritized feed of leads, discoveries, and project updates.
        </p>
      </div>
      <BriefingFeed events={events} stats={stats} />
    </div>
  );
}
```

- [ ] **Step 2: Update root page to redirect to briefing**

```tsx
// frontend/src/app/page.tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/briefing");
}
```

- [ ] **Step 3: Verify the build compiles**

Run: `cd .worktrees/briefing-simplification/frontend && npx next build 2>&1 | tail -15`
Expected: Build succeeds with `/briefing` listed as a route.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/briefing/page.tsx frontend/src/app/page.tsx
git commit -m "feat: add Briefing page with server-side event assembly and redirect root"
```

---

## Task 11: Simplify Sidebar Navigation

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Read the current Sidebar.tsx to get exact line numbers**

Run: `cat -n frontend/src/components/Sidebar.tsx | head -80`

- [ ] **Step 2: Replace the navigation items array**

Change the nav items from 6 entries (Pipeline, Agent, Review Queue, Actions, Map, Settings) to 3 entries (Briefing, Investigate, Settings). The exact edit depends on the current structure, but the nav items should become:

```typescript
const navItems = [
  {
    label: "Briefing",
    href: "/briefing",
    icon: /* existing inbox/home icon */,
    match: (path: string) => path === "/" || path.startsWith("/briefing"),
  },
  {
    label: "Investigate",
    href: "/agent",
    icon: /* existing chat/message icon */,
    match: (path: string) => path.startsWith("/agent"),
  },
  {
    label: "Settings",
    href: "/settings",
    icon: /* existing settings/gear icon */,
    match: (path: string) => path.startsWith("/settings"),
  },
];
```

- [ ] **Step 3: Verify build compiles**

Run: `cd .worktrees/briefing-simplification/frontend && npx next build 2>&1 | tail -15`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: simplify Sidebar to 3 nav items — Briefing, Investigate, Settings"
```

---

## Task 12: Chat Context Pre-Loading

**Files:**
- Modify: `frontend/src/app/agent/page.tsx`
- Modify: `frontend/src/components/chat/ChatInterface.tsx`

- [ ] **Step 1: Read current ChatInterface.tsx and agent/page.tsx**

Get exact structure of the ChatInterface component — look for where `useChat` is called and where the initial message state is set.

- [ ] **Step 2: Add `initialContext` prop to ChatInterface**

Add an optional `initialContext?: string` prop. When present, auto-send it as the first user message on mount.

In ChatInterface.tsx, add to the component signature:

```typescript
interface ChatInterfaceProps {
  initialContext?: string;
}
```

Add a `useEffect` that sends the initial context as the first message when the component mounts with a non-empty `initialContext`:

```typescript
useEffect(() => {
  if (initialContext && messages.length === 0) {
    // Use the chat's submit handler to send the context as a user message
    handleSubmit(undefined, { data: { content: initialContext } });
  }
  // Run only on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

Note: The exact implementation depends on how `useChat` is configured. The engineer should read the current `handleSubmit` / `append` mechanism and use the appropriate method.

- [ ] **Step 3: Update agent/page.tsx to read search params**

```tsx
// frontend/src/app/agent/page.tsx
"use client";

import { useSearchParams } from "next/navigation";
import { ChatInterface } from "@/components/chat/ChatInterface";

export default function AgentPage() {
  const searchParams = useSearchParams();
  const context = searchParams.get("context") || undefined;

  return <ChatInterface initialContext={context} />;
}
```

- [ ] **Step 4: Verify build compiles**

Run: `cd .worktrees/briefing-simplification/frontend && npx next build 2>&1 | tail -15`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/agent/page.tsx frontend/src/components/chat/ChatInterface.tsx
git commit -m "feat: add context pre-loading to chat from briefing card investigate buttons"
```

---

## Task 13: Update Suggested Prompts

**Files:**
- Modify: `frontend/src/components/chat/SuggestedPrompts.tsx`

- [ ] **Step 1: Read current SuggestedPrompts.tsx**

Run: `cat -n frontend/src/components/chat/SuggestedPrompts.tsx`

- [ ] **Step 2: Replace prompt suggestions with sales-focused examples**

Replace the existing prompts array with:

```typescript
const PROMPTS = [
  "What's new in ERCOT this week?",
  "What do we know about Blattner Energy?",
  "Find contacts at Signal Energy",
  "Any projects over 300MW entering construction?",
  "Show me all pending reviews",
  "Which EPCs are most active in CAISO?",
];
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/SuggestedPrompts.tsx
git commit -m "feat: update suggested prompts for sales workflow"
```

---

## Task 14: Final Build Verification & Cleanup

- [ ] **Step 1: Run full build**

```bash
cd .worktrees/briefing-simplification/frontend && npx next build 2>&1
```

Expected: Build succeeds. The old routes (`/actions`, `/review`, `/map`, `/projects/[id]`) still exist in the filesystem but are no longer linked from navigation.

- [ ] **Step 2: Verify all new routes appear**

Check the build output for:
- `/briefing` — new page
- `/agent` — existing, modified
- `/settings` — existing, unchanged

- [ ] **Step 3: Run dev server and smoke test**

```bash
cd .worktrees/briefing-simplification/frontend && npx next dev &
sleep 5
curl -s http://localhost:3000/ -o /dev/null -w "%{http_code} %{redirect_url}"
```

Expected: 307 redirect to `/briefing`

- [ ] **Step 4: Commit any remaining changes**

```bash
git status
# If anything unstaged, add and commit
```
