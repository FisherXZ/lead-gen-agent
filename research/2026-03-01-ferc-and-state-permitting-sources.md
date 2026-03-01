# Data Source Research: FERC eLibrary & State Permitting Databases

**Date:** 2026-03-01
**Purpose:** Evaluate FERC eLibrary and state-level permitting databases as enrichment sources for the solar lead-gen pipeline. These would supplement Phase 1's ISO queue data with permitting status, EPC/contractor details, and cross-referenced project intelligence.

---

## 1. FERC eLibrary

### What It Is

FERC eLibrary is the Federal Energy Regulatory Commission's public records information system containing electronic versions of all documents issued by or filed with FERC since 1981 (electronic documents from 1989+, indices from 1981+). It includes filings by parties, public comments, and Commission decisions/notices across all FERC-regulated energy matters.

- **URL:** https://elibrary.ferc.gov/eLibrary/search
- **Cost:** Free, fully public
- **Update Frequency:** Continuous — documents posted as they are filed/issued
- **Content Volume:** Millions of documents across all energy sectors

### What Solar-Related Documents It Contains

FERC eLibrary contains several categories of documents directly relevant to utility-scale solar project tracking:

**Interconnection Agreements (most valuable for our use case):**
- **LGIA (Large Generator Interconnection Agreement):** For generators > 20 MW. These are filed when a solar project signs its interconnection agreement with the transmission provider. Contains: project name, capacity, interconnecting entity, point of interconnection, and sometimes the designated engineering firm.
- **SGIA (Small Generator Interconnection Agreement):** For generators <= 20 MW. Less relevant to our >= 20 MW filter, but borderline projects may appear here.
- **ISA (Interconnection Service Agreement):** Broader category that encompasses interconnection terms.

**Tariff Filings:**
- Transmission providers file tariff amendments when new generators interconnect. These contain project-level details embedded in the tariff filing.

**Service Agreements:**
- Filed between transmission owners and generators. Some contain references to EPC contractors, engineering firms, or construction milestones.

**Rate Schedule Filings:**
- Market-based rate authority (MBR) applications from solar project LLCs. These reveal the corporate structure behind a project (parent company, developer, operator).

**Construction Agreements:**
- Filed for transmission upgrades triggered by new generation interconnection. Can reveal project timelines and associated infrastructure costs.

### Filing Types That Contain EPC or Contractor Information

EPC/contractor info is **not a standard field** in FERC filings. However, it appears in:

1. **LGIA filings (Appendix/Exhibits):** The LGIA itself is a template agreement, but the project-specific exhibits sometimes reference the engineering firm or EPC contractor responsible for interconnection facilities.
2. **Service Agreements (SA) with "EPC" in the description:** Example from recent filings: NorthWestern Corporation filed "SA 1022 - EPC with Idaho Power" (effective 3/4/2026). These explicitly mention EPC relationships.
3. **Construction Agreements:** When the interconnecting generator is responsible for building transmission upgrades, the filing may name the construction contractor.
4. **205(d) Rate Filings:** These tariff filings sometimes include construction budgets, contractor names, and engineering studies as supporting documents.
5. **Environmental Reports/Studies:** Filed as part of the interconnection process, sometimes prepared by or referencing the engineering firm.

**Bottom line:** EPC info is present but buried. You would need to download and parse the actual PDF/DOC attachments, not just the docket metadata. This is a Phase 3+ effort requiring document NLP.

### Data Structure

**Search Interface Fields:**
- Docket Number (with prefix, e.g., ER25-1234)
- Category (Issuance, Submittal)
- Industry sector
- Document Class/Type (dropdown with ~50+ types)
- Security Level
- Filing date, document date, posted date
- Keyword/full-text search
- Company name

**Docket Prefix System (key prefixes for solar):**

| Prefix | Meaning | Solar Relevance |
|--------|---------|-----------------|
| **ER** | Electric Rate filings (replaced old "All Electric Cases") | **Primary** — interconnection agreements, service agreements, tariff filings with solar LLCs |
| **EL** | Electric Complaints | Disputes about interconnection, relevant for tracking troubled projects |
| **QF** | Qualifying Facility certifications | Solar projects seeking PURPA QF status (usually smaller) |
| **RM** | Rulemaking | Policy changes affecting interconnection rules (e.g., Order 2023) |
| **AD** | Administrative proceedings | Policy workshops on interconnection reform |
| **EC** | Electric Corporate (mergers/acquisitions) | When solar developers are acquired or merge |

**Search results return:**
- Accession Number (unique document ID)
- Filed Date
- Description
- Docket Number
- Document Type
- Availability (public/CEII)

### Programmatic Access

**Official API:** FERC has a **Submission API** (for filing documents TO FERC), documented at https://www.ferc.gov/media/ferc-submission-api-step-step-guide. This is for **filers**, not for reading/searching documents. There is **no official read/search REST API**.

**The eLibrary search is a web form** that generates POST requests to a backend server. It is not a clean API — links in search results are not direct URLs but trigger server-side document retrieval via GET/POST requests.

**Community-built tools for programmatic access:**

1. **ferc-elibrary-api** (TypeScript/JavaScript)
   - GitHub: https://github.com/4very/ferc-elibrary-api
   - Docs: https://4very.github.io/ferc-elibrary-api/
   - A wrapper that programmatically interacts with the eLibrary search form
   - 38 commits, 3 releases (as of mid-2024)
   - TypeScript (93.9%), JavaScript (6.1%)

2. **FERC_DOC_TRAIL** (Python/Scrapy)
   - GitHub: https://github.com/VzPI/FERC_DOC_TRAIL
   - Built on the Scrapy framework
   - Extracts all documents and metadata from a given search query or docket number
   - Supports batch docket processing
   - More comprehensive scraping tool

3. **Custom Python scraping** (Medium article by Connor Waldoch)
   - Uses BeautifulSoup and/or Selenium to automate the eLibrary search form
   - FERC's HTML is unfriendly for scraping — links don't point to real URLs, they trigger JS-generated HTTP requests
   - Selenium or similar browser automation is the most reliable approach

**Can it be scraped?** Yes, but with caveats:
- No robots.txt blocking (as of research date)
- The site is JavaScript-heavy; simple HTTP requests won't work for all features
- Browser automation (Selenium, Playwright) is the most reliable method
- Rate limiting is unknown — be respectful with request frequency
- FERC's terms of service should be reviewed before production scraping

### Filing Types Most Relevant for Tracking Solar Projects

**Tier 1 (Direct project intelligence):**
- **ER-prefix LGIA filings** — "Large Generator Interconnection Agreement" in description. Signals a project has passed queue studies and executed its interconnection agreement. This is a strong indicator the project is moving toward construction.
- **ER-prefix LGIA Termination filings** — Signals a project is dead (e.g., "Shy Place Solar Park LGIA Termination" filed 1/2/2026). Useful for marking leads as withdrawn.
- **ER-prefix Service Agreements** — New service agreements between solar LLCs and transmission providers.

**Tier 2 (Supplementary intelligence):**
- **QF certifications** — Small/medium solar projects filing for PURPA qualifying facility status
- **EC-prefix corporate filings** — Mergers/acquisitions of solar developers
- **EL-prefix complaints** — Interconnection disputes (signals project difficulties)

**Tier 3 (Background/policy context):**
- **RM-prefix rulemakings** — FERC Order 2023 interconnection reforms, cluster study rules
- **AD-prefix administrative** — Policy workshops, technical conferences

### How to Cross-Reference FERC Data with ISO Queue Data

**The bridge is the project name + developer + capacity + location.** FERC filings reference the same project entities that appear in ISO queues, but use legal names (LLC entities) rather than the queue's sometimes-abbreviated names.

**Matching strategy:**

1. **Docket number to queue ID:** Some FERC filings explicitly reference the ISO queue position number in the filing description or the agreement text. If parseable from the document, this is a direct match.

2. **Project name fuzzy matching:** FERC filings use the project's legal LLC name (e.g., "Ratts 2 Solar LLC"), while ISO queues may use a different name. Fuzzy string matching on project name is the primary approach.

3. **Developer/interconnecting entity:** Cross-reference the FERC filing party with the ISO queue's developer field.

4. **Capacity + location:** If name matching is ambiguous, use MW capacity + state/county as a secondary filter to disambiguate.

5. **Timeline alignment:** FERC LGIA filings happen after ISO queue studies complete. A project that appears in the ISO queue in 2024 should have its LGIA filing in 2025-2026 if progressing normally.

**Practical approach for our pipeline:**
- Scrape FERC eLibrary for ER-prefix filings with keywords "solar", "photovoltaic", "LGIA", "interconnection agreement"
- Extract project name, filing entity, capacity (if in description), docket number
- Fuzzy-match against our `projects` table on `project_name` + `developer` + `mw_capacity`
- Store the FERC docket number as an enrichment field for cross-reference
- Use LGIA filings to upgrade lead scores (signed IA = stronger signal)

---

## 2. State Permitting Databases

### Overview of State Permitting Landscape

Utility-scale solar permitting in the US is a **fragmented, multi-layered** process. Most states have some combination of:
- State-level siting authority (for projects above a MW threshold)
- State PUC/PSC approval
- County/local land use permits (zoning, conditional use permits)
- Environmental permits (state-level)

There is **no single national permitting database.** Each state (and often each county) has its own system. Below is a state-by-state breakdown for the major solar markets.

### Federal-Level Reference Database: USGS USPVDB

Before diving into state databases, one federal database deserves mention as a cross-reference source:

**U.S. Large-Scale Solar Photovoltaic Database (USPVDB)**
- **URL:** https://energy.usgs.gov/uspvdb/
- **API:** https://energy.usgs.gov/api/uspvdb/v1/projects (full REST API, public, no auth for GET)
- **API Docs:** https://energy.usgs.gov/uspvdb/api-doc/
- **Coverage:** All US PV facilities >= 1 MW
- **Records:** ~3,698 facilities (ver. 3.0, April 2025)
- **Update Frequency:** Periodic releases (v1.0 Nov 2023, v2.0 Aug 2024, v3.0 Apr 2025)
- **Format:** GeoJSON, Shapefile, CSV, or via REST API
- **Cost:** Free, public domain

**Key fields available via API:**

| Field | Description |
|-------|-------------|
| `case_id` | Unique identifier |
| `eia_id` | EIA plant ID (cross-reference to EIA-860) |
| `p_name` | Facility name |
| `p_state`, `p_county` | Location |
| `ylat`, `xlong` | Coordinates |
| `p_cap_ac`, `p_cap_dc` | Capacity (MW AC and DC) |
| `p_year` | Commercial operation year |
| `p_tech_pri` | Primary technology |
| `p_axis` | Tracking type (fixed/single-axis) |
| `p_battery` | Battery co-location flag |
| `p_agrivolt` | Agrivoltaic flag |
| `p_area` | Array area (m^2) |

**API query examples:**
```
# All facilities in Texas over 100 MW AC
GET /projects?p_state=eq.Texas&p_cap_ac=gt.100

# Facilities with battery storage
GET /projects?p_battery=eq.true

# Select specific fields only
GET /projects?select=p_name,p_state,p_cap_ac,p_year&p_cap_ac=gt.50
```

**Limitation:** USPVDB tracks **operational** facilities only. It does not track projects in development or under construction. It is a backward-looking reference, not a forward-looking pipeline. Useful for validating completed projects and understanding developer track records, not for identifying new leads.

**Cross-reference value:** Match USPVDB `eia_id` or `p_name` against ISO queue `project_name` to identify which queued projects have already reached commercial operation.

---

### Texas

**Regulatory Framework:**
- Texas is a **deregulated market** (ERCOT). There is no traditional state-level Certificate of Public Convenience and Necessity (CPCN) for merchant generation.
- **SB 624 (2023 session):** Passed the Senate but ultimately failed. Would have required PUCT permits for wind/solar >= 10 MW.
- **SB 819 (2025 session):** A revived version of SB 624, currently under legislative consideration. Would create a PUCT siting regime requiring permits for solar/wind >= 10 MW, including facility information disclosure, public notice, public meetings, and environmental impact review.
- **Current status (as of March 2026):** The regulatory landscape is in flux. Check whether SB 819 passed in the 89th Legislature (2025 session).

**Where Permits Are Published:**

| Level | Authority | Database | Public? |
|-------|-----------|----------|---------|
| State | PUCT | https://interchange.puc.texas.gov/ | Yes, searchable docket system |
| ISO | ERCOT GIS queue | (Already scraped in Phase 1) | Yes |
| County | Individual county offices | No centralized database | Varies by county |
| Environmental | TCEQ (air quality permits) | https://www.tceq.texas.gov/permitting | Yes, searchable |

**Key data points:**
- **PUCT Interchange:** Searchable by docket number, party name, filing date. Contains utility filings, tariff proceedings, and any required permits under new legislation.
- **ERCOT GIS Report:** Already in our pipeline. Contains interconnection queue with project attributes, milestone dates, and some permit status fields (Air Permit, GHG Permit, Water Availability) — these are already in our `raw_data` JSONB column.
- **County permits:** Texas has 254 counties, each with its own permitting process. No centralized database exists. Some counties (e.g., Pecos, Coke, Scurry — major solar counties) publish conditional use permits on their county websites, but there is no uniform system.
- **TCEQ:** Air quality permits for projects with backup generation. Searchable by facility name and location.

**Cross-reference with ISO queue:** The ERCOT GIS Report already contains permit status fields. The PUCT docket system can be searched by project/developer name to find any state regulatory filings. County permits must be tracked individually.

**Update frequency:** ERCOT GIS Report is monthly. PUCT dockets are updated continuously. County permits have no regular cadence.

**Assessment:** Texas has the weakest centralized state permitting data of the major solar states. ERCOT queue data (already captured) is the best single source. County-level tracking would require building individual scrapers for 20-30 key solar counties — a significant effort with uncertain data quality.

---

### California

**Regulatory Framework:**
California has the most complex permitting structure of any state, with multiple overlapping authorities:

- **CEC (California Energy Commission):** Thermal power plant siting authority for facilities > 50 MW. **Note:** PV solar facilities are NOT "thermal" and do NOT require CEC certification under the Warren-Alquist Act. Only solar thermal (CSP) projects > 50 MW need CEC permits.
- **SPPE (Small Power Plant Exemption):** Facilities 50-100 MW can apply for exemption from CEC jurisdiction. Both thermal and some hybrid projects use this path.
- **CPUC (California Public Utilities Commission):** Regulates investor-owned utilities. CPUC proceedings govern power purchase agreements, grid reliability, and resource procurement.
- **CAISO:** Interconnection queue (already scraped in Phase 1).
- **County/Local:** Land use permits, conditional use permits, environmental review (CEQA).

**Where Permits Are Published:**

| Level | Authority | Database | URL |
|-------|-----------|----------|-----|
| State (thermal only) | CEC Siting | Power Plant Dockets | https://www.energy.ca.gov/proceedings/dockets/california-energy-commission-power-plant-dockets |
| State (thermal only) | CEC eFiling | Docket Log | https://efiling.energy.ca.gov/Lists/DocketLog.aspx |
| State (utilities) | CPUC | Online Documents | https://docs.cpuc.ca.gov/ |
| State (utilities) | CPUC | Proceedings & Rulemaking | https://www.cpuc.ca.gov/proceedings-and-rulemaking |
| ISO | CAISO Queue | (Already scraped in Phase 1) | http://www.caiso.com/PublishedDocuments/PublicQueueReport.xlsx |
| Federal (BLM land) | BLM | NEPA register | https://eplanning.blm.gov/ |

**Key data points:**
- **CEC Power Plant Dockets:** Searchable by docket number (format: YYYY-AFC-XX or YYYY-SPPE-XX). Contains project name, developer, capacity, status, all filings and documents. **Limited relevance for PV solar** since PV is exempt from CEC siting.
- **CPUC Documents:** All filings in CPUC proceedings are publicly available. Searchable by proceeding number, date, party. Contains PPA approvals, resource adequacy proceedings, and IOU solar procurement.
- **CPUC has no API.** The document portal is a web search form. Documents are PDFs.
- **BLM ePlanning:** For solar projects on federal land in the California desert (a major solar zone). Searchable by project name and NEPA status.

**Cross-reference with ISO queue:** CAISO queue data (already captured) is the primary source. CPUC proceedings can be searched by developer name to find PPA filings, which confirm project offtake and increase viability. CEC dockets are only relevant for CSP/thermal solar.

**Assessment:** California's PV solar permitting is primarily at the county level, making centralized tracking difficult. CAISO queue + CPUC PPA proceedings are the best state-level sources. For projects on federal land, BLM ePlanning adds value.

---

### MISO States (IL, IN, IA, MN, MI, and others)

MISO covers 15 states, each with its own permitting regime. The key distinction is between states with **state-level siting authority** (where a state commission reviews large projects) and **local-control states** (where counties have full authority).

#### Minnesota

- **Siting Authority:** Minnesota PUC — site permit required for solar >= 50 MW (Minnesota Statutes Chapter 216E, Rules Chapter 7850)
- **Database:** Minnesota PUC eDockets — https://mn.gov/puc/edockets/
- **Additional:** EERA (Environmental Review) project files at https://eera.web.commerce.state.mn.us/
- **Searchable:** Yes, by docket number, date, party name
- **Fields:** Project name, developer/applicant, capacity, location, status, all filings
- **Public:** Yes, fully public
- **API:** No API. Web form search only.
- **Update Frequency:** Continuous (filings posted as received)
- **Application guidance document:** "Application Guidance for Site Permitting of Solar Farms" (January 2024) details required fields
- **Cross-reference:** Match docket applicant name + project name against MISO queue `poiName` + `transmissionOwner`

#### Michigan

- **Siting Authority:** Michigan PSC (MPSC) — **new as of 2024** under Public Act 233 of 2023. Solar/hybrid facilities >= 50 MW require MPSC certificate.
- **Database:** MPSC e-Dockets (contested case proceedings)
- **URL:** https://www.michigan.gov/mpsc/regulatory/facility-siting/renewable-energy-and-storage-facility-siting
- **Searchable:** Yes, through MPSC case search
- **Fields:** Project name, applicant, capacity, location, setback compliance, status
- **Public:** Yes
- **API:** No API
- **Update Frequency:** Continuous
- **Note:** This is a brand-new process (October 2024 filing procedures approved). Historical projects were permitted entirely at the local level, so older projects will not appear here.
- **Cross-reference:** Match applicant name against MISO queue developer field

#### Illinois

- **Siting Authority:** **Local control** — no state-level siting authority for utility-scale solar. Counties and municipalities have full authority over zoning/siting.
- **State Role:** Illinois Power Agency (IPA) manages renewable energy procurement under the Long-Term Renewable Resources Procurement Plan. IPA conducts competitive procurements for Indexed RECs from utility-scale solar > 5 MW.
- **IPA Database:** https://ipa.illinois.gov/renewable-resources.html — program information, not a project database
- **Procurement Data:** https://www.ipa-energyrfp.com/ — RFP results (winning bidders for renewable energy credits)
- **Illinois Commerce Commission (ICC):** https://www.icc.illinois.gov/ — docket search for utility proceedings
- **No centralized permitting database** for solar projects
- **Cross-reference:** IPA procurement winners can be matched against MISO queue by developer/project name. County-level permits are not centrally tracked.

#### Indiana

- **Siting Authority:** **Primarily local control.** Indiana SB 411 (2022) established voluntary default siting standards. Counties can adopt these or set their own. No mandatory state review.
- **IURC:** Indiana Utility Regulatory Commission — regulates utilities but does not have direct siting authority for merchant solar. IURC filings available at https://www.in.gov/iurc/
- **No centralized permitting database**
- **Cross-reference:** IURC filings searchable by company name; match against MISO queue developer field

#### Iowa

- **Siting Authority:** **Hybrid.** Wind and solar projects > 25 MW must obtain a **generating certificate** from the Iowa Utilities Board (IUB). All land use authority remains at the county level.
- **IUB Database:** https://efs.iowa.gov/ (Electronic Filing System)
- **Searchable:** Yes, by docket number, company, date
- **Fields:** Applicant, project name, capacity, filings
- **Public:** Yes
- **Cross-reference:** IUB generating certificate applicant against MISO queue

#### Other MISO States

| State | Siting Authority | Solar Threshold | Database |
|-------|------------------|-----------------|----------|
| Wisconsin | PSC (hybrid) | 100 MW | https://psc.wi.gov/ |
| Missouri | Local control | N/A | https://www.psc.mo.gov/ |
| Mississippi | PSC | Varies | https://www.psc.ms.gov/ |
| Arkansas | PSC | N/A | http://www.apscservices.info/ |
| Louisiana | PSC | Varies | https://www.lpsc.louisiana.gov/ |

**MISO States Assessment:** Minnesota and Michigan (new) have the best state-level databases. Illinois, Indiana, and Iowa have limited state-level data. For most MISO states, the MISO interconnection queue (already captured) is the single best data source. State permitting data would need to be collected on a per-state basis, with Minnesota and Michigan offering the highest ROI.

---

### Arizona

- **Siting Authority:** Arizona Corporation Commission (ACC) — issues Certificate of Environmental Compatibility (CEC) for power plants and transmission lines.
- **Database:** ACC eDocket — https://edocket.azcc.gov/
- **Docket Search:** https://edocket.azcc.gov/search/docket-search
- **Searchable:** Yes, by docket number, company name, date range
- **Fields:** Applicant, project name, docket number, filing date, status, all documents
- **Public:** Yes, fully public
- **API:** No official API. Web form search interface.
- **Update Frequency:** Continuous
- **Arizona Power Plant & Transmission Line Siting Committee:** Reviews applications, holds public hearings, makes recommendations to the ACC
- **CEC Application Requirements:** Project description, environmental compatibility assessment, location, capacity, construction timeline
- **Cross-reference:** ACC CEC applicant name can be matched against CAISO queue (Arizona projects interconnecting to CAISO) or SPP/WAPA queues. Some Arizona projects appear in our CAISO scrape (the queue includes AZ-sited projects connecting to the CAISO grid).

---

### Nevada

- **Siting Authority:** Public Utilities Commission of Nevada (PUCN) — UEPA (Utility Environmental Protection Act) permits required for renewable energy power plants > 70 MW.
- **Database:** PUCN Docket Information — https://pucweb1.state.nv.us/puc2/Dktinfo.aspx?Util=Electric
- **Approved RE Facilities List:** https://puc.nv.gov/Renewable_Energy/ApprovedREFacilities/ — list of all projects with PUCN-approved UEPA permits and/or PPAs with NV Energy
- **Potential Permits List:** https://puc.nv.gov/Utilities/Construction_Permits/Potential_Permits/
- **Searchable:** Yes, docket search by utility type (Electric), docket number, date
- **Fields:** Project name, applicant, capacity, permit status, PPA status
- **Public:** Yes
- **API:** No API
- **Update Frequency:** Continuous for dockets; Approved RE Facilities list updated periodically
- **Cross-reference:** Many Nevada solar projects appear in the CAISO queue (connecting to CAISO through Path 46 or via NV Energy's ties). Match PUCN applicant against CAISO queue developer. PUCN's "Approved RE Facilities" list is a useful secondary source for validating project status.

---

### North Carolina

- **Siting Authority:** North Carolina Utilities Commission (NCUC) — no separate siting process, but solar projects file as **Small Power Producers (SP docket prefix)** or through utility procurement proceedings.
- **Database:** NCUC Docket Portal — https://starw1.ncuc.net/NCUC/page/Dockets/portal.aspx
- **Search:** https://www.ncuc.gov/search/search.php — supports wildcards (* and ?)
- **Electronic Filing:** https://www.ncuc.gov/efiling.html
- **Searchable:** Yes, by docket number, company name, type. Can filter "SP-Small Power Producer" category.
- **Fields:** Applicant, docket number, filing date, status, all documents
- **Public:** Yes
- **API:** No API
- **Update Frequency:** Continuous
- **Important Context:** North Carolina has historically been a major solar state (#2 in the US by installed capacity). Duke Energy's Carolinas/Progress service territories drive utility-scale solar procurement. HB 951 (2021) set carbon reduction goals that increased utility-scale solar procurement.
- **Cross-reference:** NC is not in MISO, ERCOT, or CAISO — it's in **PJM** (Duke Energy Carolinas/Progress are PJM members). We do NOT currently scrape PJM. To track NC solar projects, we would need to either: (a) add a PJM scraper, or (b) rely solely on NCUC filings.

---

### Florida

- **Siting Authority:** Florida Public Service Commission (FPSC) — regulates IOU rates and services. Florida's **Solar Base Rate Adjustment (SoBRA)** program allows utilities to deploy solar plants < 75 MW with limited regulatory approval if they meet a cost cap.
- **Database:** FPSC Clerk's Office Docket List — https://www.floridapsc.com/ClerkOffice/DocketList?docketType=E
- **Searchable:** Yes, by docket type (E = Electric), docket number, company
- **Ten-Year Site Plans:** Utilities file annual ten-year site plans that detail planned solar additions. Available on the FPSC website.
- **Fields:** Docket number, company, filing date, status, documents
- **Public:** Yes
- **API:** No API
- **Update Frequency:** Continuous for dockets; Ten-Year Site Plans annually (April)
- **Cross-reference:** Florida is not in MISO, ERCOT, or CAISO — it is not in any ISO/RTO. FPL (NextEra) is by far the largest solar developer in Florida and operates as a vertically integrated utility. Tracking Florida solar requires: (a) FPSC docket monitoring for utility solar procurement proceedings, (b) Ten-Year Site Plan analysis, or (c) a future scraper for FRCC/SERC interconnection data.

---

## 3. Comparative Assessment

### Data Source Quality Matrix

| Source | Public | Searchable | Has API | Solar-Specific | EPC Info | Cross-Ref to ISO Queue | Effort to Integrate |
|--------|--------|------------|---------|----------------|----------|------------------------|---------------------|
| FERC eLibrary | Yes | Yes | No (scrapers exist) | Filter by keyword | Rare, in attachments | Medium (name/docket matching) | Medium |
| USGS USPVDB | Yes | Yes | **Yes (REST)** | All solar | No | Medium (name/EIA ID) | **Low** |
| Texas PUCT | Yes | Yes | No | No solar filter | No | High (ERCOT queue cross-ref) | Medium |
| California CEC | Yes | Yes | No | Thermal only | No | Low (PV exempt) | Low value |
| California CPUC | Yes | Yes | No | PPA proceedings | No | Medium | Medium |
| Minnesota PUC | Yes | Yes | No | Site permits >= 50 MW | No | High (MISO cross-ref) | Medium |
| Michigan MPSC | Yes | Yes | No | Site permits >= 50 MW (new) | No | High (MISO cross-ref) | Medium |
| Iowa IUB | Yes | Yes | No | Generating cert > 25 MW | No | High (MISO cross-ref) | Medium |
| Arizona ACC | Yes | Yes | No | CEC applications | No | Medium (CAISO cross-ref) | Medium |
| Nevada PUCN | Yes | Yes | No | UEPA permits > 70 MW | No | Medium (CAISO cross-ref) | Medium |
| North Carolina NCUC | Yes | Yes | No | SP docket category | No | **Requires PJM scraper** | High |
| Florida FPSC | Yes | Yes | No | Utility proceedings | No | **No ISO queue** | High |

### Recommended Integration Priority

**Phase 2 (Near-term, highest ROI):**

1. **USGS USPVDB** — Already has a clean REST API with developer, capacity, location, and operational date. Integrate as a cross-reference to identify which ISO queue projects have already reached commercial operation. Minimal engineering effort.

2. **FERC eLibrary (targeted scraping)** — Scrape ER-prefix filings with "LGIA" + "solar" keywords. LGIA filings confirm a project has signed its interconnection agreement, which is a strong lead-scoring signal. Use the FERC_DOC_TRAIL scraper or build a custom Playwright-based scraper.

**Phase 3 (Medium-term, state-by-state):**

3. **Minnesota PUC eDockets** — Best state-level database in our current MISO coverage area. Site permit applications contain project details not in the MISO queue.

4. **Michigan MPSC** — New process (2024+), so limited historical data, but going forward will be a good source for Michigan solar projects.

5. **Arizona ACC eDocket** — Good CEC application data for Arizona solar projects appearing in our CAISO queue.

**Phase 4 (Longer-term, expansion):**

6. **PJM Queue Scraper** — Required before NC/FL state databases become useful. PJM is the largest ISO by capacity and covers major solar markets (NC, VA, OH, NJ).

7. **North Carolina NCUC** + **Florida FPSC** — Only valuable after PJM queue (or equivalent) is integrated.

8. **County-level permits** — The highest-effort, lowest-reliability data source. Only worth pursuing for specific high-value counties (e.g., Pecos County TX, Imperial County CA) where multiple large projects are clustered.

---

## 4. Key Takeaways

1. **No state has an API for permitting data.** Every state permitting database is a web search form. Scraping is required for all of them.

2. **FERC eLibrary is the richest single federal source** for interconnection agreement data, but EPC/contractor information is buried in PDF attachments, not in structured metadata. Extracting it requires document-level NLP, not just metadata scraping.

3. **The USGS USPVDB is the easiest win** — a free REST API with facility-level data on all US solar installations >= 1 MW. Immediate integration value as a cross-reference.

4. **State permitting data is most valuable in states with centralized siting authority** (MN, MI, NV, AZ). In local-control states (TX, IL, IN), county-level data is fragmented and impractical to collect at scale.

5. **Our biggest geographic gap is PJM territory** (NC, VA, OH, NJ, PA). These are major solar markets that don't appear in our current MISO/ERCOT/CAISO scraping. Adding a PJM queue scraper would dramatically expand coverage.

6. **Cross-referencing is primarily name-based.** There is no universal project ID that spans ISO queues, FERC filings, and state permits. Fuzzy string matching on project name + developer + capacity is the practical approach. Consider building a project entity resolution system in Phase 3+.

---

## Sources

- [FERC eLibrary](https://elibrary.ferc.gov/)
- [FERC eLibrary Search Tips](https://www.ferc.gov/elibrary-search-tips)
- [FERC Docket Prefix List (June 2025)](https://elibrary.ferc.gov/eLibrary/assets/docket-prefix.pdf)
- [FERC Standard LGIA](https://www.ferc.gov/sites/default/files/2020-04/LGIA.pdf)
- [FERC Order 2023 Interconnection Reform](https://www.ferc.gov/explainer-interconnection-final-rule)
- [ferc-elibrary-api (GitHub)](https://github.com/4very/ferc-elibrary-api)
- [FERC_DOC_TRAIL Scraper (GitHub)](https://github.com/VzPI/FERC_DOC_TRAIL)
- [Breaking Down FERC Docket Metadata with Python (Medium)](https://medium.com/@waldoch/breaking-down-ferc-docket-metadata-with-python-ae4464db9945)
- [USGS USPVDB](https://energy.usgs.gov/uspvdb/)
- [USPVDB API Documentation](https://energy.usgs.gov/uspvdb/api-doc/)
- [USPVDB Data (ver. 3.0, April 2025)](https://www.usgs.gov/data/united-states-large-scale-solar-photovoltaic-database-ver-30-april-2025)
- [Texas PUCT](https://www.puc.texas.gov/)
- [Texas SB 819 Analysis](https://capitol.texas.gov/tlodocs/89R/analysis/html/SB00819I.htm)
- [Texas SB 819 Impact on Wind and Solar (K&L Gates)](https://www.klgates.com/Proposed-Texas-Senate-Bills-Have-Potential-Negative-Impacts-on-Wind-and-Solar-1-23-2025)
- [California CEC Power Plant Dockets](https://www.energy.ca.gov/proceedings/dockets/california-energy-commission-power-plant-dockets)
- [CPUC Online Documents](https://docs.cpuc.ca.gov/)
- [Minnesota PUC eDockets](https://mn.gov/puc/edockets/)
- [Michigan MPSC Renewable Energy Siting](https://www.michigan.gov/mpsc/regulatory/facility-siting/renewable-energy-and-storage-facility-siting)
- [Michigan PA 233 Siting Process Approved (Oct 2024)](https://www.michigan.gov/mpsc/commission/news-releases/2024/10/10/commission-approves-application-process-for-renewable-energy-and-energy-storage-siting)
- [Illinois Power Agency Renewable Resources](https://ipa.illinois.gov/renewable-resources.html)
- [IPA 2026 Long-Term Plan](https://ipa.illinois.gov/announcements/illinois-power-agency-files-2026-long-term-renewable-resources-p.html)
- [Indiana IURC](https://www.in.gov/iurc/)
- [Iowa Solar Siting Resource Guide](https://www.iaenvironment.org/webres/File/Solar%20Siting%20Guide%202_20_20.pdf)
- [Arizona ACC eDocket](https://edocket.azcc.gov/)
- [Arizona Power Plant Siting Committee](https://www.azcc.gov/arizona-power-plant/arizona-power-plant)
- [Nevada PUCN Approved RE Facilities](https://puc.nv.gov/Renewable_Energy/ApprovedREFacilities/)
- [Nevada PUCN Docket Information](https://pucweb1.state.nv.us/puc2/Dktinfo.aspx?Util=Electric)
- [North Carolina NCUC Docket Portal](https://starw1.ncuc.net/NCUC/page/Dockets/portal.aspx)
- [Florida PSC Docket List](https://www.floridapsc.com/ClerkOffice/DocketList?docketType=E)
- [LBL Queued Up: Characteristics of Power Plants Seeking Transmission Interconnection](https://emp.lbl.gov/queues)
- [Interconnection.fyi (Daily Queue Updates)](https://www.interconnection.fyi/)
- [Wind, Solar and Siting: Legislative Trends in the Midwest (CSG Midwest)](https://csgmidwest.org/2024/02/29/wind-solar-and-siting/)
- [SEIA Solar State by State](https://seia.org/solar-state-by-state/)
- [IREC Solar Licensing Database](https://irecusa.org/solar-licensing-database/)
