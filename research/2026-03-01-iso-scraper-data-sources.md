# Phase 1 Technical Decisions — ISO Scrapers, Schema, Scoring & Pipeline Architecture

**Date:** 2026-03-01
**Author:** Development notes captured during Phase 1 build

---

## Overview

We scrape 3 ISO interconnection queues to find utility-scale solar projects (>= 20 MW). Each ISO publishes their queue data differently. This document captures how each data source works, what we tried, what failed, and how the final implementation works.

### Why Not gridstatus?

The original plan was to use `gridstatus` (Python library) which provides a standardized `get_interconnection_queue()` for all 3 ISOs. Two problems killed this:

1. **Python version incompatibility.** gridstatus v0.30+ requires Python `<3.13`. We run Python 3.13. The highest installable version was v0.29.1.
2. **Missing User-Agent header.** gridstatus v0.29.1 doesn't send a `User-Agent` header. MISO's API returns 403 without one.

**Decision:** Write direct fetchers for all 3 ISOs using `requests` + `pandas`. More reliable, full control, no dependency risk.

---

## MISO

### Data Source

- **Type:** JSON API
- **URL:** `https://www.misoenergy.org/api/giqueue/getprojects`
- **Auth:** None (public)
- **Requirement:** Must send a `User-Agent` header or you get 403
- **Stability:** High — single stable endpoint, JSON response

### Response Format

Returns a JSON array. Each object represents one interconnection project.

**Key fields:**

| API Field | Maps To | Notes |
|---|---|---|
| `projectNumber` | queue_id | e.g. "J3464" |
| `poiName` | project_name | Point of Interconnection name |
| `transmissionOwner` | developer | |
| `state` | state | 2-letter code |
| `county` | county | |
| `summerNetMW` | mw_capacity | Summer net capacity |
| `fuelType` | fuel_type | "Solar", "Wind", "Battery Storage", etc. |
| `facilityType` | facility_type | "Photovoltaic", "Solar/Battery", etc. |
| `applicationStatus` | status | "Active", etc. |
| `queueDate` | queue_date | ISO 8601 datetime |
| `inService` | expected_cod | Projected in-service date |

**Solar detection:** `fuelType` contains "Solar" or `facilityType` contains "Photovoltaic", "Solar/Battery", "Solar/Wind", "Solar/Wind/Battery".

### Numbers (as of 2026-03-01)

- Total projects in queue: 3,713
- Solar projects >= 20 MW: 2,103

---

## ERCOT

### Data Source

- **Type:** Monthly Excel file (.xlsx)
- **URL:** Dynamic — changes every month
- **Auth:** None for download, but discovering the URL is the hard part
- **Stability:** Medium — depends on ERCOT's document listing API staying up

### How to Find the Download URL

ERCOT publishes a new GIS Report Excel file each month. Each gets a unique `doclookupId`. The download URL pattern is:

```
https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={DOC_ID}
```

To find the current `DOC_ID`, hit the JSON document listing API:

```
https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=15933
```

This returns all documents published under report type 15933 (GIS Report category). **Important:** This category also contains "Co-located Battery Identification Report" files. Filter for documents where `FriendlyName` starts with `GIS_Report`.

The response looks like:

```json
{
  "ListDocsByRptTypeRes": {
    "DocumentList": [
      {
        "Document": {
          "FriendlyName": "GIS_Report_January2026",
          "DocID": "1189272131",
          "PublishDate": "2026-02-02T15:03:00-06:00",
          "Extension": "xlsx"
        }
      }
    ]
  }
}
```

### What We Tried That Failed

| Attempt | What | Result |
|---|---|---|
| 1 | MIS Reports page (`http://mis.ercot.com/misapp/GetReports.do?reportTypeId=15933`) | Connection timed out — MIS portal unreachable |
| 2 | Same URL over HTTPS | SSL handshake failure — broken cert for programmatic access |
| 3 | Known doclookupId (1018607859) | Downloaded successfully but was the wrong document (Battery Storage report, not GIS Report) |
| 4 | ERCOT Data Portal (`data.ercot.com`) | Returns HTML (React SPA), not JSON — no programmatic API |
| 5 | ERCOT API Explorer (`api.ercot.com`) | Returns 401 — requires subscription key |
| 6 | JSON document listing (`IceDocListJsonWS`) | **Worked.** Returns JSON list of all documents, we filter for GIS_Report |

### Excel Structure

The GIS Report has 14 sheets. We use **"Project Details - Large Gen"**.

**Header layout:**
- Rows 0–28: Notes, disclaimers, definitions
- Row 29: Section headers ("Project Attributes", "Changes from Last Report", "GIM Project Milestone Dates")
- **Row 30: Column names** (this is our header row)
- Rows 31–34: Sub-headers for multi-row column labels
- **Row 35 onward: Data**

**Key columns:**

| Excel Column | Maps To | Notes |
|---|---|---|
| `INR` | queue_id | e.g. "16INR0049" |
| `Project Name` | project_name | |
| `Interconnecting Entity` | developer | |
| `County` | county | Always Texas |
| `Projected COD` | expected_cod | |
| `Fuel` | fuel_type | 3-letter code (see mapping below) |
| `Technology` | facility_type | 2-letter code (see mapping below) |
| `Capacity (MW)` | mw_capacity | |
| `Screening Study Started` | queue_date | Used as the queue entry date |
| `IA Signed` | (status logic) | If has date → "Completed", if null → "Active" |

**Fuel code mapping:**

| Code | Meaning |
|---|---|
| SOL | Solar |
| WIN | Wind |
| GAS | Gas |
| MWH | Battery Storage |
| OIL | Oil |
| WAT | Hydro |
| HYD | Hydrogen |
| OTH | Other |

**Technology code mapping:**

| Code | Meaning |
|---|---|
| PV | Photovoltaic |
| BA | Battery Energy Storage |
| WT | Wind Turbine |
| CC | Combined-Cycle |
| GT | Gas Turbine |
| ST | Steam Turbine |

**Solar detection:** `Fuel` code is "SOL" (mapped to "Solar" during transform).

**State:** Always "TX" — hardcoded since ERCOT only covers Texas.

### Numbers (as of 2026-03-01)

- Total projects in "Large Gen" sheet: 1,831
- Solar projects >= 20 MW: 639

---

## CAISO

### Data Source

- **Type:** Excel file (.xlsx) at a stable, permanent URL
- **URL:** `http://www.caiso.com/PublishedDocuments/PublicQueueReport.xlsx`
- **Auth:** None
- **Stability:** High — same URL always points to the latest report

### Excel Structure

The file has 3 sheets, each representing a different project status:

| Sheet Name | Content | Footer Rows to Trim |
|---|---|---|
| `Grid GenerationQueue` | Active/queued projects | Last 8 rows (legend) |
| `Completed Generation Projects` | Projects that went online | Last 2 rows (footer) |
| `Withdrawn Generation Projects` | Withdrawn projects | Last 2 rows (footer) |

All sheets: skip first 3 rows (`skiprows=3`) to get past the title header.

**Quirk:** The Withdrawn sheet names the project column `"Project Name - Confidential"` instead of `"Project Name"`. We rename it during parsing.

**Quirk:** Column names contain embedded newlines from multi-line Excel headers. For example:
- `"Interconnection Request\nReceive Date"`
- `"Current\nOn-line Date"`
- `"Proposed\nOn-line Date\n(as filed with IR)"`

You must match these exactly when referencing columns in code.

**Key columns:**

| Excel Column | Maps To | Notes |
|---|---|---|
| `Queue Position` | queue_id | e.g. "124" |
| `Project Name` | project_name | |
| `Utility` | developer | PG&E, SCE, SDG&E, etc. |
| `County` | county | |
| `State` | state | Mostly CA, some AZ/NV |
| `Net MWs to Grid` | mw_capacity | Total net capacity |
| `Queue Date` | queue_date | |
| `Current\nOn-line Date` | expected_cod | Falls back to `Proposed\nOn-line Date` |
| `Application Status` | status | Or inferred from sheet name |
| `Type-1`, `Type-2`, `Type-3` | fuel_type / generation_type | Joined as "Photovoltaic + Storage" |

**Generation type values:** Photovoltaic, Solar Thermal, Storage, Wind Turbine, Combined Cycle, Combustion Turbine, Hydro, Cogeneration, Gas Turbine, Reciprocating Engine, Steam Turbine, Other.

**Solar detection:** Any of Type-1/2/3 contains "Photovoltaic" or "Solar Thermal".

**Solar+Storage detection:** Types include both a solar type and "Storage".

### Numbers (as of 2026-03-01)

- Total projects across all 3 sheets: 2,278
- Solar projects >= 20 MW: 1,114 (160 active, 113 completed, 841 withdrawn)

---

## Comparison

| | MISO | ERCOT | CAISO |
|---|---|---|---|
| **Source type** | JSON API | Excel (dynamic URL) | Excel (static URL) |
| **URL discovery** | Static endpoint | JSON doc listing → DocID → download | Static endpoint |
| **Parsing complexity** | Low (JSON) | High (30 header rows, coded values, status inference) | Medium (3 sheets, footer trimming, newline column names) |
| **Solar field** | `fuelType` = "Solar" | `Fuel` = "SOL" (mapped) | `Type-1/2/3` = "Photovoltaic" |
| **Fragility** | Low | Medium (depends on doc listing API + Excel format stability) | Low |
| **Solar projects >= 20 MW** | 2,103 | 639 | 1,114 |
| **Total** | | | **3,856** |

---

## Supabase Schema Decisions

### Why Supabase

Supabase gives us Postgres (full SQL, JSONB, indexes) with a built-in REST API and JS client, which means:
- The scrapers (Python) can write directly via the `supabase-py` client using the service-role key.
- The frontend (Next.js) can read directly via the `@supabase/ssr` client using the anon key.
- No custom API server needed. The dashboard talks straight to the database through Supabase's auto-generated REST layer.

For Phase 1 with ~4k rows and a single dashboard, this eliminates an entire backend service.

### `projects` table

The schema is designed around one question: "What does a sales rep need to see to decide if a lead is worth pursuing?"

**Columns that come directly from ISO data:**
- `queue_id` + `iso_region` — the natural composite key. Each ISO has its own ID scheme (MISO: "J3464", ERCOT: "16INR0049", CAISO: "124"), so the pair is what makes a row unique.
- `project_name`, `developer`, `state`, `county` — identification and location.
- `mw_capacity` — project size, critical for filtering and scoring.
- `fuel_type` — "Solar" or "Solar+Storage", classified by our filter logic from raw ISO fields.
- `queue_date`, `expected_cod` — timeline context. Queue date = when it entered the pipeline. Expected COD = when they plan to be operational.
- `status` — Active / Completed / Withdrawn.

**Columns for future phases (currently NULL):**
- `epc_company` — the EPC contractor. ISOs don't publish this; we'll fill it from other sources in later phases.
- `latitude`, `longitude` — geocoded location. Would require a geocoding step from state/county. Needed for a future map view.

**Operational columns:**
- `source` — always "iso_queue" for now. Future phases may add projects from permit databases, news scraping, etc. This lets the dashboard distinguish where a lead came from.
- `lead_score` — precomputed 0-100 score, recalculated on each scrape run. Stored in the row so the frontend can sort/filter without recomputing.
- `raw_data` (JSONB) — the full original record from the ISO. Acts as an audit trail. If we later realize we need a field we didn't map, we can extract it from raw_data without re-scraping.
- `created_at`, `updated_at` — auto-managed timestamps. `updated_at` uses a Postgres trigger so it changes on every upsert, letting us detect stale records.

**Dedup constraint:** `UNIQUE(iso_region, queue_id)`. This is what makes upserts idempotent — running the scraper twice produces the same rows, not duplicates. Supabase's `.upsert(records, on_conflict="iso_region,queue_id")` does an INSERT or UPDATE based on this constraint.

### `scrape_runs` table

A lightweight audit log. Each scraper execution creates one row at start (`status=running`) and updates it at end (`status=success` or `status=error`). Tracks:
- How many projects were found and upserted per run.
- Error messages if something broke.
- Timestamps for "when was this data last refreshed."

The dashboard reads the most recent run's `completed_at` to display "Last Updated."

### Row-Level Security (RLS)

- **Read:** Public. The dashboard uses the Supabase anon key, which can SELECT from both tables. No user auth needed for Phase 1 — it's an internal tool.
- **Write:** Service-role only. The scrapers use the service-role key, which bypasses RLS. The anon key cannot INSERT, UPDATE, or DELETE. This prevents the public-facing dashboard from being a write vector.

### Indexes

Indexes on: `iso_region`, `fuel_type`, `state`, `status`, `mw_capacity`, `lead_score DESC`, `queue_date DESC`. These map directly to the dashboard's filter and sort operations. With ~4k rows they're not strictly necessary for performance, but they cost nothing to maintain and will matter if the dataset grows.

---

## Lead Scoring Heuristic

### Design Philosophy

The score is a **rough prioritization tool**, not a predictive model. It answers: "If I can only look at 50 projects today, which 50 should they be?" It's intentionally simple — 4 factors, all derivable from ISO queue data, no external enrichment needed.

Score range: 0–100. Higher = better lead.

### Current Scoring Breakdown

| Factor | Condition | Points | Reasoning |
|---|---|---|---|
| **Capacity** | >= 500 MW | 30 | Bigger farms = more robot units needed = higher deal value |
| | >= 200 MW | 25 | |
| | >= 100 MW | 20 | |
| | >= 50 MW | 15 | |
| | < 50 MW | 10 | Still above our 20 MW floor but smaller opportunity |
| **Status** | Active | 25 | Active projects are real opportunities you can act on |
| | Completed | 10 | Already built — might need expansion/rework but less likely |
| | Other (Withdrawn, etc.) | 5 | Mostly dead, but kept for pattern spotting |
| **Timeline** | COD within 2 years | 30 | Ground breaks soon — most actionable window for Civ's robots |
| | COD within 3 years | 20 | Planning phase, good for early engagement |
| | COD within 5 years | 10 | Early stage, worth tracking but not urgent |
| | No COD or > 5 years | 0 | Too speculative to prioritize |
| **Type** | Solar+Storage | 15 | Hybrid projects are larger, more complex, higher value |
| | Solar only | 5 | Still a lead, just simpler scope |

**Maximum possible score:** 30 + 25 + 30 + 15 = **100** (a 500+ MW, active, Solar+Storage project with COD within 2 years).

**Minimum realistic score:** 10 + 5 + 0 + 5 = **20** (a small, non-active, solar-only project with no timeline).

### What The Score Does NOT Consider (Phase 1 Limitations)

- **Developer track record.** A project from a developer who has completed 10 solar farms is more likely to proceed than one from an unknown entity. We don't have this data yet.
- **Permitting status.** ERCOT includes some permit fields (Air Permit, GHG Permit, Water Availability) that signal how far along a project is. We store these in `raw_data` but don't score on them yet.
- **Geographic density.** Multiple projects in the same county could mean a single site visit covers several leads. Not factored in.
- **EPC company.** Whether a project has an EPC already (and who it is) would be a strong signal. Not available from ISO data.
- **Study phase progression.** ISOs track study milestones (screening, feasibility, interconnection agreement). Projects further along are more likely to break ground. We store the raw phase data but don't interpret it yet.

### Future Scoring Improvements

Phase 2+ scoring should evolve in these directions:

1. **Developer scoring.** Cross-reference developers across projects. If "NextEra Energy" appears on 50 completed projects and 20 active ones, their active projects should score higher than a first-time developer's.
2. **Permit progress weighting.** For ERCOT specifically, factor in whether air permits, GHG permits, and water availability have been secured. Each secured permit adds confidence.
3. **Study phase weighting.** Projects with signed Interconnection Agreements (IA) are far more likely to proceed than projects still in screening. This data is already in `raw_data` — just needs scoring logic.
4. **Historical movement tracking.** Compare `raw_data` across scrape runs to detect projects that are progressing (status changes, new milestone dates) vs. stalled.
5. **ML-based scoring.** Once we have enough data on which projects actually reached construction (from the Completed sheets), we could train a simple classifier to predict construction likelihood from queue attributes.

---

## Pipeline Architecture Decisions

### Base Class Pattern

All 3 scrapers extend `BaseScraper` (in `scrapers/base.py`). Each scraper only implements one method: `fetch_and_transform()`, which returns a DataFrame with standardized columns. The base class handles everything else — filtering, scoring, upserting, batching, logging, error handling.

**Why:** The pipeline steps (filter → score → upsert → log) are identical across ISOs. Only the data fetching and column mapping differ. The base class means adding a 4th ISO (e.g., PJM, SPP) is just:
1. Write a `fetch_and_transform()` that returns a DataFrame.
2. Add one line to `main.py`.

If an ISO's data source breaks, the scraper can override `fetch_and_transform()` with a completely different approach (different URL, different format) and the rest of the pipeline doesn't change.

### Batch Upserts (500 rows per batch)

Supabase's REST API has payload size limits. Sending all 2,100 MISO records in one request risks hitting those limits or timing out. Batching at 500 rows is conservative enough to stay well under limits while minimizing the number of API calls (MISO = 5 batches, ERCOT = 2, CAISO = 3).

### Transform Per ISO, Filter/Score Shared

Each ISO has its own `transform_*()` function in `transform.py` because every ISO uses different column names, codes, and formats. But once transformed into the standardized schema, the filter and scoring logic is shared — `filters.py` and `scoring.py` don't know or care which ISO the data came from.

**Why this split matters:** Solar detection is trickier than it looks. MISO says "Solar" in `fuelType`. ERCOT says "SOL" in a 3-letter code. CAISO says "Photovoltaic" in `Type-1`. The transform layer normalizes all of these so the filter can just check for the keywords "solar" and "photovoltaic" in a consistent set of columns.

### Raw Data Preservation

Every project stores the full original record in `raw_data` (JSONB). This was a deliberate trade-off: it makes rows larger (~2-3 KB each vs. ~500 bytes for just the mapped columns), but it means we never lose information. When we later decide we need ERCOT's "CDR Reporting Zone" or CAISO's "TPD Allocation Group", we can extract it from existing data without re-scraping.

### Sequential ISO Execution (Not Parallel)

`main.py` runs scrapers sequentially in a for loop, not in parallel threads. With 3 scrapers each taking 10-30 seconds, the total runtime is ~1 minute. Parallelizing would save maybe 40 seconds but add threading complexity and make error handling harder to reason about. For a weekly cron job, 1 minute vs. 20 seconds doesn't matter.

### Scrape Logging as a Separate Table

Scrape run metadata lives in `scrape_runs`, not embedded in the project rows. This means:
- We can see "ERCOT failed last Monday" without scanning project rows.
- The dashboard can show "Last Updated" with a single query.
- If a scrape produces 0 results (API down), we still have a record that it ran and failed, rather than just an absence of updates.

---

## Known Risks

1. **ERCOT Excel format changes.** The header row position (row 30) and column names could change in future reports. The scraper will error if this happens — check scrape_runs for failures.
2. **ERCOT document listing.** If `IceDocListJsonWS` goes down or changes format, we can't discover the latest report. Fallback: manually update the `doclookupId` in the scraper.
3. **CAISO footer rows.** We trim 8 footer rows from the active sheet and 2 from the others. If CAISO changes their footer, we might include junk rows or lose real data.
4. **MISO User-Agent.** If MISO tightens their bot detection beyond a simple User-Agent check, we may need to rotate headers or add delays.
