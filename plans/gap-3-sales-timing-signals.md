# Gap 3: NTP and Grading Permits as Sales Timing Signals

**Date:** 2026-03-02
**Status:** Problem definition — no implementation yet

---

## Context

Our system's current goal: identify the EPC contractor for a project → surface it as a sales lead. But the research into the developer → EPC workflow reveals that **knowing the EPC is necessary but not sufficient**. The timing of when you reach out matters as much as knowing who to call.

Civ Robotics sells autonomous layout robots used during the construction phase — specifically in the window between site grading and tracker installation. That window opens at a very specific point in the project lifecycle.

## The Timing Problem

Today, our system treats these two scenarios identically:

**Scenario A:** We discover that McCarthy is the EPC for a 500MW project in Texas. The project just reached financial close. Construction is 12-18 months away.

**Scenario B:** We discover that McCarthy is the EPC for a 300MW project in Arizona. NTP was issued last month. Grading permits were pulled two weeks ago. Crews are mobilizing.

Both show up in the dashboard as "EPC: McCarthy, Confidence: Confirmed." But Scenario B is an **urgent sales opportunity** — the equipment is needed in weeks, not months. Scenario A is a warm lead to nurture.

## What Makes This a Gap

Our lead scoring formula is: `f(MW capacity, ISO status, region, EPC known)`. There's no time-urgency component. We don't capture or surface:

- **NTP (Notice to Proceed):** The contractual moment when the EPC is authorized to start. This is the clearest signal that construction is imminent. It's sometimes announced in press releases or trade publications.
- **Grading/earthwork permits:** Filed at the county level (see Gap 2). Means site prep is starting — Civ's robots are needed very soon.
- **Equipment procurement signals:** Panel and tracker orders, which sometimes appear in trade press. Indicates construction timeline is locked.
- **Construction mobilization:** Job postings, equipment rentals, subcontractor RFPs. Hard to systematically track but sometimes visible.

## The Sales Window for Civ Robotics

```
                    Too Early              Sweet Spot           Too Late
                        │                     │                    │
Financial ──── NTP ──── Grading ──── Civil ──── Tracker ──── Commissioning ──── PTO
  Close       Issued    Permits      Work     Install
                        │                     │
                   Civ enters here      Civ's work done here
```

The ideal outreach window is **NTP issued → grading permits pulled**. That gives Civ time to get into the conversation before the civil work subcontractor is locked. After tracker installation begins, it's too late.

## What "Solved" Looks Like

Leads in our system have a **urgency tier** alongside the lead score:

- **Tier 1 — Active opportunity:** NTP issued or grading permits pulled in the last 30 days. EPC known. Surface immediately with alert.
- **Tier 2 — Near-term pipeline:** Financial close completed. EPC likely known or discoverable. 3-12 months from construction.
- **Tier 3 — Watch list:** Project in queue, permits in progress. EPC may not be selected yet. 1-3 years out.
- **Tier 4 — Early stage:** Just entered queue. Zoning not yet secured. Low priority.

This urgency tier is driven by lifecycle stage signals (Gap 1), particularly permit data (Gap 2). The dashboard surfaces Tier 1 and Tier 2 leads prominently. Tier 1 triggers notifications.

## How This Changes Our Architecture

1. **Lead scoring** needs a time dimension — not just "how big and where" but "how soon."
2. **The EPC discovery agent** should report timing signals alongside EPC identity. When it finds a press release about NTP, that's a scoring event, not just an EPC confirmation.
3. **Notifications** (Phase 6 in our roadmap) become more valuable — a Tier 1 alert about NTP + grading permits is highly actionable.
4. **The dashboard** needs to distinguish between "we know the EPC" (informational) and "this project is mobilizing now" (action required).

## Open Questions

- How reliably can we detect NTP? It's sometimes in press releases but not always public.
- Can we build a reliable signal from grading permit filings for the top solar counties?
- Should urgency tier be a computed field (from lifecycle stage + dates) or an agent judgment call?
- How does Civ Robotics' actual sales cycle length compare to the NTP → grading window? If their sales cycle is 3 months, we need to be reaching out at financial close, not NTP.

## Related Docs

- [gap-1-project-lifecycle-stages.md](gap-1-project-lifecycle-stages.md) — the stage model that urgency tiers are built on
- [gap-2-local-permitting-data.md](gap-2-local-permitting-data.md) — permits as the primary signal source for timing
- [03-epc-discovery.md](roadmap/03-epc-discovery.md) — current EPC discovery (needs timing dimension)
- [09-implementation-phases.md](roadmap/09-implementation-phases.md) — where this fits in the build sequence
