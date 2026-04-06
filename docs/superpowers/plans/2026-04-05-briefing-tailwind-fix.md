# Briefing Page Tailwind v4 Class Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 8 Briefing components that use broken `[--css-var]` arbitrary value syntax and convert them to proper Tailwind v4 utility classes, restoring the visual design that matches the rest of the app.

**Architecture:** The Briefing components were written with Tailwind v3-style arbitrary CSS variable references (`text-[--text-primary]`, `bg-[--surface-raised]`). The rest of the app (Actions, Review, Settings pages) correctly uses Tailwind v4 theme utility classes (`text-text-primary`, `bg-surface-raised`). The fix is a mechanical find-and-replace across 8 files, converting ~120 broken class references to their working equivalents. No logic changes, no restructuring — just class name corrections.

**Tech Stack:** Next.js 15, Tailwind CSS v4 (`@theme inline`), React, TypeScript

---

## Root Cause

In `frontend/src/app/globals.css`, the Tailwind v4 `@theme inline` block defines:
```css
--color-surface-raised: #252320;
--color-text-primary: #FFF8EB;
--color-accent-amber: #E8A230;
```

This generates utility classes like `bg-surface-raised`, `text-text-primary`, `text-accent-amber`.

The Briefing components instead use arbitrary value syntax like `bg-[--surface-raised]`, `text-[--text-primary]` which looks for raw CSS variables `--surface-raised`, `--text-primary` that don't exist (they're `--color-surface-raised`, etc.). Result: styles silently fail to apply.

**Working pages for reference:** `frontend/src/app/actions/page.tsx`, `frontend/src/app/review/page.tsx` — these use the correct Tailwind v4 utility class pattern.

## Mapping Table

Every `[--X]` reference maps to a Tailwind v4 utility class:

| Broken Pattern | Correct Pattern |
|---|---|
| `bg-[--surface-primary]` | `bg-surface-primary` |
| `bg-[--surface-raised]` | `bg-surface-raised` |
| `bg-[--surface-overlay]` | `bg-surface-overlay` |
| `text-[--text-primary]` | `text-text-primary` |
| `text-[--text-secondary]` | `text-text-secondary` |
| `text-[--text-tertiary]` | `text-text-tertiary` |
| `text-[--accent-amber]` | `text-accent-amber` |
| `text-[--status-green]` | `text-status-green` |
| `text-[--status-red]` | `text-status-red` |
| `border-[--border-subtle]` | `border-border-subtle` |
| `border-[--border-default]` | `border-border-default` |
| `border-[--accent-amber-muted]` | `border-accent-amber-muted` |
| `bg-[--accent-amber-muted]` | `bg-accent-amber-muted` |
| `bg-[--accent-amber]` | `bg-accent-amber` |
| `bg-[--status-green]/15` | `bg-status-green/15` |
| `bg-[--status-red]/15` | `bg-status-red/15` |
| `hover:bg-[--status-green]/25` | `hover:bg-status-green/25` |
| `hover:bg-[--status-red]/25` | `hover:bg-status-red/25` |
| `hover:bg-[--accent-amber]/25` | `hover:bg-accent-amber/25` |
| `hover:text-[--text-primary]` | `hover:text-text-primary` |
| `hover:text-[--text-secondary]` | `hover:text-text-secondary` |
| `border-l-[--accent-amber]` | `border-l-accent-amber` |

## Files (8 total)

All files are under `frontend/src/components/briefing/`:

| File | Broken refs | Notes |
|---|---|---|
| `StatBar.tsx` | 7 | 6 text + 1 border |
| `QuickFilters.tsx` | 9 | 5 bg + 4 text |
| `BriefingFeed.tsx` | 5 | empty state + dismissed section |
| `cards/NewLeadCard.tsx` | 22 | largest card, all patterns present |
| `cards/ReviewCard.tsx` | 19 | review actions + confidence colors |
| `cards/AlertCard.tsx` | 17 | two card variants (new_project + status_change) |
| `cards/DigestCard.tsx` | 15 | digest grid + top leads |
| `ProjectPanel.tsx` | 26 | slide-over panel |

Also fix the page header in `frontend/src/app/briefing/page.tsx` (3 refs).

---

### Task 1: Fix StatBar.tsx

**Files:**
- Modify: `frontend/src/components/briefing/StatBar.tsx`
- Test: `frontend/src/components/briefing/StatBar.test.tsx`

- [ ] **Step 1: Replace all broken class references in StatBar.tsx**

Open `frontend/src/components/briefing/StatBar.tsx` and make these replacements:

```tsx
// Line 11: border-[--border-subtle] → border-border-subtle
<div className="flex items-baseline gap-6 pb-6 border-b border-border-subtle">

// Line 13: text-[--text-primary] → text-text-primary
<span className="text-2xl font-serif text-text-primary">

// Line 17: text-[--text-secondary] → text-text-secondary
<span className="ml-2 text-sm text-text-secondary">

// Line 22: text-[--accent-amber] → text-accent-amber
<span className="text-2xl font-serif text-accent-amber">

// Line 25: text-[--text-secondary] → text-text-secondary
<span className="ml-2 text-sm text-text-secondary">

// Line 30: text-[--text-primary] → text-text-primary
<span className="text-2xl font-serif text-text-primary">

// Line 33: text-[--text-secondary] → text-text-secondary
<span className="ml-2 text-sm text-text-secondary">
```

- [ ] **Step 2: Run the StatBar test**

Run: `cd frontend && npx vitest run src/components/briefing/StatBar.test.tsx`
Expected: All 4 tests pass. Tests check text content only, not class names, so no test changes needed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/StatBar.tsx
git commit -m "fix(briefing): convert StatBar to Tailwind v4 utility classes"
```

---

### Task 2: Fix QuickFilters.tsx

**Files:**
- Modify: `frontend/src/components/briefing/QuickFilters.tsx`
- Test: `frontend/src/components/briefing/QuickFilters.test.tsx`

- [ ] **Step 1: Replace all broken class references in QuickFilters.tsx**

Open `frontend/src/components/briefing/QuickFilters.tsx` and make these replacements:

```tsx
// Line 30-33 (region buttons active state):
// bg-[--accent-amber-muted] → bg-accent-amber-muted
// text-[--accent-amber] → text-accent-amber
// bg-[--surface-overlay] → bg-surface-overlay
// text-[--text-secondary] → text-text-secondary
// hover:text-[--text-primary] → hover:text-text-primary

// The full className for region buttons becomes:
className={`px-3 py-1.5 rounded-full text-xs font-sans font-medium transition-colors ${
  filters.region === r.value
    ? "bg-accent-amber-muted text-accent-amber"
    : "bg-surface-overlay text-text-secondary hover:text-text-primary"
}`}

// Line 39: bg-[--border-subtle] → bg-border-subtle
<div className="w-px h-4 bg-border-subtle mx-1" />

// Line 44-47 (time buttons): same pattern as region buttons
className={`px-3 py-1.5 rounded-full text-xs font-sans font-medium transition-colors ${
  filters.timeRange === t.value
    ? "bg-accent-amber-muted text-accent-amber"
    : "bg-surface-overlay text-text-secondary hover:text-text-primary"
}`}
```

- [ ] **Step 2: Run the QuickFilters test**

Run: `cd frontend && npx vitest run src/components/briefing/QuickFilters.test.tsx`
Expected: All 5 tests pass. The test at line 41 checks `className` contains `accent-amber` which still matches the new `text-accent-amber` class.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/QuickFilters.tsx
git commit -m "fix(briefing): convert QuickFilters to Tailwind v4 utility classes"
```

---

### Task 3: Fix BriefingFeed.tsx and page.tsx

**Files:**
- Modify: `frontend/src/components/briefing/BriefingFeed.tsx`
- Modify: `frontend/src/app/briefing/page.tsx`

- [ ] **Step 1: Replace broken class references in BriefingFeed.tsx**

Open `frontend/src/components/briefing/BriefingFeed.tsx`:

```tsx
// Line 113: text-[--text-primary] → text-text-primary
<h3 className="font-serif text-2xl text-text-primary mb-3">

// Line 116: text-[--text-tertiary] → text-text-tertiary
<p className="text-sm text-text-tertiary mb-6">

// Line 121: text-[--accent-amber] → text-accent-amber
className="text-sm text-accent-amber hover:underline"

// Line 132: border-[--border-subtle] → border-border-subtle
<div className="pt-4 border-t border-border-subtle">

// Line 135: text-[--text-tertiary] → text-text-tertiary, hover:text-[--text-secondary] → hover:text-text-secondary
className="text-xs font-sans text-text-tertiary hover:text-text-secondary transition-colors"
```

- [ ] **Step 2: Replace broken class references in page.tsx**

Open `frontend/src/app/briefing/page.tsx`:

```tsx
// Line 145: text-[--text-primary] → text-text-primary
<h1 className="text-3xl font-serif text-text-primary tracking-tight">

// Line 148: text-[--text-tertiary] → text-text-tertiary
<p className="mt-1 text-sm text-text-tertiary">
```

- [ ] **Step 3: Run the BriefingFeed test**

Run: `cd frontend && npx vitest run src/components/briefing/BriefingFeed.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/briefing/BriefingFeed.tsx frontend/src/app/briefing/page.tsx
git commit -m "fix(briefing): convert BriefingFeed and page header to Tailwind v4 utility classes"
```

---

### Task 4: Fix NewLeadCard.tsx

**Files:**
- Modify: `frontend/src/components/briefing/cards/NewLeadCard.tsx`
- Test: `frontend/src/components/briefing/cards/NewLeadCard.test.tsx`

- [ ] **Step 1: Replace all broken class references in NewLeadCard.tsx**

Open `frontend/src/components/briefing/cards/NewLeadCard.tsx`. Apply all replacements:

```tsx
// Line 43: card container
className="bg-surface-raised border border-border-subtle border-l-2 border-l-accent-amber rounded-lg p-5"

// Line 47: badge
className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-status-green/15 text-status-green"

// Line 51: mono text
className="text-xs font-mono text-text-tertiary"

// Line 54: heading
className="font-serif text-lg text-text-primary"

// Line 58: subtext
className="text-sm text-text-secondary"

// Lines 65-73: lead score conditional colors
className={`text-sm font-mono font-medium ${
  event.lead_score >= 70
    ? "text-status-green"
    : event.lead_score >= 40
    ? "text-accent-amber"
    : "text-status-red"
}`}

// Line 79: outreach border
className="mb-4 border-l-2 border-border-default pl-4"

// Line 80: outreach text
className="text-sm text-text-secondary leading-relaxed"

// Line 91: contact name
className="text-text-primary font-medium"

// Line 94: contact title
className="text-text-tertiary"

// Line 100: linkedin link
className="text-accent-amber hover:underline text-xs"

// Line 111: actions border
className="flex items-center gap-3 pt-3 border-t border-border-subtle"

// Line 115: push button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-accent-amber text-surface-primary hover:opacity-90 disabled:opacity-50 transition-opacity"

// Line 121: copy button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors"

// Line 127: details button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors ml-auto"
```

- [ ] **Step 2: Run the NewLeadCard test**

Run: `cd frontend && npx vitest run src/components/briefing/cards/NewLeadCard.test.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/cards/NewLeadCard.tsx
git commit -m "fix(briefing): convert NewLeadCard to Tailwind v4 utility classes"
```

---

### Task 5: Fix ReviewCard.tsx

**Files:**
- Modify: `frontend/src/components/briefing/cards/ReviewCard.tsx`
- Test: `frontend/src/components/briefing/cards/ReviewCard.test.tsx`

- [ ] **Step 1: Replace all broken class references in ReviewCard.tsx**

Open `frontend/src/components/briefing/cards/ReviewCard.tsx`. Apply all replacements:

```tsx
// Lines 42-46: confidence color map
const confidenceColor = {
  confirmed: "text-status-green",
  likely: "text-accent-amber",
  possible: "text-text-tertiary",
  unknown: "text-text-tertiary",
}[event.confidence];

// Line 49: card container
className="bg-surface-raised border border-accent-amber-muted rounded-lg p-5"

// Line 53: badge
className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-accent-amber-muted text-accent-amber"

// Line 60: heading
className="font-serif text-lg text-text-primary"

// Line 64: subtext
className="text-sm text-text-secondary"

// Line 70: reasoning text
className="text-sm text-text-secondary mb-4"

// Line 79: source link
className="text-accent-amber hover:underline"

// Line 87: action bar border
className="flex items-center gap-3 pt-3 border-t border-border-subtle"

// Line 91: approve button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-status-green/15 text-status-green hover:bg-status-green/25 disabled:opacity-50 transition-colors"

// Line 97: reject button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-status-red/15 text-status-red hover:bg-status-red/25 disabled:opacity-50 transition-colors"

// Line 103: investigate button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors ml-auto"
```

- [ ] **Step 2: Run the ReviewCard test**

Run: `cd frontend && npx vitest run src/components/briefing/cards/ReviewCard.test.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/cards/ReviewCard.tsx
git commit -m "fix(briefing): convert ReviewCard to Tailwind v4 utility classes"
```

---

### Task 6: Fix AlertCard.tsx

**Files:**
- Modify: `frontend/src/components/briefing/cards/AlertCard.tsx`
- Test: `frontend/src/components/briefing/cards/AlertCard.test.tsx`

- [ ] **Step 1: Replace all broken class references in AlertCard.tsx**

Open `frontend/src/components/briefing/cards/AlertCard.tsx`. Apply all replacements:

```tsx
// Line 54: new_project card container
className="bg-surface-raised rounded-lg p-4"

// Line 57: badge
className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-surface-overlay text-text-tertiary mb-1"

// Line 61: heading
className="font-serif text-base text-text-primary"

// Line 64: subtext
className="text-sm text-text-secondary"

// Line 73: research button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-accent-amber-muted text-accent-amber hover:bg-accent-amber/25 disabled:opacity-50 transition-colors"

// Line 80: dismiss button
className="px-2 py-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"

// Line 91: status_change card container
className="bg-surface-raised rounded-lg p-4"

// Line 94: status change badge
className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-surface-overlay text-text-tertiary mb-1"

// Line 98: heading
className="font-serif text-base text-text-primary"

// Line 102: status arrow text
className="text-sm text-text-secondary"

// Line 104: new status emphasis
className="text-text-primary font-medium"

// Line 112: details button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-surface-overlay text-text-secondary hover:text-text-primary transition-colors"

// Line 117: dismiss button
className="px-2 py-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
```

- [ ] **Step 2: Run the AlertCard test**

Run: `cd frontend && npx vitest run src/components/briefing/cards/AlertCard.test.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/cards/AlertCard.tsx
git commit -m "fix(briefing): convert AlertCard to Tailwind v4 utility classes"
```

---

### Task 7: Fix DigestCard.tsx

**Files:**
- Modify: `frontend/src/components/briefing/cards/DigestCard.tsx`
- Test: `frontend/src/components/briefing/cards/DigestCard.test.tsx`

- [ ] **Step 1: Replace all broken class references in DigestCard.tsx**

Open `frontend/src/components/briefing/cards/DigestCard.tsx`. Apply all replacements:

```tsx
// Line 11: card container
className="bg-surface-overlay rounded-lg p-5"

// Line 12: badge
className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-surface-overlay text-text-tertiary mb-3"

// Line 18: stat number
className="text-2xl font-serif text-text-primary"

// Line 21: stat label
className="text-xs font-sans text-text-tertiary uppercase tracking-wider"

// Line 25: stat number
className="text-2xl font-serif text-text-primary"

// Line 28: stat label
className="text-xs font-sans text-text-tertiary uppercase tracking-wider"

// Line 32: stat number
className="text-2xl font-serif text-text-primary"

// Line 35: stat label
className="text-xs font-sans text-text-tertiary uppercase tracking-wider"

// Line 44: top leads border
className="pt-3 border-t border-border-subtle"

// Line 45: section label
className="text-xs font-sans text-text-tertiary uppercase tracking-wider mb-2"

// Line 51: lead name
className="text-text-primary"

// Line 53: lead project
className="text-text-tertiary"

// Lines 58-61: score conditional colors
className={`font-mono text-xs ${
  lead.lead_score >= 70
    ? "text-status-green"
    : "text-accent-amber"
}`}
```

- [ ] **Step 2: Run the DigestCard test**

Run: `cd frontend && npx vitest run src/components/briefing/cards/DigestCard.test.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/cards/DigestCard.tsx
git commit -m "fix(briefing): convert DigestCard to Tailwind v4 utility classes"
```

---

### Task 8: Fix ProjectPanel.tsx

**Files:**
- Modify: `frontend/src/components/briefing/ProjectPanel.tsx`
- Test: `frontend/src/components/briefing/ProjectPanel.test.tsx`

- [ ] **Step 1: Replace all broken class references in ProjectPanel.tsx**

Open `frontend/src/components/briefing/ProjectPanel.tsx`. Apply all replacements:

```tsx
// Line 58: panel container
className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-surface-primary border-l border-border-subtle z-50 overflow-y-auto transition-transform duration-200 ease-out"

// Line 63: back button
className="mb-4 text-sm text-text-tertiary hover:text-text-secondary transition-colors"

// Line 68: loading text
className="text-sm text-text-tertiary"

// Line 72: project title
className="font-serif text-xl text-text-primary mb-1"

// Line 75: metadata row
className="flex items-center gap-2 flex-wrap text-xs font-sans text-text-tertiary"

// Line 100: status label
className="text-text-tertiary text-xs uppercase tracking-wider mb-1"

// Line 101: status value
className="text-text-primary"

// Line 105: cod label
className="text-text-tertiary text-xs uppercase tracking-wider mb-1"

// Line 106: cod value
className="text-text-primary"

// Line 109: score label
className="text-text-tertiary text-xs uppercase tracking-wider mb-1"

// Line 110: score value
className="text-text-primary font-mono"

// Line 113: fuel label
className="text-text-tertiary text-xs uppercase tracking-wider mb-1"

// Line 114: fuel value
className="text-text-primary"

// Line 120: discovery section border
className="pt-4 border-t border-border-subtle"

// Line 121: discovery label
className="text-text-tertiary text-xs uppercase tracking-wider mb-2"

// Line 122: epc name
className="text-text-primary font-medium mb-1"

// Line 123: discovery details
className="text-sm text-text-secondary"

// Line 131: location section border
className="pt-4 border-t border-border-subtle"

// Line 132: location label
className="text-text-tertiary text-xs uppercase tracking-wider mb-2"

// Line 134: location text
className="text-sm text-text-secondary"

// Line 139: maps link
className="text-xs text-accent-amber hover:underline mt-1 inline-block"

// Line 149: actions section border
className="pt-4 border-t border-border-subtle flex gap-3"

// Line 152: investigate button
className="px-3 py-1.5 text-xs font-sans font-medium rounded bg-accent-amber text-surface-primary hover:opacity-90 transition-opacity"

// Line 159: not found text
className="text-sm text-text-tertiary"
```

- [ ] **Step 2: Run the ProjectPanel test**

Run: `cd frontend && npx vitest run src/components/briefing/ProjectPanel.test.tsx`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/briefing/ProjectPanel.tsx
git commit -m "fix(briefing): convert ProjectPanel to Tailwind v4 utility classes"
```

---

### Task 9: Visual verification

- [ ] **Step 1: Run all briefing tests together**

Run: `cd frontend && npx vitest run src/components/briefing/`
Expected: All tests pass.

- [ ] **Step 2: Start the dev server and visually verify**

Run: `cd frontend && npm run dev`

Open `http://localhost:3000/briefing` in a browser. Verify:
- Stat bar numbers show ivory and amber text (not invisible/default)
- Filter pills have visible `surface-overlay` backgrounds, active pills show amber-muted background
- Cards (if any events exist) show `surface-raised` backgrounds with proper borders
- Empty state text is visible with correct text hierarchy
- The page matches the visual weight of `/actions` and `/review`

- [ ] **Step 3: Confirm no remaining broken references**

Run: `grep -r '\[--' frontend/src/components/briefing/ frontend/src/app/briefing/`
Expected: No output (zero matches). All arbitrary CSS variable references have been eliminated.

- [ ] **Step 4: Final commit if any stragglers were found**

Only if step 3 found remaining references.
