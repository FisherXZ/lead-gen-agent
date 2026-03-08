# Gap 1: Project Lifecycle Stages

**Date:** 2026-03-02
**Status:** Problem definition — no implementation yet

---

## Context

Our system ingests projects from ISO interconnection queues and then tries to discover the EPC contractor. We treat queue entry as the starting signal and EPC identification as the goal. But between those two points, a solar project goes through 6-8 distinct permitting and development stages that we completely ignore.

## The Actual Progression

```
Land lease signed
  → Interconnection application filed (this is where we pick it up)
    → Zoning / Conditional Use Permit (CUP) secured
      → Environmental review completed (NEPA/CEQA, bio surveys, wetlands)
        → Interconnection studies completed (feasibility → system impact → facilities)
          → Financial close (debt + equity committed)
            → EPC contract awarded / NTP issued
              → Grading & earthwork permits pulled
                → Construction (civil → electrical → commissioning)
                  → Permission to Operate (PTO)
```

The full cycle from land lease to PTO is **2-5 years**. Permitting is the biggest variable.

## The Problem

We currently score leads by MW capacity, ISO status field, and region. A project that just entered the ERCOT queue last month and a project that has completed environmental review, secured its CUP, and is weeks from financial close look roughly the same in our system.

This means:
- **We can't prioritize research effort.** The EPC discovery agent wastes cycles on projects that are years from needing an EPC.
- **We can't prioritize sales outreach.** A sales rep looking at our dashboard has no way to tell which projects are imminent vs. speculative.
- **Our lead scoring is coarse.** Score = f(MW, status, region) misses the most important variable: how far along is this project in its development lifecycle?

## What "Solved" Looks Like

Each project has a `lifecycle_stage` that reflects where it sits in the progression above. This stage is derived from signals we collect — ISO status changes, permit filings, press releases, environmental review completions, financial close announcements. The stage directly feeds into lead scoring and determines when the EPC discovery agent should prioritize a project.

## Key Insight

The developer handles everything up through financial close. The EPC enters at NTP. Civ Robotics' equipment is relevant starting at grading/earthwork. So the lifecycle stage tells us:
- **Pre-CUP:** Too early — don't waste research effort
- **CUP secured, environmental done:** Getting real — start monitoring for EPC signals
- **Financial close:** EPC is being selected now — high priority for discovery agent
- **NTP / grading permits:** Sales trigger — the EPC needs layout robots soon

## Open Questions

- What data sources can we use to detect each stage transition? Some are public (permits, press releases), some are not (financial close timing).
- Do we model this as discrete stages or as a confidence-weighted estimate?
- How does this interact with our existing ISO queue status fields (which are one signal among many)?

## Related Docs

- [03-epc-discovery.md](roadmap/03-epc-discovery.md) — current EPC discovery design (doesn't account for lifecycle stage)
- [05-delta-tracking.md](roadmap/05-delta-tracking.md) — change detection (could feed stage transitions)
- [gap-2-local-permitting-data.md](gap-2-local-permitting-data.md) — permits as a data source for stage detection
- [gap-3-sales-timing-signals.md](gap-3-sales-timing-signals.md) — using stage to determine when to sell
