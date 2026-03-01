# Phase 1 Plan: Solar Lead Gen — ISO Queue Ingestion + Dashboard

**Date:** 2026-03-01
**Status:** Implemented (2026-03-01) — gridstatus replaced with direct fetchers due to Python 3.13 incompatibility

---

## Context

Civ Robotics sells autonomous layout robots to solar farm EPC contractors. They need to discover upcoming utility-scale solar projects (>20 MW) before ground breaks. ISO interconnection queues are the highest-signal, zero-cost, earliest data source — projects appear 1-3 years before construction.

Phase 1 delivers: **scrape 3 ISO queues → filter solar projects → store in Supabase → display in a Next.js dashboard**.

## Key Discovery

**`gridstatus`** (Python library, v0.34.0) already provides standardized `get_interconnection_queue()` for all 3 ISOs. Instead of writing raw parsers:
- ERCOT: Downloads Excel, handles 30-row header skip automatically
- CAISO: Downloads Excel, parses 3 sheets automatically
- MISO: Hits JSON API `https://www.misoenergy.org/api/giqueue/getprojects` (no auth)

All return DataFrames with standardized columns: `Queue ID, Project Name, Interconnecting Entity, County, State, Generation Type, Capacity (MW), Queue Date, Status, Proposed Completion Date`.

---

## Repo Structure

```
lead-gen-agent/
├── .github/workflows/scrape-iso-queues.yml   # Weekly cron
├── .gitignore
├── README.md
├── frontend/                                  # Next.js (Vercel)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx                       # Dashboard (server component)
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── ProjectsTable.tsx              # Table + client-side filtering
│   │   │   ├── FilterBar.tsx                  # Filter controls
│   │   │   └── StatsCards.tsx                 # Summary metrics
│   │   └── lib/
│   │       ├── supabase/client.ts
│   │       ├── supabase/server.ts
│   │       └── types.ts
│   ├── package.json
│   ├── .env.local.example
│   └── ...config files
├── scrapers/                                  # Python (GitHub Actions)
│   ├── pyproject.toml                         # deps: gridstatus, supabase, pandas
│   ├── .env.example
│   └── src/
│       ├── main.py                            # Entry point
│       ├── config.py                          # Constants, env loading
│       ├── db.py                              # Supabase upsert + logging
│       ├── transform.py                       # gridstatus DataFrame → DB schema
│       ├── filters.py                         # Solar detection, MW threshold
│       ├── scoring.py                         # Basic lead scoring
│       └── scrapers/
│           ├── base.py                        # Abstract base class
│           ├── ercot.py
│           ├── caiso.py
│           └── miso.py
└── supabase/migrations/
    ├── 001_create_projects.sql
    └── 002_create_indexes.sql
```

## Database Schema (Supabase Postgres)

### `projects` table

| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| queue_id | TEXT | ISO-specific identifier |
| iso_region | TEXT | ERCOT / CAISO / MISO |
| project_name | TEXT | |
| developer | TEXT | "Interconnecting Entity" |
| epc_company | TEXT | NULL in Phase 1 |
| state, county | TEXT | |
| latitude, longitude | FLOAT | NULL in Phase 1 |
| mw_capacity | FLOAT | |
| fuel_type | TEXT | Solar / Solar+Storage |
| queue_date | DATE | |
| expected_cod | DATE | Proposed Completion Date |
| status | TEXT | Active / Completed / Withdrawn |
| source | TEXT | 'iso_queue' |
| lead_score | INT | Basic heuristic (0-100) |
| raw_data | JSONB | Full original record |
| created_at, updated_at | TIMESTAMP | Auto-managed |

**Dedup constraint:** `UNIQUE(iso_region, queue_id)` — upserts update existing rows.

### `scrape_runs` table

For monitoring: iso_region, status, counts, timestamps, errors.

### Row-Level Security

Public read (anon key), service-role write only (scrapers).

## Scraper Pipeline

```
gridstatus.get_interconnection_queue()
  → filter(is_solar AND mw >= 20)
  → transform(gridstatus columns → DB schema)
  → upsert(Supabase, conflict on iso_region + queue_id)
  → log(scrape_runs)
```

Each ISO scraper extends a base class, overrides `iso_region` and solar detection logic. `gridstatus` handles all the download/parsing. If gridstatus breaks for an ISO, the scraper can override `fetch_queue()` with a direct implementation — rest of pipeline stays the same.

**Start with MISO** (JSON API, most reliable) to validate the full pipeline, then add ERCOT and CAISO.

## Frontend (Next.js on Vercel)

- Server component fetches initial data from Supabase
- Client-side `ProjectsTable` with filtering, sorting, pagination via Supabase JS client
- `FilterBar`: ISO region, state, status, fuel type, MW range, text search
- `StatsCards`: total projects, total MW, by-ISO counts, last scrape time
- Tailwind CSS for styling

## GitHub Actions

Weekly cron (Monday 6 AM UTC), plus manual `workflow_dispatch`. Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.

## Implementation Steps

1. **Scaffold repo** — .gitignore, create-next-app, scrapers/pyproject.toml, directory structure
2. **Supabase setup** — create project, run migrations, verify connectivity
3. **Build MISO scraper** — config → db → base scraper → MISO → transform → filters → main.py — run end-to-end, verify data in Supabase
4. **Add ERCOT + CAISO scrapers** — extend base class, test each
5. **Add basic scoring** — simple heuristic based on MW, status, timeline
6. **Build Next.js dashboard** — Supabase clients, types, page, table, filters, stats
7. **GitHub Actions workflow** — cron job, test with manual dispatch
8. **Deploy** — Vercel for frontend, verify full loop

## Planned Improvement: Hot Leads Section

After initial testing, the dashboard reads like a data dump — functional but doesn't guide the user toward action. Next iteration should add a **"Hot Leads" section** between the stats cards and the full table:

- Shows only the top 10-15 leads: Active status, score >= 70, sorted by score descending
- Visually prominent — accent border or background tint to separate it from the exploratory table below
- Just enough info per row to decide "should I pursue this?" — project name, developer, MW, state, expected COD, score
- The full table stays below as "All Projects" for deeper exploration and filtering

This reframes the dashboard from "data browser" to "action list + data browser."

## Verification

1. Run `python -m src.main` locally → check Supabase dashboard for rows
2. Run twice → verify no duplicates (upsert), `updated_at` changes
3. Check MISO, ERCOT, CAISO each produce >20 solar projects with >20 MW
4. Open Next.js dev server → verify table loads, filters work, stats display
5. Trigger GitHub Action manually → verify data updates
6. Deploy to Vercel → verify production dashboard
