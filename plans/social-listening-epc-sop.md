# Social Listening → EPC Lead Qualification SOP

Standard operating procedure for using social listening tools to identify and qualify solar EPC contractor leads for Civ Robotics outreach.

---

## Overview

**Goal:** Find the right *people* at solar EPC companies who would buy autonomous layout robots, using social listening platforms to surface contacts and buying signals.

**Time:** ~2 hours for initial setup + research, then 30 min/week to monitor.

**Output:** Qualified lead list with company intel, decision-maker contacts, and buying signals ranked by priority.

---

## Step 1: Platform Setup

### 1a. Add Company Domain

- **Website Domain:** `https://www.civrobotics.com/`
- **Product description:** Autonomous layout robots for utility-scale solar farm construction — GPS-guided robots that stake/mark panel and pile locations on solar sites, replacing manual surveying crews.

### 1b. Create Personas

Create **4 custom personas** (the platform's built-in sales/marketing personas don't fit hardware sales to construction):

| Persona | Description |
|---------|-------------|
| **EPC Project Manager / Construction Manager** | Manages utility-scale solar construction. Oversees site prep, pile driving, tracker/panel installation. Responsible for timelines, crew allocation, cost control. Works at solar EPCs. |
| **VP of Operations / VP of Construction** | Owns construction execution across multiple solar projects. Evaluates and approves new construction technology. Focused on scaling capacity and reducing per-MW cost. |
| **VP of Preconstruction / Estimating** | Leads preconstruction planning, site layout, cost estimating. Coordinates with engineering on tracker layouts and site civil plans. |
| **Director of Innovation / Technology** | Scouts and pilots emerging construction tech (robotics, drones, digital twins). Champions adoption internally. Runs POC evaluations. |

### 1c. Configure Filters (per persona)

**For VP of Operations / VP of Construction:**
- **Countries:** United States
- **Company Size:** 50–10,000 employees
- **Job Titles (fuzzy):** VP of Operations, VP of Construction, Vice President Operations, Vice President Construction, SVP Construction, SVP Operations, Director of Construction, Director of Operations, Head of Construction, Chief Operating Officer, VP Field Operations, VP Project Execution, General Manager Construction, VP Solar Construction, Director of Field Operations, VP Preconstruction

**For EPC Project Manager / Construction Manager:**
- **Countries:** United States
- **Company Size:** 50–10,000 employees
- **Job Titles (fuzzy):** Project Manager, Construction Manager, Senior Project Manager, Solar Project Manager, Solar Construction Manager, Field Construction Manager, Site Manager, Area Construction Manager, Project Director, Field Manager, Superintendent, General Superintendent, Project Superintendent, Construction Superintendent, Field Operations Manager, Site Construction Manager, Project Engineer

### 1d. Set Keywords

**Competitors (high signal):**
- Civ Robotics, Dusty Robotics, Rugged Robotics, Charge Robotics, Built Robotics, Terabase Energy

**Product/category:**
- Solar Layout Automation, Autonomous Staking, Robotic Site Marking, Utility Solar Robotics

**Industry (moderate signal, higher volume):**
- solar EPC, utility-scale solar construction, solar pile driving, solar site survey, solar tracker installation, construction robotics solar, solar labor shortage, solar construction technology, preconstruction solar

**Tracker OEMs (their customers = our customers):**
- Nextracker, Array Technologies

**Events/community:**
- RE+ conference, Intersolar, SEIA

**Keywords to SKIP (too noisy):**
- KUKA Construction Robotics (industrial/manufacturing, not solar)
- Sunstall Solar (modular installation, not layout)
- Generic "construction automation" or "robotics in construction" (too broad)

---

## Step 2: Initial Lead Triage

Once the platform returns results, run this triage to separate real prospects from noise.

### Discard immediately:
- **Developers/IPPs** (NextEra, Apex, Pattern, EDF, Origis, Clēnera, Con Edison, Duke Energy) — they hire EPCs, they don't buy construction equipment
- **Module/tracker manufacturers** (Gibraltar, Nextracker as employer) — equipment suppliers, not customers
- **C&I-only installers** (ForeFront Power, Cenergy) — too small, wrong project type
- **Non-solar contractors** — general contractors, gas/wind-only, electrical distribution

### Keep and prioritize:
- Companies that **self-perform EPC** on utility-scale solar (>50 MW)
- Contacts with titles that control **field operations or technology adoption**
- Multiple employees from same company = active hiring = active construction

### Tier the results:

| Tier | Criteria | Action |
|------|----------|--------|
| **Tier 1** | Self-performing solar EPC + VP/Director-level contact + active projects | Outreach this week |
| **Tier 2** | Solar EPC + PM/Superintendent contact + known projects | Outreach this month |
| **Tier 3** | Solar-adjacent or developer with construction management | Monitor, don't outreach yet |
| **Drop** | Non-solar, C&I-only, manufacturers, developers | Remove from list |

---

## Step 3: Deep-Dive Research (Agent Prompt)

For Tier 1 and Tier 2 companies, paste this prompt into the platform's agent to get actionable intel:

```
For each of these confirmed solar EPC companies, find the answers to
these questions. Search their websites, press releases, job postings,
LinkedIn, and news articles:

COMPANIES: [paste company names here]

FOR EACH COMPANY FIND:

1. ACTIVE PROJECTS: What utility-scale solar projects (>50 MW) do they
   have under construction RIGHT NOW or breaking ground in 2026?
   List project name, location, MW size, and expected completion.

2. AWARDED CONTRACTS: Any recently announced EPC contract wins that
   haven't started construction yet? These are upcoming layout needs.

3. HOW THEY DO LAYOUT TODAY: Any mention of their surveying/staking
   process? Do they use manual crews, Dusty Robotics, GPS rovers,
   total stations, or any other method? Check job postings for
   "surveyor", "layout", "staking" roles — active hiring for these
   roles means they still do it manually.

4. PAIN POINTS: Any mentions of project delays, labor shortages,
   rework issues, or schedule overruns? Check news, Glassdoor reviews,
   and industry articles.

5. TECHNOLOGY ADOPTION: Do they mention using construction tech,
   robotics, drones, digital twins, or automation anywhere? Companies
   that already adopt tech are easier to sell to.

6. KEY DECISION MAKERS: Beyond the contacts we already have, who else
   at the company holds these titles: VP Construction, VP Operations,
   VP Preconstruction, Director of Innovation, Head of Field Operations?
   List name and title.

7. UPCOMING EVENTS: Are any of these companies presenting at,
   sponsoring, or attending RE+, Intersolar, or other solar conferences
   in 2026?

Format as a table per company. Flag any company that is still hiring
manual surveyors — that is the #1 buying signal for our product.
```

---

## Step 4: Buying Signal Scoring

After the deep-dive, score each company:

| Signal | Points | Why |
|--------|--------|-----|
| **Actively hiring surveyors/staking roles** | +5 | They're spending money on the exact thing we replace |
| **Already uses construction robotics** (Built, Charge, Swap) | +4 | Proven tech buyer, short sales cycle |
| **Multiple active projects >100 MW** | +3 | High volume = high ROI for our robot |
| **VP/Director-level contact in hand** | +3 | Can actually make the purchase decision |
| **Attending RE+ or Intersolar** | +2 | Face-to-face demo opportunity |
| **Vertically integrated (own EPC, not subbed out)** | +2 | Controls their own construction process |
| **Public mentions of labor shortage or schedule pressure** | +1 | Aware of the problem we solve |

**Priority brackets:**
- **12+ points:** Hot lead — outreach immediately with personalized pitch
- **8–11 points:** Warm lead — outreach within 2 weeks
- **4–7 points:** Monitor — add to nurture, revisit quarterly

---

## Step 5: Follow-Up Research Prompt

For the top 3 scored companies, run this second agent prompt to get outreach-ready intel:

```
For SOLV Energy, Blattner, and Strata Clean Energy specifically:

1. Find the exact job posting URLs for their surveyor/staking roles.
   I want to reference these in outreach ("I noticed you're hiring
   survey techs for your Texas sites...").

2. For each active construction project, what tracker system are they
   using? (Nextracker, Array, FTC Solar, GameChange) Tracker type
   affects layout complexity and staking density.

3. What is their typical project timeline from site mobilization to
   pile driving start? Any public references to how long their
   survey/layout phase takes?

4. Who are their surveying subcontractors, if any? Check for
   subcontractor bid postings or vendor lists.

5. For companies using Built Robotics or other automation: what is
   the handoff workflow between their survey crew and the next
   construction step? Our robot could feed coordinates directly —
   that's the integrated pitch.
```

---

## Step 6: Cross-Reference with ISO Queue Data

After qualifying leads through social listening, cross-reference against our own pipeline:

```bash
cd agent
python -c "
import os
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

from supabase import create_client
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])

# Search for EPC companies found via social listening
epcs = ['SOLV Energy', 'Blattner', 'Moss', 'Strata Clean Energy']

for epc in epcs:
    resp = client.table('projects').select(
        'project_name, state, mw_capacity, iso_region, expected_cod'
    ).ilike('epc_company', f'%{epc}%').execute()

    if resp.data:
        print(f'\n{epc} — {len(resp.data)} projects in our queue data:')
        for p in resp.data:
            print(f'  {p[\"project_name\"]} | {p[\"state\"]} | {p[\"mw_capacity\"]}MW | COD:{p[\"expected_cod\"]}')
    else:
        print(f'\n{epc} — not yet in our queue data (run batch discovery)')
"
```

If an EPC isn't in your data yet, run batch EPC discovery on projects in their known states/regions (see `batch-research-runbook.md`).

---

## Step 7: Weekly Monitoring

Set up recurring monitoring (30 min/week):

1. **Check new social listening alerts** — new people matching personas, new keyword mentions
2. **Re-run deep-dive prompt** on any new Tier 1 companies
3. **Check for new surveyor job postings** at existing Tier 1 targets (signal they're ramping a new project)
4. **Update scoring** as new intel comes in
5. **Cross-reference** any new EPC names against ISO queue data

---

## Reference: Known EPC Landscape

### Tier 1 National EPCs (primary targets)
- SOLV Energy, Blattner (Quanta), Moss, Strata Clean Energy, McCarthy Building Companies, Primoris, Mortenson, MasTec

### Tier 2 Regional / Integrated EPCs
- BayWa r.e., Hanwha Q CELLS EPC, OCI Energy, Berry Construction, Signal Energy, Swinerton, RES (Renewable Energy Systems), JUWI

### Developers (NOT buyers — they hire the EPCs above)
- NextEra, Invenergy, AES, Lightsource bp, Savion, Clearway, Apex, EDF Renewables, Pattern Energy, Origis, Clēnera

### Tracker OEMs (their projects = our opportunity)
- Nextracker, Array Technologies, FTC Solar, GameChange Solar
