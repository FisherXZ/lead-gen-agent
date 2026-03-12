# Chat UI Polish Plan — 2026-03-11

## Problem
Our agent chat interface renders all text as plain strings. Markdown syntax (`**bold**`, `| tables |`, `## headings`) shows as raw characters. Compared to Claude.ai and Manus, we lack:
- Rich markdown rendering (headings, tables, bold, lists, code blocks, links)
- Polished tool call visualization (collapsible cards with icons)
- Visual hierarchy and typography

## Current State
- `ChatMessage.tsx` renders text parts as `<div className="whitespace-pre-wrap text-sm">{part.text}</div>`
- No markdown library installed
- `ToolPart.tsx` exists but is basic — flat cards, no collapse, no icons, no status indicators
- Custom tool result cards (EPC results, guidance, etc.) in `frontend/src/components/chat/parts/` — these stay as-is

---

## Research Findings (completed)

### Industry Survey — Markdown Rendering
| Project | Library | Code Highlight | Tables | Streaming Strategy |
|---|---|---|---|---|
| **Streamdown** (Vercel) | Custom remark/rehype | Shiki | GFM built-in | `remend` auto-close + memoized LRU |
| **NextChat** | react-markdown | rehype-highlight | remark-gfm | useDebouncedCallback |
| **LobeChat** | react-markdown v10 | Shiki | remark-gfm | via @lobehub/ui |
| **LibreChat** | react-markdown | rehype-highlight | remark-gfm | React.memo + useMemo |

**Key insight:** Vercel built `streamdown` specifically for AI streaming chat — handles incomplete tables/code blocks mid-stream, memoized rendering, purpose-built for Next.js + AI SDK + Tailwind.

### Industry Survey — Tool Call Visualization
| Pattern | Used By | Description |
|---|---|---|
| **Inline collapsible card** | shadcn.io/ai, LibreChat | Header row (icon + label + status) → expand for details |
| **Custom component per tool** | Vercel AI SDK, CopilotKit | Rich cards for specific tools (weather, charts) |
| **Side panel execution** | Manus | Separate pane showing step-by-step progress |
| **Task list / log** | AgentGPT | Sequential task list with status |

**Key insight:** `shadcn.io/ai` has a ready-made Tool component — collapsible card with status indicators, built for Vercel AI SDK's `parts` array. Our data structure already matches.

### Universal patterns across all projects:
- Spinner while tool running → checkmark when done → red X on error
- Background tools (search, fetch) auto-collapse when done
- Primary tools (results, reports) stay expanded showing rich cards
- Chevron toggle for expand/collapse

---

## Tier 1: Markdown + Typography

### Decision: Use `streamdown` (Vercel's library)
- Purpose-built for Next.js + AI SDK + streaming
- Handles partial markdown during streaming (incomplete tables, unclosed code blocks)
- Memoized rendering with LRU cache (no O(n²) re-parse on every token)
- Shiki for code highlighting (better than highlight.js)
- GFM tables built-in
- CSS custom properties compatible with Tailwind

### Packages to install
```
npm i streamdown @streamdown/code
```
(Skip @streamdown/math and @streamdown/mermaid — we don't need LaTeX or diagrams)

### Changes

**1. `ChatMessage.tsx` — swap text renderer**
```tsx
// BEFORE
<div className="whitespace-pre-wrap text-sm leading-relaxed">
  {part.text}
</div>

// AFTER
import { Streamdown } from 'streamdown'
import { code } from '@streamdown/code'

<Streamdown
  animated
  plugins={{ code }}
  isAnimating={/* true while streaming */}
>
  {part.text}
</Streamdown>
```

**2. Add Tailwind typography styles**
- Install `@tailwindcss/typography` plugin
- Add `prose prose-sm prose-slate` wrapper class
- Custom overrides: table overflow-x-auto, heading sizes, link colors

**3. Custom table wrapper** (for wide tables)
```tsx
table: ({ children }) => (
  <div className="overflow-x-auto">
    <table className="min-w-full">{children}</table>
  </div>
)
```

### Files touched
- `frontend/package.json` — new deps
- `frontend/src/components/chat/ChatMessage.tsx` — swap text renderer
- `frontend/tailwind.config.ts` — add typography plugin
- `frontend/src/components/chat/MarkdownMessage.tsx` — NEW, thin wrapper for Streamdown with our styles

---

## Tier 3: Tool Call Cards Polish

### Decision: shadcn.io/ai-inspired collapsible cards
Our existing `ToolPart.tsx` already switches on tool name and renders custom cards. We wrap this in a collapsible container with header/status/icons.

### Component structure
```
<ToolPart>
  <CollapsibleToolCard>
    <Header>  (always visible)
      <ToolIcon />           — per-tool SVG icon
      <ProgressLabel />      — existing getProgressLabel text
      <StatusBadge />        — spinner (running) | checkmark (done)
      <ChevronToggle />      — expand/collapse
    </Header>
    <Body>  (collapsible with animation)
      {renderToolResult()}   — existing EpcResultCard, ProjectListCard, etc.
    </Body>
  </CollapsibleToolCard>
</ToolPart>
```

### Auto-collapse logic
| Tool | Default state when done |
|---|---|
| `brave_search` | Collapsed (one-liner: "Searched for X") |
| `scrape_website` | Collapsed ("Scraped example.com") |
| `recall`, `remember` | Collapsed ("Recalled 3 memories") |
| `assess_confidence` | Collapsed ("Confidence: 78%") |
| `search_projects` | **Expanded** (shows project list) |
| `report_findings` | **Expanded** (shows EPC result card) |
| `request_guidance` | **Expanded** (shows guidance card) |

### Tool icons (inline SVGs, no icon library)
| Tool | Icon |
|---|---|
| `brave_search` | 🔍 Search magnifying glass |
| `scrape_website` | 🌐 Globe |
| `search_projects` | 🗃️ Database/table |
| `report_findings` | 📋 Clipboard/document |
| `assess_confidence` | 📊 Bar chart |
| `recall` / `remember` | 🧠 Brain |
| `request_guidance` | 💬 Message bubble |
| unknown | 🔧 Wrench |

### Animation
- Tailwind `transition-all duration-200` + `max-height` for collapse
- Or use Radix `Collapsible` if already available (check if radix is in deps)

### Files touched
- `frontend/src/components/chat/ToolPart.tsx` — wrap in collapsible card
- `frontend/src/components/chat/CollapsibleToolCard.tsx` — NEW, reusable wrapper
- `frontend/src/components/chat/ToolIcon.tsx` — NEW, icon mapping

---

## Out of Scope
- Tier 2: Thinking/reasoning UI (needs backend streaming changes)
- Dark theme
- File attachments
- Side panel execution view (Manus-style — overkill for now)

---

## Execution Plan

### Team Structure (5 agents)

**Leader** — Project coordinator
- Owns the plan, settles differences of opinion between engineers
- Actively communicates with Fisher (CEO) when issues arise or requirements are unclear
- Does final integration check after both tracks merge
- Does NOT write code — only coordinates

**Engineer 1** — Markdown rendering (Tier 1)
- Writes detailed technical breakdown of their implementation approach
- Shares plan with Engineer 2 to identify conflicts/dependencies
- Implements: streamdown, typography, MarkdownMessage component

**Engineer 2** — Tool call cards (Tier 3)
- Writes detailed technical breakdown of their implementation approach
- Shares plan with Engineer 1 to identify conflicts/dependencies
- Implements: CollapsibleToolCard, ToolIcon, ToolPart refactor

**Reviewer 1** — Engineering perspective
- Reviews both engineers' code for technical quality
- Focuses on: correctness, performance, edge cases, streaming behavior
- Catches bugs, missing error handling, unnecessary complexity

**Reviewer 2** — PM / product perspective
- Reviews both engineers' code from user experience angle
- Focuses on: does it match the Claude/Manus reference screenshots?
- Checks: visual polish, spacing, animation smoothness, accessibility
- Flags anything that feels "off" compared to the design intent

### Workflow (4 phases)

**Phase 1: Technical Breakdown (engineers in parallel)**
1. Both engineers read the plan + existing code
2. Each writes a detailed technical implementation breakdown:
   - Exact file changes with before/after
   - Package versions and imports
   - Edge cases they'll handle
   - Risks or open questions
3. Engineers share plans with each other
4. They identify overlaps/conflicts (e.g., both touching ChatMessage.tsx)
5. If they can't resolve a conflict → escalate to Leader
6. If requirements are unclear → Leader escalates to Fisher

**Phase 2: Implementation (engineers in parallel)**
1. Engineer 1 implements markdown rendering
2. Engineer 2 implements tool call cards
3. Both work in isolated worktrees to avoid conflicts
4. Leader monitors progress, answers questions

**Phase 3: Review (reviewers in parallel)**
1. Reviewer 1 (engineering) reviews both tracks for technical quality
2. Reviewer 2 (PM/product) reviews both tracks for UX quality
3. Issues flagged → engineers fix
4. Leader settles any disagreements between reviewers and engineers

**Phase 4: Integration**
1. Leader merges both tracks
2. Verifies no conflicts between markdown rendering and tool cards
3. Final check against acceptance criteria
4. Reports to Fisher

### Acceptance Criteria
- [ ] Assistant messages render markdown: headings, bold, tables, lists, code blocks, links
- [ ] Tables are responsive (horizontal scroll on overflow)
- [ ] Tool calls show as collapsible cards with icons and status indicators
- [ ] Background tools auto-collapse; primary tools stay expanded
- [ ] Smooth expand/collapse animation
- [ ] No regressions on existing custom cards (EPC results, guidance, etc.)
- [ ] Streaming still works correctly (no flicker, no broken partial markdown)
- [ ] Both engineers' implementations are compatible (no CSS/component conflicts)
