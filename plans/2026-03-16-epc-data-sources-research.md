# EPC Data Sources Research — Beyond the Known Sources

**Date:** 2026-03-16
**Purpose:** Comprehensive catalog of publicly accessible data sources for identifying which EPC contractors are building utility-scale solar projects in the US.

**Known sources (already on our radar):** ISO queues (ERCOT, CAISO, MISO, PJM), FERC eLibrary, EIA-860, state PUCs (Ohio OPSB, Texas PUCT, Nevada PUCN), SEC EDGAR, press releases, trade pubs (Solar Power World, PV Tech, ENR), EPC company websites, county records.

---

## Plain English

This document catalogs every publicly accessible database, registry, and filing system in the US that could help us figure out which EPC contractor is building a specific solar project. The sources range from federal databases with downloadable spreadsheets (easy) to state-by-state permit portals that would need individual scraping (hard). The highest-value new finds are: the FAST-41 Federal Permitting Dashboard (names contractors in permit filings), BLM active project lists (federal land solar), state renewable energy siting offices (especially NY ORES and VA DEQ), Army Corps NWP-51 permits (wetland impacts name the builder), the Wiki-Solar database (30% of utility-scale projects have EPC data), LBNL/USGS databases (free downloadable project-level data), and the various REC tracking systems (WREGIS, GATS, M-RETS) which register generators by owner.

---

## Tier 1: HIGH VALUE — Likely Names EPCs or Developers Directly

### 1. FAST-41 Federal Permitting Dashboard
- **URL:** https://www.permits.performance.gov/projects/fast-41-covered
- **What it contains:** Federal permitting timelines for large infrastructure projects including solar. Tracks all federal agency reviews (BLM, USACE, FWS, EPA) for covered projects.
- **Names EPCs?** Yes — permit applications typically name the developer and construction contractor.
- **Accessibility:** Web-browsable, some documents downloadable. No API.
- **Notes:** Only covers projects that opt into FAST-41 coverage. Multiple solar projects tracked (Samantha Solar, Pantheon Solar, Royal Slope Solar, Silver Star Solar, Bonanza Solar, etc.).

### 2. BLM Active Solar and Wind Projects
- **URL:** https://www.blm.gov/programs/intermittent-energy/active-solar-and-wind-projects
- **What it contains:** All active renewable energy projects on BLM-managed federal land. 120+ approved projects, 54 in preliminary review (35 solar), 131 additional applications.
- **Names EPCs?** Project applications name developers; EPC may appear in right-of-way filings and environmental documents.
- **Accessibility:** Web table with links to individual project pages and MLRS reports. ArcGIS maps available for CA projects.
- **Notes:** Covers western states (11 states, 31M+ acres open for solar). Critical for desert Southwest projects.

### 3. Wiki-Solar Database
- **URL:** https://wiki-solar.org/company/contractor/
- **What it contains:** 25,000+ utility-scale solar projects globally (4 MWAC+). Tracks owners, developers, EPC contractors, O&M contractors, module suppliers, inverter suppliers, landowners, off-takers, and financiers.
- **Names EPCs?** Yes, explicitly — EPC is a dedicated data field. However, only ~30% of projects have EPC data filled in.
- **Accessibility:** Partially free (top lists published as PDFs). Full database appears to be commercial/subscription.
- **Notes:** Published top EPC lists semi-annually. Most recent: SOLV Energy #1 at 13.2 GW AC.

### 4. New York ORES (Office of Renewable Energy Siting)
- **URL:** https://ores.ny.gov/permit-applications
- **What it contains:** All permit applications for renewable energy projects 25 MW+ in New York State.
- **Names EPCs?** Applications require description of "experience and expertise of persons who will develop, design, construct, and operate the project."
- **Accessibility:** Online portal with application documents. Interactive ArcGIS dashboard at https://www.arcgis.com/apps/dashboards/4841a0a133524fceb6ff1ca0d8dcaf06
- **Notes:** Replaced Article 10 process. Now under Public Service Law Article VIII (RAPID Act, effective April 2024).

### 5. Virginia DEQ Renewable Energy Permits + REDA Atlas
- **URL:** https://www.deq.virginia.gov/permits/renewable-energy
- **REDA Map:** https://geohub-vadeq.hub.arcgis.com/
- **Solar Permit Map:** https://solarpermitmap.coopercenter.org/
- **What it contains:** All utility-scale solar facility permits in Virginia (both DEQ Permit by Rule and SCC permits). REDA provides georeferenced permit boundaries aligned with parcel data.
- **Names EPCs?** Permit applications name the developer and engineering firms; construction contractor may be named.
- **Accessibility:** GIS viewer, downloadable data.
- **Notes:** Virginia is one of the fastest-growing solar states. Two permitting paths: DEQ (PBR for <=150 MW) and SCC (larger projects).

### 6. USACE Nationwide Permit 51 (Land-Based Renewable Energy)
- **URL:** https://permits.ops.usace.army.mil/
- **What it contains:** Army Corps Section 404/Section 10 permits for solar projects that impact wetlands or waterways. NWP-51 is specifically for land-based renewable energy generation facilities.
- **Names EPCs?** Pre-construction notifications (PCNs) name the applicant/permittee, which is typically the developer or EPC contractor.
- **Accessibility:** Regulatory permit database is searchable online. Individual district offices also maintain records.
- **Notes:** Any solar project disturbing wetlands needs this permit. Covers construction activities including access roads, laydown areas, and panel arrays.

### 7. Illinois Commerce Commission — Certified Utility-Scale Solar Installers
- **URL:** https://icc.illinois.gov/authority/utility-scale-solar-installers
- **What it contains:** Registry of entities certified to install utility-scale solar projects in Illinois (83 Ill. Adm. Code Part 461).
- **Names EPCs?** Yes — this IS a list of certified solar EPCs/installers.
- **Accessibility:** Web page, likely downloadable.
- **Notes:** Illinois requires certification for any entity performing utility-scale solar installations. Other states may have similar registries.

### 8. CEQAnet (California Environmental Quality Act Database)
- **URL:** https://ceqanet.lci.ca.gov
- **What it contains:** All CEQA environmental review documents since 1990. Includes EIRs, Negative Declarations, and related documents for California solar projects.
- **Names EPCs?** Environmental documents frequently name the project applicant, developer, and sometimes the EPC contractor. Always name consulting engineering firms.
- **Accessibility:** Searchable online database with full-text document downloads.
- **Notes:** California is the largest solar market. Every utility-scale project goes through CEQA review. Searchable by project type.

### 9. Minnesota PUC Energy Infrastructure Permitting
- **URL:** https://puc.eip.mn.gov/solar
- **What it contains:** All solar projects 50 MW+ requiring Minnesota PUC site permits. Application documents, docket filings, permit conditions.
- **Names EPCs?** Applications name developers and engineering consultants; EPC may be named in construction plans.
- **Accessibility:** Online portal with document downloads. eDockets system at mn.gov/puc/edockets.

### 10. Virginia SCC Docket Search
- **URL:** https://www.scc.virginia.gov/docketsearch
- **What it contains:** All regulatory filings for energy projects in Virginia, including utility petitions for solar project approval.
- **Names EPCs?** Docket filings name developers and often reference construction contracts/contractors.
- **Accessibility:** Searchable database with document downloads.

---

## Tier 2: MEDIUM VALUE — Names Developers/Owners, EPC Sometimes Discoverable

### 11. USGS Large-Scale Solar Photovoltaic Database (USPVDB)
- **URL:** https://energy.usgs.gov/uspvdb/
- **Viewer:** https://energy.usgs.gov/uspvdb/viewer/
- **What it contains:** 4,400+ large-scale PV facilities (1 MW+ DC) with locations, array boundaries, panel type, site type, initial year of operation. Version 3.0 (April 2025).
- **Names EPCs?** No — tracks plant attributes, not construction details. But useful for identifying projects to cross-reference.
- **Accessibility:** Free download in Shapefile, GeoJSON, CSV. REST web services available. Public domain data.
- **Notes:** Position-verified from aerial imagery to within 10 meters. Excellent for geographic analysis.

### 12. LBNL Utility-Scale Solar Data
- **URL:** https://emp.lbl.gov/utility-scale-solar
- **Data download:** https://data.openei.org/submissions/8541
- **What it contains:** Project-level data on 1,760+ solar projects. Includes deployment, technology, cost, performance, PPA pricing, and value metrics.
- **Names EPCs?** Not directly, but contains owner/developer data that can be cross-referenced.
- **Accessibility:** Free download from OEDI. Annual updates.

### 13. EIA-860M Monthly Generator Inventory
- **URL:** https://www.eia.gov/electricity/data/eia860m/
- **What it contains:** Monthly updates on status of existing and proposed generators 1 MW+. Tracks solar projects from proposed through under-construction to operational. Includes owner/operator data.
- **Names EPCs?** Names owners and operators, not EPCs directly. But early-stage project entries often list the developer who is also the EPC.
- **Accessibility:** Free Excel downloads, monthly updates.
- **Notes:** More current than annual EIA-860. Shows construction pipeline in near real-time.

### 14. Interconnection.fyi
- **URL:** https://www.interconnection.fyi/
- **What it contains:** 30,000+ interconnection queue projects across all US ISOs and utilities, updated daily. Tracks from application through commercial operation.
- **Names EPCs?** Names the queue applicant (developer), not EPC. But developer name is a strong lead for EPC identification.
- **Accessibility:** Free web viewer. GridTracker enterprise platform for additional features.
- **Notes:** Aggregates queues across PJM, MISO, ERCOT, CAISO, SPP, NYISO, ISO-NE, and non-ISO utilities. Excellent for tracking project pipeline.

### 15. SEIA Major Solar Projects List
- **URL:** https://seia.org/research-resources/major-solar-projects-list/
- **What it contains:** 8,500+ ground-mounted solar projects (1 MW+), representing 359+ GWdc. Includes operating, under construction, and under development projects.
- **Names EPCs?** Full member database includes owner, electricity purchaser, land type, expected online date. EPC may be included.
- **Accessibility:** Public interactive map (free). Full searchable Excel database requires SEIA membership (paid). Updated monthly.
- **Notes:** Data gathered from press releases, company announcements, and conversations with developers.

### 16. DOE Loan Programs Office Portfolio
- **URL:** https://www.energy.gov/lpo/portfolio-projects (now under Office of Energy Dominance Financing)
- **What it contains:** $30B+ portfolio of loans, loan guarantees, and conditional commitments for energy projects including solar.
- **Names EPCs?** Project documentation names developers and often references EPC agreements.
- **Accessibility:** Portfolio list is public. Individual project details available via FOIA or public documents.

### 17. REC Tracking Systems (WREGIS, GATS, M-RETS, NC-RETS, NEPOOL GIS, NVTREC)
- **WREGIS:** Western US — tracks generators from small rooftop to large wind/solar
- **GATS:** PJM region (mid-Atlantic, parts of Midwest)
- **M-RETS:** Midwest
- **NC-RETS:** North Carolina (ncrets.org)
- **NEPOOL GIS:** New England (nepoolgis.com)
- **What they contain:** Generator registrations, REC issuance, ownership, and retirement. Every utility-scale solar plant must register.
- **Names EPCs?** Names generator owners/operators, not EPCs. But registration data reveals project developers.
- **Accessibility:** Varies by system. Some have public generator registries; most require account creation.
- **Notes:** These systems collectively cover all US regions. Generator registration data often includes commissioning dates, capacity, and location — useful for identifying new projects.

### 18. EMMA (Electronic Municipal Market Access)
- **URL:** https://emma.msrb.org/
- **What it contains:** Municipal bond filings, official statements, continuing disclosures for municipal finance including solar project revenue bonds and green bonds.
- **Names EPCs?** Official statements for solar project bonds frequently name the EPC contractor as a material party.
- **Accessibility:** Free, searchable online. Keyword search available.
- **Notes:** Particularly useful for publicly financed solar projects (municipal utilities, state agencies like NYSERDA). Bond official statements are treasure troves of project detail.

### 19. DOE Tribal Energy Projects Database
- **URL:** https://www.energy.gov/indianenergy/tribal-energy-projects-database
- **Interactive Map:** https://www.energy.gov/indianenergy/tribal-energy-projects-database-interactive-map
- **What it contains:** Energy projects on tribal lands funded by DOE Office of Indian Energy. Filterable by state, technology, project category.
- **Names EPCs?** Project descriptions name participating entities, which may include construction partners.
- **Accessibility:** Free, filterable web table and interactive map.

### 20. FERC Form 556 (Qualifying Facility Certifications)
- **URL:** https://www.ferc.gov/qf
- **What it contains:** All self-certifications and applications for Qualifying Facility status under PURPA. Solar facilities >1 MW must file.
- **Names EPCs?** Names the facility owner/operator, not EPC. But filing entity is often the developer.
- **Accessibility:** Electronic filing system (eFiling). Searchable.

---

## Tier 3: SUPPLEMENTARY — Project Intelligence, Cross-Reference Value

### 21. PUDL (Public Utility Data Liberation Project)
- **URL:** https://catalyst.coop/pudl/ | https://data.catalyst.coop/
- **GitHub:** https://github.com/catalyst-cooperative/pudl
- **What it contains:** Open-source ETL pipeline that cleans and integrates EIA-860, EIA-923, FERC Form 1, EPA CEMS, and other federal energy data into analysis-ready databases.
- **Names EPCs?** No — but makes owner/operator data far more accessible and cross-referenceable than raw EIA data.
- **Accessibility:** Free, open source. Available on AWS, Kaggle, Zenodo. Python API.
- **Notes:** Excellent for programmatic access to EIA generator/owner data. Actively maintained.

### 22. Open Energy Data Initiative (OEDI)
- **URL:** https://data.openei.org/
- **What it contains:** 1,700+ energy datasets from DOE programs and national labs. Includes solar project data, capacity factors, performance data.
- **Names EPCs?** Varies by dataset. Some project-level data includes developer information.
- **Accessibility:** Free download. Also available via AWS Open Data Registry.

### 23. EPA RE-Powering America's Land Initiative
- **URL:** https://www.epa.gov/re-powering
- **What it contains:** 190,000+ contaminated/landfill/mine sites screened for renewable energy. Tracks 459 completed renewable energy installations and 200+ in development.
- **Names EPCs?** Project tracking matrix names developers and may reference construction entities.
- **Accessibility:** Interactive mapping tool, downloadable tracking matrix (PDF/spreadsheet).

### 24. E2 Clean Economy Works Project Tracker
- **URL:** https://e2.org/project-tracker/ | https://e2.org/announcements/
- **What it contains:** 415+ major clean energy projects announced since August 2022 (IRA passage). Tracks investments, jobs, cancellations.
- **Names EPCs?** Names the announcing company (usually developer/manufacturer). EPC sometimes referenced.
- **Accessibility:** Free interactive map and announcements list.

### 25. Rhodium Group / MIT Clean Investment Monitor
- **URL:** https://www.cleaninvestmentmonitor.org/
- **What it contains:** Quarterly tracking of public and private investments in clean energy manufacturing and deployment across US. $278B invested in past four quarters.
- **Names EPCs?** Facility-level project tracking includes company names, but focused on investors/developers rather than EPCs.
- **Accessibility:** Free interactive data visualization and mapping. Detailed data on ClimateDeck (subscription).

### 26. Cleanview
- **URL:** https://cleanview.co/
- **What it contains:** 10,000+ power projects and 1,000+ data centers tracked. Monthly market reports. Claims 97% developer identification rate for tracked projects.
- **Names EPCs?** Names developers. EPC data unclear.
- **Accessibility:** Project Explorer is free. Full platform/alerts are subscription.
- **Notes:** Newer entrant in clean energy market intelligence. Monthly Power Market Reports.

### 27. NABCEP Professional Directory
- **URL:** https://directories.nabcep.org/
- **What it contains:** Directory of certified solar installation professionals and accredited companies.
- **Names EPCs?** Yes — this is essentially a directory of qualified solar installers/contractors.
- **Accessibility:** Free searchable directory.
- **Notes:** NABCEP (North American Board of Certified Energy Practitioners) certification is the industry standard. Useful for identifying potential EPCs but doesn't tie them to specific projects.

### 28. IREC National Solar Licensing Database
- **URL:** https://irecusa.org/solar-licensing-database/
- **What it contains:** Licensing, certification, and other requirements impacting the solar industry, organized by state.
- **Names EPCs?** References to state-specific contractor licensing requirements and databases.
- **Accessibility:** Free web tool.

### 29. Ohm Analytics
- **URL:** https://www.ohmanalytics.com/
- **What it contains:** Proprietary database of US solar, storage, and electrification projects aggregated from thousands of sources. Real-time market trends and research reports.
- **Names EPCs?** Likely includes installer/contractor data given their "Solar Company Data Partnership" offering.
- **Accessibility:** Subscription/commercial.

### 30. U.S. Fish & Wildlife Service — ECOS and IPaC
- **URL:** https://ecos.fws.gov/ | https://ipac.ecosphere.fws.gov/
- **What it contains:** Environmental consultations, habitat conservation plans, biological opinions for solar projects near endangered species habitat.
- **Names EPCs?** Habitat Conservation Plans name the applicant (developer), and construction methodology sections may reference the EPC.
- **Accessibility:** ECOS is free and searchable. Note: Solar/wind projects currently require Office of the Secretary review before IPaC use.

### 31. DOE Solar Energy Research Database
- **URL:** https://www.energy.gov/eere/solar/solar-energy-research-database
- **What it contains:** Active SETO-funded solar research and development projects. Map and database table sortable by program area, state.
- **Names EPCs?** Names award recipients (companies/labs), not field EPCs.
- **Accessibility:** Free, searchable.

### 32. USDA REAP (Rural Energy for America Program)
- **URL:** https://www.rd.usda.gov/programs-services/energy-programs/rural-energy-america-program-renewable-energy-systems-energy-efficiency-improvement-guaranteed-loans
- **What it contains:** $2B+ in grants and loans for rural renewable energy projects. 8,012 clean energy projects funded with IRA money.
- **Names EPCs?** Award announcements sometimes name the recipient and project details. Contractor info may be in application documents.
- **Accessibility:** Grant recipient lists published by congressional delegation offices (e.g., Senator Baldwin's office published Wisconsin REAP recipients).

### 33. State SHPO (State Historic Preservation Office) Section 106 Reviews
- **Various state URLs** (e.g., NY: parks.ny.gov/shpo, MN: mn.gov/admin/shpo)
- **What it contains:** Cultural resource reviews for solar projects on federal land or with federal nexus.
- **Names EPCs?** Reviews name the project applicant and consulting firms.
- **Accessibility:** Varies by state. Many now have online submission portals (NY CRIS, CT CRIS, etc.).

### 34. EPA ECHO (Enforcement and Compliance History Online)
- **URL:** https://echo.epa.gov/
- **What it contains:** Environmental compliance data for EPA-regulated facilities including solar plants with NPDES stormwater permits.
- **Names EPCs?** Names the facility operator (which may be the developer or EPC).
- **Accessibility:** Free, searchable, updated weekly.

### 35. NREL Solar Ordinance Databases
- **URL:** Via data.nrel.gov
- **What it contains:** ~1,000 solar energy zoning ordinances at state, county, township, and city levels. Downloadable spreadsheets + interactive maps.
- **Names EPCs?** No — tracks regulations, not projects. But useful for understanding where projects are possible.
- **Accessibility:** Free download.

### 36. Energy Communities / IRA Bonus Mapper
- **URL:** https://energycommunities.gov/energy-community-tax-credit-bonus/
- **Mapper:** https://www.novoco.com/resource-centers/renewable-energy-tax-credits/inflation-reduction-act-bonus-credits
- **What it contains:** Census tract and MSA/non-MSA designations for energy community bonus credits (10% bonus ITC).
- **Names EPCs?** No — geographic eligibility tool. But projects in these zones are more likely to be built.
- **Accessibility:** Free interactive maps.

---

## Tier 4: COMMERCIAL/SUBSCRIPTION — Comprehensive but Paid

### 37. S&P Global Market Intelligence (formerly IHS Markit)
- **URL:** https://www.spglobal.com/esg/s1/topic/solar-energy-storage.html
- **What it contains:** Largest dedicated solar project database globally — 115,000+ projects. Tracks EPCs, developers, owners, module/inverter suppliers.
- **Names EPCs?** Yes, explicitly. Dedicated EPC tracking field with market share analysis.
- **Accessibility:** Commercial subscription.

### 38. Wood Mackenzie / US Solar Market Insight
- **URL:** https://www.woodmac.com/industry/power-and-renewables/solar-data-hub/
- **What it contains:** Quarterly data on US solar from ~200 utilities, state agencies, installers, manufacturers. Project-level pipeline data with GIS overlays.
- **Names EPCs?** Yes — includes market share analysis of installers (EPCs).
- **Accessibility:** Commercial subscription. Joint publication with SEIA.

### 39. Hitachi Energy Velocity Suite (formerly ABB)
- **URL:** https://www.hitachienergy.com/us/en/products-and-solutions/energy-portfolio-management/market-intelligence-services/velocity-suite
- **What it contains:** 3,000+ data sources integrated. Connects generation assets to transmission, substations, interconnection queues, competitive intelligence.
- **Names EPCs?** Not primarily — focused on asset/market data rather than construction contractors.
- **Accessibility:** Commercial subscription.

### 40. LandGate
- **URL:** https://www.landgate.com/energy-markets/solar-data
- **What it contains:** Parcel-level solar development analysis, siting data, transmission/substation data, interconnection queue data, site control data, PPA/LMP pricing.
- **Names EPCs?** Not directly — focused on site prospecting rather than construction tracking.
- **Accessibility:** Commercial subscription. Enterprise AI agent recently launched.

### 41. LevelTen Energy
- **URL:** https://www.leveltenenergy.com/
- **What it contains:** 470+ developers on platform, 8 GW+ of clean energy procured. PPA marketplace and asset marketplace (5.8 GW+ exchanged).
- **Names EPCs?** Developer data, not EPC specifically.
- **Accessibility:** Platform registration required. PPA Price Index published quarterly.

### 42. PF Nexus
- **URL:** https://www.pfnexus.com/platform/database
- **What it contains:** 7,018+ clean energy developers, investors, lenders globally. Solar PV projects by developer.
- **Names EPCs?** Developer profiles may include EPC capabilities.
- **Accessibility:** Free tier available, premium features subscription.

---

## Summary: Best New Sources to Add to Our Pipeline

| Priority | Source | Names EPC? | Free? | Effort to Integrate |
|----------|--------|------------|-------|---------------------|
| 1 | FAST-41 Federal Permitting Dashboard | Yes (in filings) | Yes | Medium (scrape docs) |
| 2 | BLM Active Projects + MLRS Reports | Yes (in filings) | Yes | Medium (scrape) |
| 3 | Wiki-Solar Top EPC Lists | Yes (explicitly) | Partial | Low (PDF/web) |
| 4 | NY ORES Permit Applications | Yes (in apps) | Yes | Medium (portal scrape) |
| 5 | VA DEQ/REDA Solar Permits | Yes (in apps) | Yes | Medium (GIS + scrape) |
| 6 | USACE NWP-51 Permits | Yes (permittee) | Yes | Hard (per-district) |
| 7 | CEQAnet (California) | Yes (in EIRs) | Yes | Medium (searchable) |
| 8 | EMMA Municipal Bonds | Yes (in OS docs) | Yes | Medium (text mining) |
| 9 | Illinois ICC Certified Installers | Yes (IS the list) | Yes | Low |
| 10 | SEIA Major Projects List | Partial | Membership | Low (if member) |
| 11 | USPVDB + LBNL Data | Owner only | Yes | Low (download) |
| 12 | EIA-860M Monthly | Owner only | Yes | Low (download) |
| 13 | Interconnection.fyi | Developer only | Yes | Low (web/API) |
| 14 | REC Tracking Systems | Owner only | Varies | Medium (per system) |
| 15 | E2 Clean Economy Works | Developer | Yes | Low |
| 16 | State SHPO Reviews | In filings | Varies | Hard (per state) |
| 17 | PUDL/OEDI | Owner only | Yes | Low (Python/API) |

### Recommended Next Steps

1. **Immediate wins (low effort, high value):** Wiki-Solar top EPC lists, Illinois ICC certified installer list, LBNL/USPVDB/EIA-860M downloads for project universe, E2 project tracker, NABCEP directory
2. **Medium-term integrations:** FAST-41 dashboard scraping, BLM active project parsing, CEQAnet solar project searches, EMMA bond document mining, NY ORES application scraping
3. **State-by-state expansion:** VA DEQ REDA, MN PUC eDockets, Virginia SCC docket search, other state PUC/siting offices
4. **Cross-reference strategy:** Use free databases (USPVDB, EIA-860M, interconnection queues) to identify projects, then look up those specific projects in permit/environmental review databases to find the named EPC
