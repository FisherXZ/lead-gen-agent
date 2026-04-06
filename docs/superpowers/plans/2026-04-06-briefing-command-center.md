# Briefing Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the passive Briefing event feed with a full-width command center dashboard featuring a pipeline funnel, inline review/research/contact actions, and 4 stacked panels.

**Architecture:** Server component fetches all data from Supabase in one Promise.all, passes structured props to a client BriefingDashboard. The dashboard renders PipelineFunnel + QuickNav + 4 action panels (NeedsReview, NeedsInvestigation, Contacts, RecentlyCompleted). Each panel is a focused client component with its own local state for interactions.

**Tech Stack:** Next.js 15 (App Router), Tailwind CSS v4, Supabase, React, TypeScript, Vitest + Testing Library

**Target branch:** `feature/briefing-command-center` from `main`

---

## Task 1: PipelineFunnel component

Pure presentational component that takes counts as props and renders a 5-stage horizontal tracker with arrows between stages.

**Files:**
- Create: `frontend/src/components/briefing/PipelineFunnel.tsx`
- Create: `frontend/src/components/briefing/PipelineFunnel.test.tsx`

- [ ] **Step 1: Create PipelineFunnel.tsx**

```tsx
// frontend/src/components/briefing/PipelineFunnel.tsx
"use client";

import Link from "next/link";

interface FunnelStage {
  label: string;
  count: number;
  href: string;
}

interface PipelineFunnelProps {
  totalProjects: number;
  researched: number;
  pendingReview: number;
  accepted: number;
  inCrm: number;
}

export default function PipelineFunnel({
  totalProjects,
  researched,
  pendingReview,
  accepted,
  inCrm,
}: PipelineFunnelProps) {
  const stages: FunnelStage[] = [
    { label: "Projects", count: totalProjects, href: "/projects" },
    { label: "Researched", count: researched, href: "/projects" },
    { label: "Pending Review", count: pendingReview, href: "/review" },
    { label: "Accepted", count: accepted, href: "/actions" },
    { label: "In CRM", count: inCrm, href: "/actions" },
  ];

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised px-4 py-4">
      {/* Desktop: horizontal row */}
      <div className="hidden sm:flex items-center justify-between">
        {stages.map((stage, i) => {
          const isPendingReview = i === 2;
          const isBottleneck = isPendingReview && stage.count > 0;

          return (
            <div key={stage.label} className="flex items-center">
              <Link
                href={stage.href}
                className={`group flex flex-col items-center rounded-md px-4 py-2 transition-colors hover:bg-surface-overlay ${
                  isBottleneck
                    ? "bg-accent-amber-muted border border-accent-amber-muted"
                    : ""
                }`}
              >
                <span
                  className={`font-serif text-[26px] leading-tight ${
                    isBottleneck
                      ? "text-accent-amber"
                      : stage.count === 0 && i === 4
                        ? "text-text-tertiary"
                        : i === 3
                          ? "text-status-green"
                          : "text-text-primary"
                  }`}
                >
                  {stage.count}
                </span>
                <span
                  className={`mt-0.5 text-[9px] font-medium uppercase tracking-widest ${
                    isBottleneck ? "text-accent-amber" : "text-text-tertiary"
                  }`}
                >
                  {stage.label}
                </span>
              </Link>
              {i < stages.length - 1 && (
                <span className="mx-2 text-text-tertiary" aria-hidden="true">
                  →
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile: vertical list */}
      <div className="flex flex-col gap-2 sm:hidden">
        {stages.map((stage, i) => {
          const isPendingReview = i === 2;
          const isBottleneck = isPendingReview && stage.count > 0;

          return (
            <Link
              key={stage.label}
              href={stage.href}
              className={`flex items-center justify-between rounded-md px-3 py-2 transition-colors hover:bg-surface-overlay ${
                isBottleneck
                  ? "bg-accent-amber-muted border border-accent-amber-muted"
                  : ""
              }`}
            >
              <span
                className={`text-[9px] font-medium uppercase tracking-widest ${
                  isBottleneck ? "text-accent-amber" : "text-text-tertiary"
                }`}
              >
                {stage.label}
              </span>
              <span
                className={`font-serif text-lg leading-tight ${
                  isBottleneck
                    ? "text-accent-amber"
                    : stage.count === 0 && i === 4
                      ? "text-text-tertiary"
                      : i === 3
                        ? "text-status-green"
                        : "text-text-primary"
                }`}
              >
                {stage.count}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create PipelineFunnel.test.tsx**

```tsx
// frontend/src/components/briefing/PipelineFunnel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PipelineFunnel from "./PipelineFunnel";

describe("PipelineFunnel", () => {
  it("renders all 5 stage counts", () => {
    render(
      <PipelineFunnel
        totalProjects={423}
        researched={64}
        pendingReview={61}
        accepted={3}
        inCrm={0}
      />
    );
    expect(screen.getByText("423")).toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(screen.getByText("61")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("renders all 5 stage labels", () => {
    render(
      <PipelineFunnel
        totalProjects={10}
        researched={5}
        pendingReview={3}
        accepted={2}
        inCrm={1}
      />
    );
    // Labels appear twice (desktop + mobile)
    expect(screen.getAllByText("Projects").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Pending Review").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("In CRM").length).toBeGreaterThanOrEqual(1);
  });

  it("renders arrows between stages on desktop", () => {
    render(
      <PipelineFunnel
        totalProjects={10}
        researched={5}
        pendingReview={3}
        accepted={2}
        inCrm={1}
      />
    );
    const arrows = screen.getAllByText("→");
    expect(arrows.length).toBe(4);
  });

  it("renders links to correct pages", () => {
    render(
      <PipelineFunnel
        totalProjects={10}
        researched={5}
        pendingReview={3}
        accepted={2}
        inCrm={0}
      />
    );
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/projects");
    expect(hrefs).toContain("/review");
    expect(hrefs).toContain("/actions");
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/PipelineFunnel.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/PipelineFunnel.tsx frontend/src/components/briefing/PipelineFunnel.test.tsx && git commit -m "feat(briefing): add PipelineFunnel component with 5-stage horizontal tracker"
```

---

## Task 2: QuickNav component

Simple link strip with pills for navigating to other pages.

**Files:**
- Create: `frontend/src/components/briefing/QuickNav.tsx`
- Create: `frontend/src/components/briefing/QuickNav.test.tsx`

- [ ] **Step 1: Create QuickNav.tsx**

```tsx
// frontend/src/components/briefing/QuickNav.tsx
"use client";

import Link from "next/link";

const NAV_LINKS = [
  { label: "Pipeline", href: "/projects" },
  { label: "Review Queue", href: "/review" },
  { label: "Actions", href: "/actions" },
  { label: "Map", href: "/map" },
  { label: "Solarina", href: "/agent" },
] as const;

export default function QuickNav() {
  return (
    <div className="flex flex-wrap gap-2">
      {NAV_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-md border border-border-subtle px-3 py-1 text-xs text-text-tertiary transition-colors hover:border-border-default hover:text-text-secondary"
        >
          {link.label} →
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create QuickNav.test.tsx**

```tsx
// frontend/src/components/briefing/QuickNav.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import QuickNav from "./QuickNav";

describe("QuickNav", () => {
  it("renders all 5 navigation links", () => {
    render(<QuickNav />);
    expect(screen.getByText("Pipeline →")).toBeInTheDocument();
    expect(screen.getByText("Review Queue →")).toBeInTheDocument();
    expect(screen.getByText("Actions →")).toBeInTheDocument();
    expect(screen.getByText("Map →")).toBeInTheDocument();
    expect(screen.getByText("Solarina →")).toBeInTheDocument();
  });

  it("links point to correct pages", () => {
    render(<QuickNav />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(5);
    expect(links[0]).toHaveAttribute("href", "/projects");
    expect(links[1]).toHaveAttribute("href", "/review");
    expect(links[2]).toHaveAttribute("href", "/actions");
    expect(links[3]).toHaveAttribute("href", "/map");
    expect(links[4]).toHaveAttribute("href", "/agent");
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/QuickNav.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/QuickNav.tsx frontend/src/components/briefing/QuickNav.test.tsx && git commit -m "feat(briefing): add QuickNav link strip component"
```

---

## Task 3: NeedsReviewPanel

Takes pending discoveries, renders cards with approve/reject buttons, handles local state for card removal on action.

**Files:**
- Create: `frontend/src/components/briefing/NeedsReviewPanel.tsx`
- Create: `frontend/src/components/briefing/NeedsReviewPanel.test.tsx`

- [ ] **Step 1: Create NeedsReviewPanel.tsx**

```tsx
// frontend/src/components/briefing/NeedsReviewPanel.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { agentFetch } from "@/lib/agent-fetch";

export interface PendingDiscovery {
  id: string;
  epc_contractor: string;
  confidence: string;
  reasoning_summary: string;
  project_id: string;
  project_name: string;
  mw_capacity: number | null;
  iso_region: string;
}

interface NeedsReviewPanelProps {
  discoveries: PendingDiscovery[];
  totalPending: number;
  onCountChange?: (delta: number) => void;
}

const CONFIDENCE_STYLES: Record<string, string> = {
  confirmed: "badge-green",
  likely: "badge-amber",
  possible: "badge-neutral",
};

export default function NeedsReviewPanel({
  discoveries: initialDiscoveries,
  totalPending,
  onCountChange,
}: NeedsReviewPanelProps) {
  const [discoveries, setDiscoveries] =
    useState<PendingDiscovery[]>(initialDiscoveries);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remaining = totalPending - (initialDiscoveries.length - discoveries.length);

  async function handleAction(id: string, action: "accepted" | "rejected") {
    setLoadingId(id);
    setError(null);
    try {
      const res = await agentFetch(`/api/discover/${id}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      if (res.ok) {
        setDiscoveries((prev) => prev.filter((d) => d.id !== id));
        onCountChange?.(-1);
      } else {
        setError(`Failed to ${action === "accepted" ? "approve" : "reject"}. Try again.`);
      }
    } catch {
      setError(`Failed to ${action === "accepted" ? "approve" : "reject"}. Try again.`);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Needs Review
          </h2>
          {remaining > 0 && (
            <span className="rounded-full bg-accent-amber-muted px-2 py-0.5 text-[10px] font-semibold text-accent-amber">
              {remaining}
            </span>
          )}
        </div>
        <Link
          href="/review"
          className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
        >
          View all →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="border-b border-border-subtle px-4 py-2">
          <p className="text-xs text-status-red">{error}</p>
        </div>
      )}

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {discoveries.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              All caught up. No pending reviews.
            </p>
          </div>
        ) : (
          discoveries.map((d) => {
            const isExpanded = expandedId === d.id;
            const isLoading = loadingId === d.id;
            const badgeStyle =
              CONFIDENCE_STYLES[d.confidence] || "badge-neutral";

            return (
              <div key={d.id} className="group">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() =>
                    setExpandedId(isExpanded ? null : d.id)
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setExpandedId(isExpanded ? null : d.id);
                    }
                  }}
                  className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay cursor-pointer"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-[13px] text-text-primary">
                        {d.epc_contractor}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${badgeStyle}`}
                      >
                        {d.confidence}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">
                      {d.project_name} · {d.mw_capacity ?? "—"}MW ·{" "}
                      {d.iso_region}
                    </p>
                  </div>

                  {/* Approve / Reject buttons */}
                  <div
                    className="ml-3 flex shrink-0 items-center gap-1.5"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => handleAction(d.id, "accepted")}
                      disabled={isLoading}
                      aria-label={`Approve ${d.epc_contractor}`}
                      className="rounded-md bg-status-green/15 px-2 py-1 text-xs font-medium text-status-green transition-colors hover:bg-status-green/25 disabled:opacity-50"
                    >
                      ✓
                    </button>
                    <button
                      onClick={() => handleAction(d.id, "rejected")}
                      disabled={isLoading}
                      aria-label={`Reject ${d.epc_contractor}`}
                      className="rounded-md bg-status-red/15 px-2 py-1 text-xs font-medium text-status-red transition-colors hover:bg-status-red/25 disabled:opacity-50"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                {/* Expanded reasoning */}
                {isExpanded && d.reasoning_summary && (
                  <div className="border-t border-border-subtle bg-surface-overlay px-4 py-3">
                    <p className="text-xs leading-relaxed text-text-secondary">
                      {d.reasoning_summary}
                    </p>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer: + N more */}
      {remaining > discoveries.length && discoveries.length > 0 && (
        <div className="border-t border-border-subtle px-4 py-2 text-center">
          <Link
            href="/review"
            className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
          >
            + {remaining - discoveries.length} more →
          </Link>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create NeedsReviewPanel.test.tsx**

```tsx
// frontend/src/components/briefing/NeedsReviewPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import NeedsReviewPanel, { PendingDiscovery } from "./NeedsReviewPanel";

vi.mock("@/lib/agent-fetch", () => ({
  agentFetch: vi.fn(),
}));

import { agentFetch } from "@/lib/agent-fetch";
const mockAgentFetch = vi.mocked(agentFetch);

const mockDiscoveries: PendingDiscovery[] = [
  {
    id: "d1",
    epc_contractor: "McCarthy Building",
    confidence: "confirmed",
    reasoning_summary: "Found on FERC filing",
    project_id: "p1",
    project_name: "Solar Ranch Alpha",
    mw_capacity: 200,
    iso_region: "ERCOT",
  },
  {
    id: "d2",
    epc_contractor: "Blattner Energy",
    confidence: "likely",
    reasoning_summary: "LinkedIn mention",
    project_id: "p2",
    project_name: "Sunbeam Beta",
    mw_capacity: 150,
    iso_region: "CAISO",
  },
];

describe("NeedsReviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders discovery cards with EPC name and confidence", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(screen.getByText("McCarthy Building")).toBeInTheDocument();
    expect(screen.getByText("Blattner Energy")).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.getByText("likely")).toBeInTheDocument();
  });

  it("renders project context line", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(
      screen.getByText("Solar Ranch Alpha · 200MW · ERCOT")
    ).toBeInTheDocument();
  });

  it("renders approve and reject buttons for each card", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(screen.getAllByText("✓")).toHaveLength(2);
    expect(screen.getAllByText("✕")).toHaveLength(2);
  });

  it("shows total pending count badge", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={61} />
    );
    expect(screen.getByText("61")).toBeInTheDocument();
  });

  it("shows View all link to /review", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    const viewAll = screen.getByText("View all →");
    expect(viewAll.closest("a")).toHaveAttribute("href", "/review");
  });

  it("shows empty state when no discoveries", () => {
    render(<NeedsReviewPanel discoveries={[]} totalPending={0} />);
    expect(
      screen.getByText("All caught up. No pending reviews.")
    ).toBeInTheDocument();
  });

  it("expands reasoning on card click", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(screen.queryByText("Found on FERC filing")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("McCarthy Building"));
    expect(screen.getByText("Found on FERC filing")).toBeInTheDocument();
  });

  it("removes card on successful approve", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);
    const onCountChange = vi.fn();

    render(
      <NeedsReviewPanel
        discoveries={mockDiscoveries}
        totalPending={10}
        onCountChange={onCountChange}
      />
    );

    const approveButtons = screen.getAllByText("✓");
    fireEvent.click(approveButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText("McCarthy Building")).not.toBeInTheDocument();
    });
    expect(onCountChange).toHaveBeenCalledWith(-1);
    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/discover/d1/review",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ action: "accepted" }),
      })
    );
  });

  it("removes card on successful reject", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);

    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );

    const rejectButtons = screen.getAllByText("✕");
    fireEvent.click(rejectButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText("McCarthy Building")).not.toBeInTheDocument();
    });
    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/discover/d1/review",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ action: "rejected" }),
      })
    );
  });

  it("shows error on failed action", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: false } as Response);

    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );

    fireEvent.click(screen.getAllByText("✓")[0]);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to approve. Try again.")
      ).toBeInTheDocument();
    });
    // Card should still be there
    expect(screen.getByText("McCarthy Building")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/NeedsReviewPanel.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/NeedsReviewPanel.tsx frontend/src/components/briefing/NeedsReviewPanel.test.tsx && git commit -m "feat(briefing): add NeedsReviewPanel with inline approve/reject"
```

---

## Task 4: NeedsInvestigationPanel

Takes unresearched projects, renders cards with Research button that triggers the 2-step plan/execute flow.

**Files:**
- Create: `frontend/src/components/briefing/NeedsInvestigationPanel.tsx`
- Create: `frontend/src/components/briefing/NeedsInvestigationPanel.test.tsx`

- [ ] **Step 1: Create NeedsInvestigationPanel.tsx**

```tsx
// frontend/src/components/briefing/NeedsInvestigationPanel.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { agentFetch } from "@/lib/agent-fetch";

export interface UnresearchedProject {
  id: string;
  project_name: string;
  iso_region: string;
  state: string | null;
  lead_score: number;
}

interface NeedsInvestigationPanelProps {
  projects: UnresearchedProject[];
  totalUnresearched: number;
}

export default function NeedsInvestigationPanel({
  projects: initialProjects,
  totalUnresearched,
}: NeedsInvestigationPanelProps) {
  const [projects, setProjects] =
    useState<UnresearchedProject[]>(initialProjects);
  const [researchingId, setResearchingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());

  const remaining =
    totalUnresearched - (initialProjects.length - projects.length);

  async function handleResearch(projectId: string) {
    setResearchingId(projectId);
    setError(null);
    try {
      // Step 1: Get research plan
      const planRes = await agentFetch("/api/discover/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!planRes.ok) {
        setError("Failed to generate research plan.");
        return;
      }
      const planData = await planRes.json();

      // Step 2: Execute research
      const execRes = await agentFetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, plan: planData.plan }),
      });
      if (execRes.ok) {
        setCompletedIds((prev) => new Set(prev).add(projectId));
      } else {
        setError("Research execution failed.");
      }
    } catch {
      setError("Research failed. Try again.");
    } finally {
      setResearchingId(null);
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
          Needs Investigation
        </h2>
        <Link
          href="/projects"
          className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
        >
          View pipeline →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="border-b border-border-subtle px-4 py-2">
          <p className="text-xs text-status-red">{error}</p>
        </div>
      )}

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {projects.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              All projects have been researched.
            </p>
          </div>
        ) : (
          projects.map((p) => {
            const isResearching = researchingId === p.id;
            const isCompleted = completedIds.has(p.id);

            return (
              <div
                key={p.id}
                className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay"
              >
                <Link href={`/projects/${p.id}`} className="min-w-0 flex-1">
                  <span className="font-serif text-[13px] text-text-primary">
                    {p.project_name || "Unnamed Project"}
                  </span>
                  <p className="mt-0.5 text-[10px] text-text-tertiary">
                    {p.iso_region}
                    {p.state ? ` · ${p.state}` : ""}
                    {p.lead_score > 0 ? ` · Score ${p.lead_score}` : ""}
                  </p>
                </Link>

                <div className="ml-3 shrink-0">
                  {isCompleted ? (
                    <span className="rounded-md bg-status-green/15 px-3 py-1 text-xs font-medium text-status-green">
                      Done
                    </span>
                  ) : (
                    <button
                      onClick={() => handleResearch(p.id)}
                      disabled={isResearching || researchingId !== null}
                      className="rounded-md bg-accent-amber-muted px-3 py-1 text-xs font-medium text-accent-amber transition-colors hover:bg-accent-amber/25 disabled:opacity-50"
                    >
                      {isResearching ? (
                        <span className="flex items-center gap-1.5">
                          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent-amber border-t-transparent" />
                          Researching
                        </span>
                      ) : (
                        "Research"
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      {remaining > projects.length && projects.length > 0 && (
        <div className="border-t border-border-subtle px-4 py-2 text-center">
          <span className="text-[10px] text-text-tertiary">
            Top by lead score · {remaining - projects.length} more
          </span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create NeedsInvestigationPanel.test.tsx**

```tsx
// frontend/src/components/briefing/NeedsInvestigationPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import NeedsInvestigationPanel, {
  UnresearchedProject,
} from "./NeedsInvestigationPanel";

vi.mock("@/lib/agent-fetch", () => ({
  agentFetch: vi.fn(),
}));

import { agentFetch } from "@/lib/agent-fetch";
const mockAgentFetch = vi.mocked(agentFetch);

const mockProjects: UnresearchedProject[] = [
  {
    id: "p1",
    project_name: "Solar Ranch Alpha",
    iso_region: "ERCOT",
    state: "TX",
    lead_score: 90,
  },
  {
    id: "p2",
    project_name: "Sunbeam Beta",
    iso_region: "CAISO",
    state: "CA",
    lead_score: 75,
  },
];

describe("NeedsInvestigationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders project cards with name and context", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    expect(screen.getByText("Solar Ranch Alpha")).toBeInTheDocument();
    expect(screen.getByText("Sunbeam Beta")).toBeInTheDocument();
    expect(screen.getByText("ERCOT · TX · Score 90")).toBeInTheDocument();
  });

  it("renders Research button for each project", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    expect(screen.getAllByText("Research")).toHaveLength(2);
  });

  it("renders View pipeline link", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    const link = screen.getByText("View pipeline →");
    expect(link.closest("a")).toHaveAttribute("href", "/projects");
  });

  it("renders project links to detail pages", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/projects/p1");
    expect(hrefs).toContain("/projects/p2");
  });

  it("shows empty state when no projects", () => {
    render(
      <NeedsInvestigationPanel projects={[]} totalUnresearched={0} />
    );
    expect(
      screen.getByText("All projects have been researched.")
    ).toBeInTheDocument();
  });

  it("calls plan then execute on Research click", async () => {
    mockAgentFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ plan: "test-plan" }),
      } as Response)
      .mockResolvedValueOnce({ ok: true } as Response);

    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );

    fireEvent.click(screen.getAllByText("Research")[0]);

    await waitFor(() => {
      expect(screen.getByText("Done")).toBeInTheDocument();
    });

    expect(mockAgentFetch).toHaveBeenCalledTimes(2);
    expect(mockAgentFetch).toHaveBeenNthCalledWith(
      1,
      "/api/discover/plan",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_id: "p1" }),
      })
    );
    expect(mockAgentFetch).toHaveBeenNthCalledWith(
      2,
      "/api/discover",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_id: "p1", plan: "test-plan" }),
      })
    );
  });

  it("shows error when plan step fails", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: false } as Response);

    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );

    fireEvent.click(screen.getAllByText("Research")[0]);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to generate research plan.")
      ).toBeInTheDocument();
    });
  });

  it("shows + N more footer when there are more projects", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={50} />
    );
    expect(screen.getByText("Top by lead score · 48 more")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/NeedsInvestigationPanel.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/NeedsInvestigationPanel.tsx frontend/src/components/briefing/NeedsInvestigationPanel.test.tsx && git commit -m "feat(briefing): add NeedsInvestigationPanel with 2-step research flow"
```

---

## Task 5: ContactsPanel

Takes EPCs needing contacts and CRM-ready leads, renders mixed cards with Find/Push buttons.

**Files:**
- Create: `frontend/src/components/briefing/ContactsPanel.tsx`
- Create: `frontend/src/components/briefing/ContactsPanel.test.tsx`

- [ ] **Step 1: Create ContactsPanel.tsx**

```tsx
// frontend/src/components/briefing/ContactsPanel.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { agentFetch } from "@/lib/agent-fetch";

export interface NeedContactsItem {
  discovery_id: string;
  entity_id: string;
  epc_contractor: string;
  project_name: string;
  project_id: string;
}

export interface CrmReadyItem {
  discovery_id: string;
  project_id: string;
  epc_contractor: string;
  project_name: string;
  contact_count: number;
}

interface ContactsPanelProps {
  needContacts: NeedContactsItem[];
  crmReady: CrmReadyItem[];
}

export default function ContactsPanel({
  needContacts: initialNeedContacts,
  crmReady: initialCrmReady,
}: ContactsPanelProps) {
  const [needContacts, setNeedContacts] =
    useState<NeedContactsItem[]>(initialNeedContacts);
  const [crmReady, setCrmReady] = useState<CrmReadyItem[]>(initialCrmReady);
  const [findingId, setFindingId] = useState<string | null>(null);
  const [pushingId, setPushingId] = useState<string | null>(null);
  const [syncedIds, setSyncedIds] = useState<Set<string>>(new Set());
  const [foundIds, setFoundIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  async function handleFindContacts(entityId: string, discoveryId: string) {
    setFindingId(discoveryId);
    setError(null);
    try {
      const res = await agentFetch("/api/contacts/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entityId }),
      });
      if (res.ok) {
        setFoundIds((prev) => new Set(prev).add(discoveryId));
      } else {
        setError("Contact discovery failed.");
      }
    } catch {
      setError("Contact discovery failed.");
    } finally {
      setFindingId(null);
    }
  }

  async function handlePushToHubSpot(projectId: string, discoveryId: string) {
    setPushingId(discoveryId);
    setError(null);
    try {
      const res = await agentFetch("/api/hubspot/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (res.ok) {
        setSyncedIds((prev) => new Set(prev).add(discoveryId));
      } else {
        setError("HubSpot push failed.");
      }
    } catch {
      setError("HubSpot push failed.");
    } finally {
      setPushingId(null);
    }
  }

  const totalCount = needContacts.length + crmReady.length;

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Contacts
          </h2>
          {totalCount > 0 && (
            <span className="rounded-full bg-accent-amber-muted px-2 py-0.5 text-[10px] font-semibold text-accent-amber">
              {totalCount}
            </span>
          )}
        </div>
        <Link
          href="/actions"
          className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
        >
          Actions →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="border-b border-border-subtle px-4 py-2">
          <p className="text-xs text-status-red">{error}</p>
        </div>
      )}

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {totalCount === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              No contacts needed right now.
            </p>
          </div>
        ) : (
          <>
            {/* CRM-ready items first */}
            {crmReady.map((item) => {
              const isSynced = syncedIds.has(item.discovery_id);
              const isPushing = pushingId === item.discovery_id;

              return (
                <div
                  key={`crm-${item.discovery_id}`}
                  className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-[13px] text-text-primary">
                        {item.epc_contractor}
                      </span>
                      <span className="rounded-full bg-accent-amber/15 px-2 py-0.5 text-[10px] font-semibold text-accent-amber">
                        {item.contact_count} contacts
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">
                      {item.project_name} · Ready for CRM push
                    </p>
                  </div>

                  <div className="ml-3 shrink-0">
                    {isSynced ? (
                      <span className="rounded-md bg-status-green/15 px-3 py-1 text-xs font-medium text-status-green">
                        Synced
                      </span>
                    ) : (
                      <button
                        onClick={() =>
                          handlePushToHubSpot(
                            item.project_id,
                            item.discovery_id
                          )
                        }
                        disabled={isPushing}
                        className="rounded-md bg-accent-amber px-3 py-1 text-xs font-medium text-surface-primary transition-colors hover:bg-accent-amber/90 disabled:opacity-50"
                      >
                        {isPushing ? (
                          <span className="flex items-center gap-1.5">
                            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-surface-primary border-t-transparent" />
                            Pushing
                          </span>
                        ) : (
                          "Push to HS"
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Need contacts items */}
            {needContacts.map((item) => {
              const isFound = foundIds.has(item.discovery_id);
              const isFinding = findingId === item.discovery_id;

              return (
                <div
                  key={`find-${item.discovery_id}`}
                  className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-[13px] text-text-primary">
                        {item.epc_contractor}
                      </span>
                      <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-[10px] font-medium text-text-tertiary">
                        0 contacts
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">
                      {item.project_name}
                    </p>
                  </div>

                  <div className="ml-3 shrink-0">
                    {isFound ? (
                      <span className="rounded-md bg-status-green/15 px-3 py-1 text-xs font-medium text-status-green">
                        Found
                      </span>
                    ) : (
                      <button
                        onClick={() =>
                          handleFindContacts(item.entity_id, item.discovery_id)
                        }
                        disabled={isFinding || findingId !== null}
                        className="rounded-md bg-accent-amber-muted px-3 py-1 text-xs font-medium text-accent-amber transition-colors hover:bg-accent-amber/25 disabled:opacity-50"
                      >
                        {isFinding ? (
                          <span className="flex items-center gap-1.5">
                            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent-amber border-t-transparent" />
                            Finding
                          </span>
                        ) : (
                          "Find"
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ContactsPanel.test.tsx**

```tsx
// frontend/src/components/briefing/ContactsPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ContactsPanel, {
  NeedContactsItem,
  CrmReadyItem,
} from "./ContactsPanel";

vi.mock("@/lib/agent-fetch", () => ({
  agentFetch: vi.fn(),
}));

import { agentFetch } from "@/lib/agent-fetch";
const mockAgentFetch = vi.mocked(agentFetch);

const mockNeedContacts: NeedContactsItem[] = [
  {
    discovery_id: "d1",
    entity_id: "e1",
    epc_contractor: "McCarthy Building",
    project_name: "Solar Alpha",
    project_id: "p1",
  },
  {
    discovery_id: "d2",
    entity_id: "e2",
    epc_contractor: "Blattner Energy",
    project_name: "Solar Beta",
    project_id: "p2",
  },
];

const mockCrmReady: CrmReadyItem[] = [
  {
    discovery_id: "d3",
    project_id: "p3",
    epc_contractor: "Mortenson",
    project_name: "Solar Gamma",
    contact_count: 3,
  },
];

describe("ContactsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders CRM-ready items before need-contacts items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    const names = screen.getAllByText(/McCarthy|Blattner|Mortenson/);
    expect(names[0]).toHaveTextContent("Mortenson");
    expect(names[1]).toHaveTextContent("McCarthy");
    expect(names[2]).toHaveTextContent("Blattner");
  });

  it("shows contact count badge for CRM-ready items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getByText("3 contacts")).toBeInTheDocument();
  });

  it("shows 0 contacts badge for need-contacts items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getAllByText("0 contacts")).toHaveLength(2);
  });

  it("renders Push to HS button for CRM-ready items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getByText("Push to HS")).toBeInTheDocument();
  });

  it("renders Find button for need-contacts items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getAllByText("Find")).toHaveLength(2);
  });

  it("shows total count badge", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows Synced after successful HubSpot push", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);

    render(
      <ContactsPanel
        needContacts={[]}
        crmReady={mockCrmReady}
      />
    );

    fireEvent.click(screen.getByText("Push to HS"));

    await waitFor(() => {
      expect(screen.getByText("Synced")).toBeInTheDocument();
    });

    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/hubspot/push",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_id: "p3" }),
      })
    );
  });

  it("shows Found after successful contact discovery", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);

    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={[]}
      />
    );

    fireEvent.click(screen.getAllByText("Find")[0]);

    await waitFor(() => {
      expect(screen.getByText("Found")).toBeInTheDocument();
    });

    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/contacts/discover",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ entity_id: "e1" }),
      })
    );
  });

  it("shows error on failed push", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: false } as Response);

    render(
      <ContactsPanel
        needContacts={[]}
        crmReady={mockCrmReady}
      />
    );

    fireEvent.click(screen.getByText("Push to HS"));

    await waitFor(() => {
      expect(screen.getByText("HubSpot push failed.")).toBeInTheDocument();
    });
  });

  it("shows empty state when no items", () => {
    render(<ContactsPanel needContacts={[]} crmReady={[]} />);
    expect(
      screen.getByText("No contacts needed right now.")
    ).toBeInTheDocument();
  });

  it("renders Actions link", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    const link = screen.getByText("Actions →");
    expect(link.closest("a")).toHaveAttribute("href", "/actions");
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/ContactsPanel.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/ContactsPanel.tsx frontend/src/components/briefing/ContactsPanel.test.tsx && git commit -m "feat(briefing): add ContactsPanel with Find + Push to HS actions"
```

---

## Task 6: RecentlyCompletedPanel

Takes accepted discoveries with optional HubSpot sync info, renders informational cards with green status indicators.

**Files:**
- Create: `frontend/src/components/briefing/RecentlyCompletedPanel.tsx`
- Create: `frontend/src/components/briefing/RecentlyCompletedPanel.test.tsx`

- [ ] **Step 1: Create RecentlyCompletedPanel.tsx**

```tsx
// frontend/src/components/briefing/RecentlyCompletedPanel.tsx
"use client";

import Link from "next/link";

export interface CompletedItem {
  discovery_id: string;
  project_id: string;
  epc_contractor: string;
  project_name: string;
  mw_capacity: number | null;
  contact_count: number;
  has_hubspot_sync: boolean;
  completed_at: string;
}

interface RecentlyCompletedPanelProps {
  items: CompletedItem[];
}

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default function RecentlyCompletedPanel({
  items,
}: RecentlyCompletedPanelProps) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Recently Completed
          </h2>
          {items.length > 0 && (
            <span className="rounded-full bg-status-green/15 px-2 py-0.5 text-[10px] font-semibold text-status-green">
              {items.length}
            </span>
          )}
        </div>
      </div>

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {items.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              No completed actions yet.
            </p>
          </div>
        ) : (
          items.map((item) => (
            <Link
              key={item.discovery_id}
              href={`/projects/${item.project_id}`}
              className="flex items-start gap-3 px-4 py-3 transition-colors"
            >
              {/* Green dot */}
              <span
                className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-status-green"
                aria-hidden="true"
              />

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-serif text-[13px] text-text-primary">
                    {item.epc_contractor}
                  </span>
                  {item.has_hubspot_sync ? (
                    <span className="rounded-full bg-status-green/15 px-2 py-0.5 text-[10px] font-semibold text-status-green">
                      In HubSpot
                    </span>
                  ) : (
                    <span className="rounded-full bg-status-green/10 px-2 py-0.5 text-[10px] font-medium text-status-green/70">
                      Accepted
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[10px] text-text-tertiary">
                  {item.project_name}
                  {item.mw_capacity ? ` · ${item.mw_capacity}MW` : ""}
                  {item.contact_count > 0
                    ? ` · ${item.contact_count} contacts`
                    : ""}
                  {" · "}
                  {timeAgo(item.completed_at)}
                </p>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create RecentlyCompletedPanel.test.tsx**

```tsx
// frontend/src/components/briefing/RecentlyCompletedPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import RecentlyCompletedPanel, { CompletedItem } from "./RecentlyCompletedPanel";

const now = new Date().toISOString();
const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();

const mockItems: CompletedItem[] = [
  {
    discovery_id: "d1",
    project_id: "p1",
    epc_contractor: "McCarthy Building",
    project_name: "Solar Alpha",
    mw_capacity: 200,
    contact_count: 3,
    has_hubspot_sync: true,
    completed_at: now,
  },
  {
    discovery_id: "d2",
    project_id: "p2",
    epc_contractor: "Blattner Energy",
    project_name: "Solar Beta",
    mw_capacity: 150,
    contact_count: 0,
    has_hubspot_sync: false,
    completed_at: twoHoursAgo,
  },
];

describe("RecentlyCompletedPanel", () => {
  it("renders EPC names", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("McCarthy Building")).toBeInTheDocument();
    expect(screen.getByText("Blattner Energy")).toBeInTheDocument();
  });

  it("shows In HubSpot badge for synced items", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("In HubSpot")).toBeInTheDocument();
  });

  it("shows Accepted badge for non-synced items", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("shows count badge in header", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders links to project detail pages", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/projects/p1");
    expect(links[1]).toHaveAttribute("href", "/projects/p2");
  });

  it("shows project context with MW and contacts", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(
      screen.getByText(/Solar Alpha · 200MW · 3 contacts/)
    ).toBeInTheDocument();
  });

  it("shows empty state when no items", () => {
    render(<RecentlyCompletedPanel items={[]} />);
    expect(
      screen.getByText("No completed actions yet.")
    ).toBeInTheDocument();
  });

  it("renders green dots for each item", () => {
    const { container } = render(
      <RecentlyCompletedPanel items={mockItems} />
    );
    const dots = container.querySelectorAll(".bg-status-green.rounded-full.h-1\\.5");
    expect(dots.length).toBe(2);
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/RecentlyCompletedPanel.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/RecentlyCompletedPanel.tsx frontend/src/components/briefing/RecentlyCompletedPanel.test.tsx && git commit -m "feat(briefing): add RecentlyCompletedPanel with status badges"
```

---

## Task 7: BriefingDashboard

Client shell component that composes PipelineFunnel + QuickNav + 4 panels into the 2x2 grid layout.

**Files:**
- Create: `frontend/src/components/briefing/BriefingDashboard.tsx`
- Create: `frontend/src/components/briefing/BriefingDashboard.test.tsx`

- [ ] **Step 1: Create BriefingDashboard.tsx**

```tsx
// frontend/src/components/briefing/BriefingDashboard.tsx
"use client";

import { useState, useCallback } from "react";
import PipelineFunnel from "./PipelineFunnel";
import QuickNav from "./QuickNav";
import NeedsReviewPanel, { PendingDiscovery } from "./NeedsReviewPanel";
import NeedsInvestigationPanel, {
  UnresearchedProject,
} from "./NeedsInvestigationPanel";
import ContactsPanel, {
  NeedContactsItem,
  CrmReadyItem,
} from "./ContactsPanel";
import RecentlyCompletedPanel, {
  CompletedItem,
} from "./RecentlyCompletedPanel";

export interface BriefingDashboardProps {
  funnel: {
    totalProjects: number;
    researched: number;
    pendingReview: number;
    accepted: number;
    inCrm: number;
  };
  pendingDiscoveries: PendingDiscovery[];
  totalPending: number;
  unresearchedProjects: UnresearchedProject[];
  totalUnresearched: number;
  needContacts: NeedContactsItem[];
  crmReady: CrmReadyItem[];
  recentlyCompleted: CompletedItem[];
}

export default function BriefingDashboard({
  funnel: initialFunnel,
  pendingDiscoveries,
  totalPending,
  unresearchedProjects,
  totalUnresearched,
  needContacts,
  crmReady,
  recentlyCompleted,
}: BriefingDashboardProps) {
  const [funnel, setFunnel] = useState(initialFunnel);

  const handleReviewCountChange = useCallback((delta: number) => {
    setFunnel((prev) => ({
      ...prev,
      pendingReview: Math.max(0, prev.pendingReview + delta),
      accepted: prev.accepted - delta, // approve decreases pending, increases accepted
    }));
  }, []);

  return (
    <div className="space-y-5">
      {/* Pipeline Funnel */}
      <PipelineFunnel
        totalProjects={funnel.totalProjects}
        researched={funnel.researched}
        pendingReview={funnel.pendingReview}
        accepted={funnel.accepted}
        inCrm={funnel.inCrm}
      />

      {/* Quick Nav */}
      <QuickNav />

      {/* 2x2 Action Grid */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <NeedsReviewPanel
          discoveries={pendingDiscoveries}
          totalPending={totalPending}
          onCountChange={handleReviewCountChange}
        />
        <NeedsInvestigationPanel
          projects={unresearchedProjects}
          totalUnresearched={totalUnresearched}
        />
        <ContactsPanel needContacts={needContacts} crmReady={crmReady} />
        <RecentlyCompletedPanel items={recentlyCompleted} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create BriefingDashboard.test.tsx**

```tsx
// frontend/src/components/briefing/BriefingDashboard.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import BriefingDashboard, {
  BriefingDashboardProps,
} from "./BriefingDashboard";

// Mock all child panels to isolate the shell
vi.mock("./PipelineFunnel", () => ({
  default: (props: any) => (
    <div data-testid="pipeline-funnel">
      Funnel: {props.totalProjects}/{props.pendingReview}
    </div>
  ),
}));

vi.mock("./QuickNav", () => ({
  default: () => <div data-testid="quick-nav">QuickNav</div>,
}));

vi.mock("./NeedsReviewPanel", () => ({
  default: (props: any) => (
    <div data-testid="needs-review">
      Review: {props.discoveries.length} items
    </div>
  ),
}));

vi.mock("./NeedsInvestigationPanel", () => ({
  default: (props: any) => (
    <div data-testid="needs-investigation">
      Investigation: {props.projects.length} items
    </div>
  ),
}));

vi.mock("./ContactsPanel", () => ({
  default: (props: any) => (
    <div data-testid="contacts-panel">
      Contacts: {props.needContacts.length + props.crmReady.length} items
    </div>
  ),
}));

vi.mock("./RecentlyCompletedPanel", () => ({
  default: (props: any) => (
    <div data-testid="recently-completed">
      Completed: {props.items.length} items
    </div>
  ),
}));

const mockProps: BriefingDashboardProps = {
  funnel: {
    totalProjects: 423,
    researched: 64,
    pendingReview: 61,
    accepted: 3,
    inCrm: 0,
  },
  pendingDiscoveries: [
    {
      id: "d1",
      epc_contractor: "McCarthy",
      confidence: "confirmed",
      reasoning_summary: "test",
      project_id: "p1",
      project_name: "Solar A",
      mw_capacity: 200,
      iso_region: "ERCOT",
    },
  ],
  totalPending: 61,
  unresearchedProjects: [
    {
      id: "p2",
      project_name: "Solar B",
      iso_region: "CAISO",
      state: "CA",
      lead_score: 80,
    },
  ],
  totalUnresearched: 350,
  needContacts: [
    {
      discovery_id: "d2",
      entity_id: "e1",
      epc_contractor: "Blattner",
      project_name: "Solar C",
      project_id: "p3",
    },
  ],
  crmReady: [],
  recentlyCompleted: [
    {
      discovery_id: "d3",
      project_id: "p4",
      epc_contractor: "Mortenson",
      project_name: "Solar D",
      mw_capacity: 300,
      contact_count: 2,
      has_hubspot_sync: false,
      completed_at: new Date().toISOString(),
    },
  ],
};

describe("BriefingDashboard", () => {
  it("renders all 6 sub-components", () => {
    render(<BriefingDashboard {...mockProps} />);
    expect(screen.getByTestId("pipeline-funnel")).toBeInTheDocument();
    expect(screen.getByTestId("quick-nav")).toBeInTheDocument();
    expect(screen.getByTestId("needs-review")).toBeInTheDocument();
    expect(screen.getByTestId("needs-investigation")).toBeInTheDocument();
    expect(screen.getByTestId("contacts-panel")).toBeInTheDocument();
    expect(screen.getByTestId("recently-completed")).toBeInTheDocument();
  });

  it("passes funnel counts to PipelineFunnel", () => {
    render(<BriefingDashboard {...mockProps} />);
    expect(screen.getByTestId("pipeline-funnel")).toHaveTextContent(
      "Funnel: 423/61"
    );
  });

  it("passes correct item counts to panels", () => {
    render(<BriefingDashboard {...mockProps} />);
    expect(screen.getByTestId("needs-review")).toHaveTextContent("1 items");
    expect(screen.getByTestId("needs-investigation")).toHaveTextContent(
      "1 items"
    );
    expect(screen.getByTestId("contacts-panel")).toHaveTextContent("1 items");
    expect(screen.getByTestId("recently-completed")).toHaveTextContent(
      "1 items"
    );
  });
});
```

- [ ] **Step 3: Verify**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/BriefingDashboard.test.tsx 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/components/briefing/BriefingDashboard.tsx frontend/src/components/briefing/BriefingDashboard.test.tsx && git commit -m "feat(briefing): add BriefingDashboard shell composing all panels into 2x2 grid"
```

---

## Task 8: Rewrite briefing/page.tsx

Server component with all Supabase queries in a single Promise.all, passes structured props to BriefingDashboard.

**Files:**
- Modify: `frontend/src/app/briefing/page.tsx`

- [ ] **Step 1: Rewrite page.tsx**

Replace the entire contents of `frontend/src/app/briefing/page.tsx` with:

```tsx
// frontend/src/app/briefing/page.tsx
import { createClient } from "@/lib/supabase/server";
import BriefingDashboard from "@/components/briefing/BriefingDashboard";
import type { PendingDiscovery } from "@/components/briefing/NeedsReviewPanel";
import type { UnresearchedProject } from "@/components/briefing/NeedsInvestigationPanel";
import type { NeedContactsItem, CrmReadyItem } from "@/components/briefing/ContactsPanel";
import type { CompletedItem } from "@/components/briefing/RecentlyCompletedPanel";

export const revalidate = 300; // 5 minute ISR

export default async function BriefingPage() {
  const supabase = await createClient();

  // ─── Parallel data fetch ─────────────────────────────────────────────
  const [
    projectCountResult,
    pendingResult,
    acceptedResult,
    allDiscoveriesCountResult,
    hubspotSyncResult,
  ] = await Promise.all([
    // 1. Total projects count
    supabase.from("projects").select("*", { count: "exact", head: true }),

    // 2. Pending discoveries (for review panel + funnel count)
    supabase
      .from("epc_discoveries")
      .select(
        "id, epc_contractor, confidence, reasoning, project_id, projects(id, project_name, mw_capacity, iso_region)"
      )
      .eq("review_status", "pending")
      .order("created_at", { ascending: false })
      .limit(5),

    // 3. Accepted discoveries (for contacts, completed, funnel)
    supabase
      .from("epc_discoveries")
      .select(
        "id, epc_contractor, confidence, entity_id, project_id, review_status, created_at, projects(id, project_name, mw_capacity, iso_region, state, lead_score)"
      )
      .eq("review_status", "accepted")
      .order("created_at", { ascending: false })
      .limit(50),

    // 4. All discoveries count (for "researched" funnel stage)
    supabase
      .from("epc_discoveries")
      .select("project_id", { count: "exact", head: true }),

    // 5. HubSpot sync log (for funnel + completed panel)
    supabase
      .from("hubspot_sync_log")
      .select("project_id, created_at")
      .order("created_at", { ascending: false })
      .limit(100),
  ]);

  // ─── Error handling ──────────────────────────────────────────────────
  if (projectCountResult.error) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="text-status-red">
          Failed to load data: {projectCountResult.error.message}
        </p>
      </main>
    );
  }

  // ─── Derive funnel counts ────────────────────────────────────────────
  const totalProjects = projectCountResult.count ?? 0;
  const pendingDiscoveriesRaw = pendingResult.data || [];
  const acceptedDiscoveries = acceptedResult.data || [];
  const hubspotSyncs = hubspotSyncResult.data || [];
  const hubspotProjectIds = new Set(hubspotSyncs.map((s: any) => s.project_id));

  // Count of pending discoveries (may be more than the 5 we fetched)
  const totalPending = pendingDiscoveriesRaw.length; // We'll refine below

  // For a more accurate pending count, do a separate count query
  const pendingCountResult = await supabase
    .from("epc_discoveries")
    .select("*", { count: "exact", head: true })
    .eq("review_status", "pending");
  const totalPendingCount = pendingCountResult.count ?? pendingDiscoveriesRaw.length;

  // Accepted count
  const acceptedCountResult = await supabase
    .from("epc_discoveries")
    .select("*", { count: "exact", head: true })
    .eq("review_status", "accepted");
  const acceptedCount = acceptedCountResult.count ?? acceptedDiscoveries.length;

  // Researched = distinct project_id count from epc_discoveries
  const researchedResult = await supabase.rpc("count_distinct_projects_discovered");
  // Fallback: use allDiscoveriesCountResult count if RPC doesn't exist
  const researched =
    typeof researchedResult.data === "number"
      ? researchedResult.data
      : allDiscoveriesCountResult.count ?? 0;

  const inCrm = new Set(hubspotSyncs.map((s: any) => s.project_id)).size;

  const funnel = {
    totalProjects,
    researched,
    pendingReview: totalPendingCount,
    accepted: acceptedCount,
    inCrm,
  };

  // ─── Build panel data ────────────────────────────────────────────────

  // Panel 1: Needs Review (top 5 pending)
  const pendingDiscoveries: PendingDiscovery[] = pendingDiscoveriesRaw.map(
    (d: any) => {
      const p = d.projects as any;
      const reasoningSummary =
        typeof d.reasoning === "string"
          ? d.reasoning.slice(0, 200)
          : d.reasoning?.summary?.slice(0, 200) ?? "";
      return {
        id: d.id,
        epc_contractor: d.epc_contractor,
        confidence: d.confidence,
        reasoning_summary: reasoningSummary,
        project_id: d.project_id,
        project_name: p?.project_name || "Unknown Project",
        mw_capacity: p?.mw_capacity ?? null,
        iso_region: p?.iso_region || "—",
      };
    }
  );

  // Panel 2: Needs Investigation (unresearched projects, top 5 by lead_score)
  const discoveredProjectIds = new Set(
    [...(pendingResult.data || []), ...acceptedDiscoveries].map(
      (d: any) => d.project_id
    )
  );
  // Fetch all discovered project IDs for accurate filtering
  const allDiscoveredResult = await supabase
    .from("epc_discoveries")
    .select("project_id");
  const allDiscoveredIds = new Set(
    (allDiscoveredResult.data || []).map((d: any) => d.project_id)
  );

  const unresearchedResult = await supabase
    .from("projects")
    .select("id, project_name, iso_region, state, lead_score")
    .not("id", "in", `(${[...allDiscoveredIds].join(",")})`)
    .order("lead_score", { ascending: false })
    .limit(5);

  const unresearchedProjects: UnresearchedProject[] = (
    unresearchedResult.data || []
  ).map((p: any) => ({
    id: p.id,
    project_name: p.project_name || "Unnamed Project",
    iso_region: p.iso_region,
    state: p.state,
    lead_score: p.lead_score ?? 0,
  }));

  const totalUnresearched = totalProjects - allDiscoveredIds.size;

  // Panel 3: Contacts
  // Need contacts: accepted discoveries with entity_id but 0 contacts
  const entitiesWithContacts = new Set<string>();
  if (acceptedDiscoveries.some((d: any) => d.entity_id)) {
    const entityIds = acceptedDiscoveries
      .filter((d: any) => d.entity_id)
      .map((d: any) => d.entity_id);
    const contactsResult = await supabase
      .from("contacts")
      .select("entity_id")
      .in("entity_id", entityIds);
    (contactsResult.data || []).forEach((c: any) =>
      entitiesWithContacts.add(c.entity_id)
    );
  }

  const needContacts: NeedContactsItem[] = acceptedDiscoveries
    .filter(
      (d: any) => d.entity_id && !entitiesWithContacts.has(d.entity_id)
    )
    .slice(0, 5)
    .map((d: any) => {
      const p = d.projects as any;
      return {
        discovery_id: d.id,
        entity_id: d.entity_id,
        epc_contractor: d.epc_contractor,
        project_name: p?.project_name || "Unknown Project",
        project_id: d.project_id,
      };
    });

  // CRM-ready: accepted with entity that HAS contacts but NOT in hubspot_sync_log
  const crmReady: CrmReadyItem[] = [];
  const entitiesWithContactsList = acceptedDiscoveries.filter(
    (d: any) =>
      d.entity_id &&
      entitiesWithContacts.has(d.entity_id) &&
      !hubspotProjectIds.has(d.project_id)
  );
  // Get contact counts for CRM-ready items
  for (const d of entitiesWithContactsList.slice(0, 3)) {
    const countResult = await supabase
      .from("contacts")
      .select("*", { count: "exact", head: true })
      .eq("entity_id", (d as any).entity_id);
    const p = (d as any).projects as any;
    crmReady.push({
      discovery_id: (d as any).id,
      project_id: (d as any).project_id,
      epc_contractor: (d as any).epc_contractor,
      project_name: p?.project_name || "Unknown Project",
      contact_count: countResult.count ?? 0,
    });
  }

  // Panel 4: Recently Completed (accepted discoveries, most recent)
  const recentlyCompleted: CompletedItem[] = acceptedDiscoveries
    .slice(0, 5)
    .map((d: any) => {
      const p = d.projects as any;
      const contactCount = entitiesWithContacts.has(d.entity_id) ? 1 : 0; // Approximate
      return {
        discovery_id: d.id,
        project_id: d.project_id,
        epc_contractor: d.epc_contractor,
        project_name: p?.project_name || "Unknown Project",
        mw_capacity: p?.mw_capacity ?? null,
        contact_count: contactCount,
        has_hubspot_sync: hubspotProjectIds.has(d.project_id),
        completed_at: d.created_at,
      };
    });

  // ─── Render ──────────────────────────────────────────────────────────
  return (
    <main className="mx-auto max-w-7xl px-4 pt-12 pb-16 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="font-serif text-3xl tracking-tight text-text-primary">
          Briefing
        </h1>
        <p className="mt-1 text-sm text-text-tertiary">
          Your command center for leads, reviews, and pipeline actions.
        </p>
      </div>

      <BriefingDashboard
        funnel={funnel}
        pendingDiscoveries={pendingDiscoveries}
        totalPending={totalPendingCount}
        unresearchedProjects={unresearchedProjects}
        totalUnresearched={totalUnresearched}
        needContacts={needContacts}
        crmReady={crmReady}
        recentlyCompleted={recentlyCompleted}
      />
    </main>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx next build 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add frontend/src/app/briefing/page.tsx && git commit -m "feat(briefing): rewrite page.tsx as command center with Supabase queries + BriefingDashboard"
```

---

## Task 9: Cleanup

Delete old briefing components and types that are no longer used.

**Files to delete:**
- `frontend/src/components/briefing/BriefingFeed.tsx`
- `frontend/src/components/briefing/BriefingFeed.test.tsx`
- `frontend/src/components/briefing/StatBar.tsx`
- `frontend/src/components/briefing/StatBar.test.tsx`
- `frontend/src/components/briefing/QuickFilters.tsx`
- `frontend/src/components/briefing/QuickFilters.test.tsx`
- `frontend/src/components/briefing/ProjectPanel.tsx`
- `frontend/src/components/briefing/ProjectPanel.test.tsx`
- `frontend/src/components/briefing/cards/AlertCard.tsx`
- `frontend/src/components/briefing/cards/AlertCard.test.tsx`
- `frontend/src/components/briefing/cards/DigestCard.tsx`
- `frontend/src/components/briefing/cards/DigestCard.test.tsx`
- `frontend/src/components/briefing/cards/NewLeadCard.tsx`
- `frontend/src/components/briefing/cards/NewLeadCard.test.tsx`
- `frontend/src/components/briefing/cards/ReviewCard.tsx`
- `frontend/src/components/briefing/cards/ReviewCard.test.tsx`
- `frontend/src/lib/briefing-types.ts`

- [ ] **Step 1: Check for remaining imports of old files**

Before deleting, verify no other files import the old components:

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && grep -r "briefing-types\|BriefingFeed\|StatBar\|QuickFilters\|ProjectPanel\|AlertCard\|DigestCard\|NewLeadCard\|ReviewCard" frontend/src --include="*.ts" --include="*.tsx" -l | grep -v "components/briefing/" | grep -v "briefing-types.ts"
```

The only file that should appear is `frontend/src/app/briefing/page.tsx` (which was already rewritten in Task 8 and no longer imports these). If other files appear, update their imports before proceeding.

- [ ] **Step 2: Delete old files**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && rm -f \
  frontend/src/components/briefing/BriefingFeed.tsx \
  frontend/src/components/briefing/BriefingFeed.test.tsx \
  frontend/src/components/briefing/StatBar.tsx \
  frontend/src/components/briefing/StatBar.test.tsx \
  frontend/src/components/briefing/QuickFilters.tsx \
  frontend/src/components/briefing/QuickFilters.test.tsx \
  frontend/src/components/briefing/ProjectPanel.tsx \
  frontend/src/components/briefing/ProjectPanel.test.tsx \
  frontend/src/components/briefing/cards/AlertCard.tsx \
  frontend/src/components/briefing/cards/AlertCard.test.tsx \
  frontend/src/components/briefing/cards/DigestCard.tsx \
  frontend/src/components/briefing/cards/DigestCard.test.tsx \
  frontend/src/components/briefing/cards/NewLeadCard.tsx \
  frontend/src/components/briefing/cards/NewLeadCard.test.tsx \
  frontend/src/components/briefing/cards/ReviewCard.tsx \
  frontend/src/components/briefing/cards/ReviewCard.test.tsx \
  frontend/src/lib/briefing-types.ts
```

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && rmdir frontend/src/components/briefing/cards 2>/dev/null || true
```

- [ ] **Step 3: Verify all tests pass**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx vitest run src/components/briefing/ 2>&1 | tail -20
```

- [ ] **Step 4: Verify build**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent/frontend && npx next build 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fisher/Documents/GitHub2026/lead-gen-agent && git add -A frontend/src/components/briefing/ frontend/src/lib/briefing-types.ts && git commit -m "chore(briefing): delete old BriefingFeed, StatBar, QuickFilters, cards, and briefing-types"
```

---

## Summary

| Task | Component | Files | Key interaction |
|------|-----------|-------|-----------------|
| 1 | PipelineFunnel | 2 new | Clickable 5-stage funnel with bottleneck highlight |
| 2 | QuickNav | 2 new | Link pills to Pipeline, Review, Actions, Map, Solarina |
| 3 | NeedsReviewPanel | 2 new | Approve/reject via `PATCH /api/discover/{id}/review` |
| 4 | NeedsInvestigationPanel | 2 new | Research via `POST /api/discover/plan` + `POST /api/discover` |
| 5 | ContactsPanel | 2 new | Find via `POST /api/contacts/discover`, Push via `POST /api/hubspot/push` |
| 6 | RecentlyCompletedPanel | 2 new | Informational cards with green status dots |
| 7 | BriefingDashboard | 2 new | Client shell composing all panels in 2x2 grid |
| 8 | page.tsx rewrite | 1 modified | Server component with Supabase queries + props |
| 9 | Cleanup | 17 deleted | Remove old BriefingFeed, StatBar, cards, types |

**Total: 14 files created, 1 modified, 17 deleted.**

---

## Plain English

**What are we building?**
We are replacing the Briefing page -- currently a passive news feed that says "You're all caught up" even when 61 discoveries are waiting -- with a full-width command center. The new page has a pipeline funnel at the top showing exactly where everything stands (423 projects, 64 researched, 61 pending review, 3 accepted, 0 in CRM), followed by four action panels where you can approve/reject discoveries, kick off research, find contacts, and push leads to HubSpot. All without leaving the page.

**Why this structure?**
Each panel is a standalone component with its own local state, so approve/reject in the review panel does not re-render the contacts panel. The server component does one big data fetch and passes structured props down, keeping the client components lightweight. This matches the pattern used in the Review Queue and Actions pages.

**What gets deleted?**
The old BriefingFeed, StatBar, QuickFilters, ProjectPanel, all 4 card types, and the briefing-types file. 17 files total. They are fully replaced by the 7 new components.
