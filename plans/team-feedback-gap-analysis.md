# Team Feedback — Gap Analysis & Implementation Plan

_Generated 2026-03-07_

---

## HIGH PRIORITY

### 1. Global Year Filter (COD 2026–2027)

**Gap:** FilterBar has ISO, state, status, fuel type, MW range, and text search — but no year/date filter. The EPC table page hardcodes `expected_cod` between 2025–2028 in the SSR query but exposes no user control.

**What exists:**
- `projects.expected_cod` (DATE) — already in the schema
- `projects.queue_date` (DATE) — also available
- `Filters` type in `types.ts` — has no year field
- `FilterBar.tsx` — renders all current filters, no date picker
- `Dashboard.tsx` — applies filters client-side via `useMemo`
- `epc-discovery/table/page.tsx` — hardcoded `.gte("expected_cod", "2025-01-01").lte("expected_cod", "2028-12-31")`

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/lib/types.ts` | Add `cod_year_min?: number`, `cod_year_max?: number` to `Filters` |
| `frontend/src/components/FilterBar.tsx` | Add year range dropdown (2024–2030) |
| `frontend/src/components/Dashboard.tsx` | Add COD year to `useMemo` filter logic |
| `frontend/src/app/epc-discovery/table/page.tsx` | Remove hardcoded date range, pass dynamic filter |
| `frontend/src/components/epc/EpcDiscoveryDashboard.tsx` | Accept + apply year filter |
| `frontend/src/components/epc/ProjectPicker.tsx` | Filter projects by year |

**Effort:** Small — pure frontend, no schema changes.

---

### 2. Project Details Page

**Gap:** No detail view for individual projects. The `ProjectsTable` renders rows but clicking does nothing. No route `/projects/[id]` exists.

**What exists:**
- `projects` table has all required fields: `project_name`, `developer`, `state`, `county`, `status`, `latitude`, `longitude`
- Latitude/longitude fields exist in schema but are **not populated** by scrapers
- `raw_data` JSONB may contain coordinates from ISO sources
- No Next.js dynamic route for project detail

**Files to create:**
| File | Purpose |
|------|---------|
| `frontend/src/app/projects/[id]/page.tsx` | SSR detail page — fetches single project + its discoveries |
| `frontend/src/components/ProjectDetail.tsx` | Detail view component |

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/components/ProjectsTable.tsx` | Make project name a clickable `<Link>` to `/projects/[id]` |
| `frontend/src/components/epc/ResearchPanel.tsx` | Add link to project detail page |
| `scrapers/src/transform.py` | Extract lat/lng from `raw_data` if available (ERCOT has coordinates) |

**Detail page should show:**
- Header: project name, developer, ISO region badge
- Info grid: state, county, MW capacity, fuel type, status, queue date, expected COD
- Coordinates: lat/lng with clickable Google Maps link (`https://www.google.com/maps?q={lat},{lng}`)
- EPC section: accepted discovery (if any) with sources
- Research history: prior research attempts from `research_attempts` table
- Raw data: collapsible JSON viewer of `raw_data`

**Effort:** Medium — new page + component, optional scraper fix for coordinates.

---

### 3. Global Search Bar

**Gap:** Search exists but is scoped per page. Projects page searches `project_name` and `developer` only. EPC table searches `project_name`, `developer`, `queue_id`. No cross-entity search (EPC name, location).

**What exists:**
- `FilterBar.tsx` has a search input → filters by `project_name.includes()` or `developer.includes()`
- `ProjectPicker.tsx` has a separate search → same approach
- No unified search across projects + EPC discoveries + entities

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/lib/types.ts` | Expand `Filters.search` to be used globally |
| `frontend/src/components/FilterBar.tsx` | Widen search to include `epc_company`, `county`, `state` |
| `frontend/src/components/Dashboard.tsx` | Update filter logic to match on `epc_company`, `county` |
| `frontend/src/components/epc/ProjectPicker.tsx` | Add `epc_contractor` to search scope |

**Effort:** Small — extend existing client-side search matching.

---

### 4. Project Status Tracking

**Gap:** `projects.status` exists but reflects ISO queue status (Active/Completed/Withdrawn), not construction lifecycle. No Pre-Construction / Under Construction / Completed lifecycle tracking.

**What exists:**
- `projects.status` — ISO queue status ("Active", "Completed", "Withdrawn")
- No separate lifecycle/construction status field
- `epc_discoveries.review_status` — review workflow, not project lifecycle

**Options:**
- **Option A (recommended):** Add a new `construction_status` column to `projects` to avoid overloading `status`
- **Option B:** Repurpose `status` — risky since scrapers write to it

**Files to create:**
| File | Purpose |
|------|---------|
| `supabase/migrations/007_add_construction_status.sql` | `ALTER TABLE projects ADD COLUMN construction_status TEXT DEFAULT 'unknown'` with CHECK constraint |

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/lib/types.ts` | Add `construction_status` to `Project` type |
| `frontend/src/components/FilterBar.tsx` | Add construction status filter dropdown |
| `frontend/src/components/Dashboard.tsx` | Apply construction status filter |
| `frontend/src/components/ProjectsTable.tsx` | Show construction status column (color-coded pill) |
| `frontend/src/components/epc/ProjectPicker.tsx` | Show status indicator |
| `agent/src/db.py` | Add `construction_status` to `search_projects` filters |

**Construction status values:** `unknown`, `pre_construction`, `under_construction`, `completed`, `cancelled`

**Effort:** Medium — schema migration + frontend filter + column.

---

### 5. EPC Table Improvements

**Gap:** EPC table has filter tabs (All/Needs Research/Has EPC/Pending) and project search, but lacks year filter, location filter, status filter, and row expansion for associated data.

**What exists:**
- `EpcDiscoveryDashboard.tsx` — two-pane layout with left picker, right detail
- `ProjectPicker.tsx` — list with checkboxes, search, filter tabs
- `ResearchPanel.tsx` — shows detail for selected project (EPC, confidence, sources)
- No expandable rows, no year/location/status filters

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/components/epc/EpcDiscoveryDashboard.tsx` | Add filter bar (year, state, construction status) above picker |
| `frontend/src/components/epc/ProjectPicker.tsx` | Accept and apply new filters; add expandable row UI |
| `frontend/src/app/epc-discovery/table/page.tsx` | Remove hardcoded date filter, pass all projects |

**Expandable row design:**
- Click chevron → expands to show: developer, EPC contractor, confidence, source count, data sources list
- Sources show channel + publication + reliability badge
- Link to full project detail page

**Effort:** Medium — new filter controls + expandable row component.

---

## MEDIUM PRIORITY

### 6. Data Freshness Indicator

**Gap:** `StatsCards` shows "Last updated" from `scrape_runs` but doesn't show per-ISO breakdown or scheduled frequency. No persistent indicator across pages.

**What exists:**
- `scrape_runs` table — tracks `iso_region`, `status`, `started_at`, `completed_at`
- `StatsCards.tsx` — shows most recent successful scrape date
- GitHub Actions scheduled scrapers (cron-based)
- No data freshness component on EPC pages

**Files to create:**
| File | Purpose |
|------|---------|
| `frontend/src/components/DataFreshnessBar.tsx` | Compact bar showing per-ISO last scan date + next scheduled + staleness indicator |

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/app/page.tsx` | Pass `scrape_runs` to DataFreshnessBar |
| `frontend/src/app/epc-discovery/table/page.tsx` | Fetch and show DataFreshnessBar |
| `frontend/src/app/layout.tsx` | Optionally add to global layout |

**Data to show:**
- Per ISO: last scan date, projects found, status (green/amber/red based on age)
- Overall: "Data as of {date}" with tooltip showing breakdown
- Scheduled frequency: "Scrapers run daily at 6am UTC" (static text or from config)

**Effort:** Small — new component, data already available in `scrape_runs`.

---

### 7. Data Source Transparency

**Gap:** No explanation of where data comes from. Users see data but don't know the provenance.

**What exists:**
- `projects.source` — always `'iso_queue'`
- `epc_discoveries.sources` — array of `{channel, publication, date, url, excerpt, reliability}`
- `SourceCard.tsx` — renders individual sources on EPC discoveries
- No "About our data" section or methodology explanation

**Files to create:**
| File | Purpose |
|------|---------|
| `frontend/src/components/DataSourcesInfo.tsx` | Expandable panel explaining data sources |

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/app/page.tsx` | Add collapsible "About Our Data" section below stats |
| `frontend/src/app/epc-discovery/table/page.tsx` | Add same section |

**Content to include:**
- **Project Data:** ERCOT, CAISO, MISO interconnection queues (with links to official sources)
- **EPC Discovery:** Web search via Tavily → Claude agent analysis of press releases, trade publications, permit filings, SEC filings
- **Confidence Levels:** Explain confirmed vs likely vs possible
- **Limitations:** Not all ISOs covered, EPC discovery depends on public disclosures

**Effort:** Small — static content component, no backend changes.

---

## LOWER PRIORITY

### 8. EPC Chat Repositioning

**Gap:** Chat is a dedicated page (`/epc-discovery`), but team wants it as a side panel on the right of data views, not a primary navigation destination. Focus should be on data quality first.

**What exists:**
- `ChatInterface.tsx` — full-page chat with sidebar for conversation history
- NavBar: Projects | EPC Chat | EPC Table (chat is prominent)
- Chat is self-contained component, could be extracted to a drawer/panel

**Files to modify:**
| File | Change |
|------|--------|
| `frontend/src/components/NavBar.tsx` | De-emphasize or remove "EPC Chat" from primary nav |
| `frontend/src/components/chat/ChatInterface.tsx` | Refactor to support embedded panel mode (narrower, no sidebar) |
| `frontend/src/app/page.tsx` | Add collapsible chat drawer on right edge |
| `frontend/src/app/epc-discovery/table/page.tsx` | Add collapsible chat drawer on right edge |

**Alternative:** Keep chat as separate page but move it to last position in nav and make it less prominent. Simpler and avoids layout complexity.

**Effort:** Medium (full drawer) or Small (just reorder nav).

---

## FUTURE CONSIDERATIONS

### 9. EPC Probability Scoring

**Gap:** `lead_score` field exists on `projects` (INTEGER 0–100) but is always 0. No scoring logic implemented.

**What would be needed:**
- Scoring algorithm based on: project size, expected COD proximity, developer track record (from KB), state permitting difficulty, EPC discovery confidence
- `agent/src/scoring.py` — new module with scoring logic
- Update score on discovery acceptance or periodic batch recalculation
- Frontend: score column already rendered in `ProjectsTable.tsx` (color-coded badge)

**Depends on:** Knowledge base being populated with enough data to score meaningfully.

### 10. Automated Alerts for Status Changes

**Gap:** No change detection or notification system. Data is scraped but not diffed.

**What would be needed:**
- Delta tracking in scrapers: compare new scrape vs previous, detect changes in `status`, `expected_cod`, `mw_capacity`
- `supabase/migrations/008_create_alerts.sql` — alerts table
- Notification channel: email, Slack webhook, or in-app notification center
- `frontend/src/components/AlertsPanel.tsx` — show recent changes

**Depends on:** Data freshness infrastructure being reliable first.

---

## Implementation Priority Order

| # | Item | Effort | Impact | Dependencies |
|---|------|--------|--------|-------------|
| 1 | Global Year Filter | Small | High | None |
| 2 | Global Search Bar (expand scope) | Small | High | None |
| 3 | Data Source Transparency | Small | Medium | None |
| 4 | Data Freshness Indicator | Small | Medium | None |
| 5 | EPC Table Filters + Expandable Rows | Medium | High | #1 (year filter pattern) |
| 6 | Project Details Page | Medium | High | None (coordinates optional) |
| 7 | Project Status Tracking | Medium | Medium | Migration 007 |
| 8 | Chat Repositioning | Small–Med | Low | None |
| 9 | EPC Probability Scoring | Large | High | KB data, scoring algorithm |
| 10 | Automated Alerts | Large | Medium | Delta tracking, notifications |

**Recommended sprint:** Items 1–4 first (all small, no migrations), then 5–6, then 7–8.
