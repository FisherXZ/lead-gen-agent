# Gap 2: Local Permitting Data as a Signal Source

**Date:** 2026-03-02
**Status:** Problem definition — no implementation yet

---

## Context

Our EPC discovery design identifies 5 disclosure channels: developer press releases, trade publications, EPC portfolio websites, SEC filings, and state utility commission filings. All 5 focus on the **financial close → construction** window.

But there's an entire upstream data layer we're not touching: local (county/city) permit records. These are public records that surface at multiple points in the development timeline and contain information we can't get anywhere else.

## What Local Permits Reveal

### Zoning / Conditional Use Permits (CUP)
- **Filed by:** Developer
- **When:** 1-3 years before construction
- **What it tells us:** The project is real enough that someone is spending money on land-use approvals. Includes project location, developer name, MW capacity, and sometimes site plans.
- **Public?** Yes — county planning commission records, often with public hearing schedules.

### Building & Electrical Permits
- **Filed by:** The EPC contractor (not the developer)
- **When:** Weeks to months before construction starts
- **What it tells us:** **The EPC's name is on the permit application.** This is potentially the most direct EPC disclosure channel — more reliable than press releases, earlier than trade publications.
- **Public?** Yes — county/city building department records.

### Grading / Earthwork Permits
- **Filed by:** EPC or civil subcontractor
- **When:** Immediately before site work begins
- **What it tells us:** Construction is imminent. This is the moment Civ Robotics' autonomous layout robots become relevant — survey and layout work happens right after grading.
- **Public?** Yes — county grading/engineering department.

## The Problem

Our 5 existing channels are all indirect — they report on EPC relationships after the fact (press releases, articles, portfolio pages). Local permits are **primary source documents** where the EPC is named as the permit applicant. We're ignoring the most direct signal.

Additionally, permit filings are **stage indicators** (see Gap 1). A CUP filing tells us the project is past the speculative phase. A building permit tells us the EPC is engaged. A grading permit tells us construction is weeks away.

## Why This Is Hard

County permit data is **fragmented across thousands of jurisdictions**. There's no national permit database. Each county has its own system — some have online portals, some require FOIA requests, some are paper-only.

However, this fragmentation has a silver lining: it means this data is hard for competitors to aggregate too. If we can crack access for even the top 20-30 counties by solar activity (mostly in TX, CA, AZ, NV, IN, OH), we'd cover a disproportionate share of utility-scale projects.

## Potential Access Paths

1. **County online portals** — Many large counties have searchable permit databases (e.g., Travis County TX, Maricopa County AZ). Could be scraped or queried via the EPC discovery agent.
2. **Third-party aggregators** — Services like BuildZoom, Construction Monitor, or Dodge Data aggregate permit data nationally. These are paid APIs but could shortcut the fragmentation problem.
3. **State-level aggregation** — Some states (notably CA via CEQA clearinghouse) aggregate environmental permits statewide.
4. **Agent-based research** — The EPC discovery agent could be given a tool to search county permit records for a specific project, rather than building automated scrapers for every county.

## What "Solved" Looks Like

Local permitting becomes a 6th EPC disclosure channel. When the agent researches a project, it checks relevant county permit records alongside trade pubs and press releases. Building permit applications that name the EPC get `confidence: "confirmed"` because the EPC is literally the applicant of record.

Permit filings also feed lifecycle stage tracking (Gap 1) — each permit type maps to a specific stage in the project progression.

## Open Questions

- Which counties have the most utility-scale solar activity? Need to prioritize the top 20-30.
- Are third-party permit aggregators (BuildZoom, Dodge) worth the cost, or is targeted county-level access sufficient?
- How do we match a county permit record to a project in our ISO queue database? (Project names may differ between the interconnection application and the building permit.)
- Should this be an automated scraping channel or an agent tool that searches on-demand?

## Related Docs

- [03-epc-discovery.md](roadmap/03-epc-discovery.md) — the 5 existing channels (this would be Channel 6)
- [gap-1-project-lifecycle-stages.md](gap-1-project-lifecycle-stages.md) — permits as stage indicators
- [gap-3-sales-timing-signals.md](gap-3-sales-timing-signals.md) — grading permits as the sales trigger
