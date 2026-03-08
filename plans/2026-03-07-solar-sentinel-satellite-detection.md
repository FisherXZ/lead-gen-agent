# Solar Sentinel — Satellite-Based Construction Detection

**Date:** 2026-03-07
**Status:** Plan — future phase
**Origin:** Liav's concept doc (`Solar_Sentinel_Project_Brief.docx`)
**Core idea:** Monitor satellite imagery of permitted solar project sites to detect construction starts before competitors know a project has broken ground.

---

## Why This Matters

Civ Robotics needs to reach EPC contractors at the right moment — after ground-breaking but before they've committed to a layout workflow. Today that's word-of-mouth. Solar Sentinel turns it into a systematic, automated signal across all permitted US solar projects.

---

## Imagery Sources Evaluated

### Google Maps Static/Tiles API
- **Resolution:** 0.15–5m (varies; rural sites often 1–5m)
- **Freshness:** Poor — 6 months to 2+ years old in rural areas, no update schedule
- **Access:** Immediate. 100K free tile requests/month, $2/1000 beyond
- **Use case:** Agent spot-checks, Phase 0 validation
- **Limitation:** ToS gray area for mass automated analysis; stale imagery

### Sentinel-2 via Google Earth Engine (GEE)
- **Resolution:** 10m (RGB + NIR for NDVI)
- **Freshness:** Excellent — 2–5 day revisit at US latitudes
- **Access:** Free non-commercial (quota tiers enforced April 27, 2026). Commercial = GCP billing
- **Use case:** Automated NDVI change detection at scale
- **Limitation:** Too coarse for visual classification — algorithmic only
- **Key dates:** Verify non-commercial eligibility by Sept 2025. Partner Tier apps by March 31, 2026

### NAIP (National Agriculture Imagery Program)
- **Resolution:** 0.3–0.6m — can see individual panel rows
- **Freshness:** Terrible — each state updated every 2–3 years
- **Access:** Completely free, public domain, available in GEE
- **Use case:** High-res historical baseline for before/after comparison
- **Limitation:** Useless for timely detection

### Planet Labs (PlanetScope / SkySat)
- **Resolution:** 3–5m daily (PlanetScope), 50cm on-demand (SkySat)
- **Freshness:** Best in class — daily global coverage
- **Access:** Paid, not publicly priced. ~$20+/sq km for SkySat tasking
- **Use case:** Production-grade daily monitoring (endgame)
- **Limitation:** Expensive. Planet + Anthropic partnership (March 2025) may simplify later
- **Note:** Planet Labs announced a partnership with Anthropic to use Claude for satellite imagery analysis

### Landsat (NASA/USGS)
- **Resolution:** 30m, 16-day revisit
- **Access:** Free, 40+ year archive
- **Verdict:** Skip — Sentinel-2 is strictly better at 3x resolution and 3x frequency

### Claude Vision (classifier, not a source)
- **Input:** High-res tiles (Google Maps, NAIP, Planet). Not useful on raw Sentinel-2 at 10m
- **Cost:** ~$0.01 per image
- **Output:** Construction phase label (land clearing / construction start / panel installation / no change / unclear) + confidence score
- **Validated by:** Planet + Anthropic partnership using Claude for satellite analysis at scale

---

## Detection Logic (from Liav's document)

**Stage 1 — Spectral Change Detection (GEE/Sentinel-2)**
- Compare recent 15-day composite vs. 30-day-prior baseline
- NDVI delta > 0.15 = candidate signal (conservative; > 0.25 = high confidence)
- Bare earth % > 30% of AOI = change event triggered
- Require persistence across 2+ observations to reduce false positives from seasonal variation

**Stage 2 — AI Visual Classification (Claude Vision)**
- Only triggered for AOIs that pass Stage 1 thresholds
- 512x512 RGB tile exported from GEE (or fetched from Google Maps for higher res)
- Claude classifies into: Land Clearing / Construction Start / Panel Installation / No Change / Unclear
- Minimum 70% confidence before creating a lead

---

## Integration with Existing System

### What we already have
- `projects` table has `latitude` and `longitude` columns (DOUBLE PRECISION) — but all NULL
- Agent tool pattern in `agent/src/agent.py`: tool definition dict → handler in run loop → implementation module
- `raw_data` JSONB column may contain ISO-specific coordinates (CAISO includes POI coords)

### What's missing
- **Geocoding** — no scraper populates lat/lon, no geocoding service exists in the pipeline
- **Coordinate passthrough** — `build_user_message()` in `prompts.py` doesn't include lat/lon
- **Satellite implementation module** — needs `agent/src/satellite.py`

---

## Implementation Phases

### Phase 0: Manual Validation (no code)
- Pick 3–5 projects from ISO queue with known locations
- Google Maps → zoom in → visually confirm construction is visible
- Screenshot evidence for stakeholders
- **Goal:** Prove the concept works with zero investment

### Phase 1: Geocoding (prerequisite for all satellite work)
- Extract POI coordinates from `raw_data` JSONB where available (CAISO)
- Geocode remaining projects from state/county via Census Geocoder (free) or Google Geocoding API
- Populate `latitude`/`longitude` columns in `projects` table
- Update `build_user_message()` in `prompts.py` to pass coordinates to the agent
- **Effort:** Medium
- **PR scope:** Geocoding pipeline + coordinate population

### Phase 2: Agent Spot-Check Tool
- New module: `agent/src/satellite.py`
  - Fetch Google Maps Static API tile at project lat/lon (zoom 17–18)
  - Send tile to Claude Vision with construction phase prompt
  - Return: phase label, confidence, reasoning
- Add `check_satellite_imagery` tool to `TOOLS` list in `agent/src/agent.py`
- Add handler in `run_agent_async()` tool execution loop
- Update system prompt in `prompts.py` to instruct agent when to use satellite check
- Optionally expose in chat agent (`chat_agent.py`) for interactive use
- **Cost:** ~$2/month (within free tier)
- **Effort:** Medium
- **PR scope:** Satellite tool + prompt updates

### Phase 3: Automated NDVI Monitoring (Solar Sentinel core)
- Register GEE non-commercial project (earthengine.google.com)
- Build `sentinel_monitor.py`:
  - Load AOIs from projects table (where lat/lon is not null)
  - Fetch Sentinel-2 composites via GEE Python API
  - Compute NDVI delta + bare earth % per AOI
  - Flag sites exceeding thresholds (persistent across 2+ observations)
- Flagged sites → fetch high-res tile → Claude Vision classification
- Store results in a new `satellite_observations` table
- Weekly cron job (GitHub Actions or local)
- **Cost:** ~$5–20/month
- **Effort:** High
- **PR scope:** GEE pipeline + observation storage + scheduling

### Phase 4: CRM + Alerts (SEPARATE PR)
> This phase is intentionally scoped as its own PR, independent of satellite detection.
- HubSpot deal creation for confirmed leads (confidence >= 70%)
  - Deal name: `[SATELLITE] {Project Name} — {Phase}`
  - Pipeline stage mapped from construction phase
  - Deal value: MW capacity x $8,000
  - Close date: projected 180/90/30 days based on phase
- Slack webhook alerts to sales team
  - Project name, EPC, state, phase, confidence, coordinates, HubSpot deal ID
- **Depends on:** Phase 3 producing reliable detections
- **PR scope:** HubSpot integration + Slack alerts + confidence threshold tuning

### Phase 5: Premium Imagery (if ROI proven)
- Planet Labs integration for daily 3–5m monitoring on high-priority sites
- SkySat tasking for 50cm imagery on hottest leads
- Leverage Planet + Anthropic integration as it matures
- Construction progress dashboard (map view of all monitored sites)
- **Trigger:** Phase 3–4 proves the concept generates real sales conversations

---

## Cost Summary

| Phase | Monthly Cost |
|-------|-------------|
| Phase 0 (manual) | $0 |
| Phase 1 (geocoding) | $0–5 (Census Geocoder is free) |
| Phase 2 (spot-check tool) | ~$2 (within Google Maps free tier) |
| Phase 3 (NDVI monitoring) | ~$5–20 (GEE free + Claude Vision API) |
| Phase 4 (CRM + alerts) | $0 (HubSpot + Slack existing integrations) |
| Phase 5 (Planet Labs) | $1,000+/month |

---

## Open Questions
- [ ] Is Civ Robotics' use considered commercial for GEE? May need commercial tier for production
- [ ] Which ISOs include POI coordinates in their queue data? (CAISO likely does)
- [ ] Google Maps ToS — is automated tile fetching for analysis acceptable at our scale?
- [ ] Confidence threshold calibration — 70% may need tuning after dry-run testing
- [ ] Should Phase 2 spot-check results feed back into lead scoring?

---

## References
- Liav's document: `Solar_Sentinel_Project_Brief.docx`
- [Sentinel-2 in Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/sentinel-2)
- [GEE Non-commercial Tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers)
- [Planet + Anthropic Partnership](https://www.businesswire.com/news/home/20250306606139/en/)
- [Claude Vision Docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Google Maps Static API Billing](https://developers.google.com/maps/documentation/maps-static/usage-and-billing)
- [NAIP in Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/USDA_NAIP_DOQQ)
