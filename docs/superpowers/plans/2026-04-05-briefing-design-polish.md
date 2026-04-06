# Briefing Design Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply 7 design polish fixes to the briefing components to maximize visual hierarchy, scannability, and editorial feel per DESIGN.md.

**Architecture:** Pure CSS/Tailwind class changes across existing components. No logic changes, no new files, no type changes.

**Tech Stack:** Tailwind CSS, CSS custom properties from DESIGN.md

**Worktree:** `.worktrees/briefing-simplification` (branch: `feature/briefing-simplification`)

---

## Task 1: Narrow page width + page header polish

**Files:**
- Modify: `frontend/src/app/briefing/page.tsx:36,143-148`

- [ ] **Step 1: Change max-w-7xl to max-w-2xl and polish the header**

In `briefing/page.tsx`, change the error container and main container:

Line 36: `max-w-7xl` → `max-w-2xl`
Line 143: `max-w-7xl` → `max-w-2xl`, add more top padding
Lines 144-148: Enlarge heading, add subtitle

```tsx
// Line 36 error state
<main className="mx-auto max-w-2xl px-4 py-10 sm:px-6">

// Lines 143-151
<main className="mx-auto max-w-2xl px-4 pt-12 pb-16 sm:px-6">
  <div className="mb-10">
    <h1 className="text-3xl font-serif text-[--text-primary] tracking-tight">
      Briefing
    </h1>
    <p className="mt-1 text-sm text-[--text-tertiary]">
      Your prioritized leads, discoveries, and project updates.
    </p>
  </div>
  <BriefingFeed events={events} stats={stats} />
</main>
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx next build 2>&1 | tail -10`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/briefing/page.tsx
git commit -m "style: narrow briefing to newsletter width, polish page header"
```

---

## Task 2: Card visual hierarchy differentiation

**Files:**
- Modify: `frontend/src/components/briefing/cards/NewLeadCard.tsx:43`
- Modify: `frontend/src/components/briefing/cards/AlertCard.tsx:54,91`
- Modify: `frontend/src/components/briefing/cards/DigestCard.tsx:11`

- [ ] **Step 1: Add left amber border to NewLeadCard**

In `NewLeadCard.tsx` line 43, change the card container class:
```
OLD: className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-5"
NEW: className="bg-[--surface-raised] border border-[--border-subtle] border-l-2 border-l-[--accent-amber] rounded-lg p-5"
```

- [ ] **Step 2: Remove border from AlertCards, use lighter treatment**

In `AlertCard.tsx` line 54 (new_project variant):
```
OLD: className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-4"
NEW: className="bg-[--surface-raised] rounded-lg p-4"
```

In `AlertCard.tsx` line 91 (status_change variant):
```
OLD: className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-4"
NEW: className="bg-[--surface-raised] rounded-lg p-4"
```

- [ ] **Step 3: Give DigestCard a distinct background**

In `DigestCard.tsx` line 11:
```
OLD: className="bg-[--surface-raised] border border-[--border-subtle] rounded-lg p-5"
NEW: className="bg-[--surface-overlay] rounded-lg p-5"
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `cd frontend && npx vitest run`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/briefing/cards/NewLeadCard.tsx frontend/src/components/briefing/cards/AlertCard.tsx frontend/src/components/briefing/cards/DigestCard.tsx
git commit -m "style: differentiate card types visually — amber border for leads, borderless alerts, overlay digest"
```

---

## Task 3: Outreach quote styling

**Files:**
- Modify: `frontend/src/components/briefing/cards/NewLeadCard.tsx:78-80`

- [ ] **Step 1: Replace italic quote with pull-quote treatment**

In `NewLeadCard.tsx` lines 78-80, change:

```tsx
// OLD
<p className="text-sm text-[--text-secondary] mb-4 leading-relaxed italic">
  &ldquo;{event.outreach_context}&rdquo;
</p>

// NEW
{event.outreach_context && (
  <div className="mb-4 border-l-2 border-[--border-default] pl-4">
    <p className="text-sm text-[--text-secondary] leading-relaxed">
      {event.outreach_context}
    </p>
  </div>
)}
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest run`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/cards/NewLeadCard.tsx
git commit -m "style: use pull-quote treatment for outreach context"
```

---

## Task 4: StatBar emphasis

**Files:**
- Modify: `frontend/src/components/briefing/StatBar.tsx`

- [ ] **Step 1: Increase stat number size and add bottom spacing**

Replace the full StatBar return:

```tsx
return (
  <div className="flex items-baseline gap-6 pb-6 border-b border-[--border-subtle]">
    <div>
      <span className="text-2xl font-serif text-[--text-primary]">
        {stats.new_leads_this_week}
      </span>
      <span className="ml-2 text-sm text-[--text-secondary]">
        new leads this week
      </span>
    </div>
    <div>
      <span className="text-2xl font-serif text-[--accent-amber]">
        {stats.awaiting_review}
      </span>
      <span className="ml-2 text-sm text-[--text-secondary]">
        awaiting review
      </span>
    </div>
    <div>
      <span className="text-2xl font-serif text-[--text-primary]">
        {stats.total_epcs_discovered}
      </span>
      <span className="ml-2 text-sm text-[--text-secondary]">
        EPCs discovered
      </span>
    </div>
  </div>
);
```

- [ ] **Step 2: Update StatBar tests to match new structure**

The tests look for text content, which hasn't changed — the same numbers and labels render. But the `strong` tags are gone. Check if tests still pass first. If they fail, update the selectors.

Run: `cd frontend && npx vitest run src/components/briefing/StatBar.test.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/StatBar.tsx
git commit -m "style: enlarge stat numbers with serif font, add bottom border"
```

---

## Task 5: ProjectPanel slide-in transition

**Files:**
- Modify: `frontend/src/components/briefing/ProjectPanel.tsx:58`

- [ ] **Step 1: Add transition classes to the panel**

In `ProjectPanel.tsx` line 58, add transition:

```
OLD: className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-[--surface-primary] border-l border-[--border-subtle] z-50 overflow-y-auto"
NEW: className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-[--surface-primary] border-l border-[--border-subtle] z-50 overflow-y-auto transition-transform duration-200 ease-out"
```

And add fade to backdrop (line 55-57):
```
OLD: className="fixed inset-0 bg-black/40 z-40"
NEW: className="fixed inset-0 bg-black/40 z-40 transition-opacity duration-200"
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/ProjectPanel.tsx
git commit -m "style: add slide-in transition to ProjectPanel"
```

---

## Task 6: Empty state polish

**Files:**
- Modify: `frontend/src/components/briefing/BriefingFeed.tsx:112-119`

- [ ] **Step 1: Enlarge empty state and add CTA**

In `BriefingFeed.tsx` lines 112-119, replace:

```tsx
// OLD
<div className="text-center py-16">
  <h3 className="font-serif text-lg text-[--text-primary] mb-2">
    You&apos;re all caught up
  </h3>
  <p className="text-sm text-[--text-tertiary]">
    No new events for the selected filters. Try expanding the time range.
  </p>
</div>

// NEW
<div className="text-center py-20">
  <h3 className="font-serif text-2xl text-[--text-primary] mb-3">
    You&apos;re all caught up
  </h3>
  <p className="text-sm text-[--text-tertiary] mb-6">
    No new events for the selected filters. Try expanding the time range.
  </p>
  <a
    href="/agent"
    className="text-sm text-[--accent-amber] hover:underline"
  >
    Start investigating →
  </a>
</div>
```

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx vitest run`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/BriefingFeed.tsx
git commit -m "style: polish empty state with larger heading and investigate CTA"
```

---

## Task 7: Final build + test verification

- [ ] **Step 1: Run full test suite**

Run: `cd frontend && npx vitest run`
Expected: All tests pass.

- [ ] **Step 2: Run full build**

Run: `cd frontend && npx next build 2>&1 | tail -15`
Expected: Build succeeds.
