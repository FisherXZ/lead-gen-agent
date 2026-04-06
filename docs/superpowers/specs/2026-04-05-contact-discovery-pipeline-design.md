# Contact Discovery & Persona Classification Pipeline — Design Spec

**Date:** 2026-04-05
**Status:** Draft
**Author:** Fisher + Claude
**Depends on:** Agent Runtime Revamp (`2026-04-05-agent-runtime-revamp-design.md`)

## Problem Statement

Our product finds which EPC contractor is building a solar project. But the sales team can't call a company — they need to call a person. Today there's a basic `find_contacts` tool that does web search for leadership names, but it has no CRM integration, no LinkedIn depth, no persona scoring, and no way to link contacts to specific projects.

The gap: **project → EPC → ???** → person → outreach.

## What We're Building

Two capabilities adapted from The Hog (proven lead discovery SaaS) into our solar EPC pipeline:

1. **Contact Discovery Pipeline** — multi-source search for people at a known EPC, starting with CRM check and fanning out to LinkedIn, EPC websites, OSHA, Exa, and web search
2. **Persona-Based Classification** — 4-stage AI scoring of each contact against a "solar EPC robot buyer" persona, with human override

## Design Principles

- **Third agent configuration** — contact discovery is a sub-agent on the new `AgentRuntime`, same as research. Not a separate pipeline.
- **Agent-orchestrated** — the Claude agent decides search order and adapts based on results. No rigid tiers or waterfall.
- **CRM-first** — always check HubSpot before external sources. Existing relationships are the highest-value signal.
- **Enrich selectively** — only spend API credits (email/phone) on contacts that score ≥ 0.5 on persona match.

## Architecture

```
User: "Find contacts at Signal Energy for the Brazoria project"
    │
    ▼
Chat Agent (AgentRuntime, chat config)
    │
    calls tool: run_contact_discovery(entity_id=..., project_id=...)
    │
    ▼
Contact Discovery Sub-Agent (AgentRuntime, contact_discovery config)
    ├── lookup_hubspot_contacts  (CRM check)
    ├── query_knowledge_base     (prior research check)
    ├── search_linkedin          (LinkedIn search + Apify profile scrape)
    ├── search_exa_people        (AI-powered web people search)
    ├── scrape_epc_website       (team/project pages)
    ├── search_osha              (site-level employer records, existing tool)
    ├── web_search               (press releases, conferences, existing tool)
    ├── save_contact             (persist to DB)
    ├── classify_contact         (4-stage persona scoring)
    ├── enrich_contact_email     (email waterfall)
    └── enrich_contact_phone     (phone waterfall)
    │
    ▼
Returns structured findings to Chat Agent
Chat Agent presents ranked contacts to user
```

Research sub-agent and contact discovery sub-agent can be chained: "research this project" → finds EPC → "find contacts there" → finds people. All in one chat conversation.

## New Tools (8)

### Tool 1: `search_linkedin`

**Source:** Tavily/Brave web search (`site:linkedin.com/in`) + Apify LinkedIn Profile Scraper

**Input:**
```python
class SearchLinkedInInput(BaseModel):
    company_name: str
    role_keywords: list[str] = ["project manager", "VP construction", "director operations"]
    location: str | None = None
    max_results: int = Field(5, ge=1, le=20)
```

**Behavior:**
1. Constructs search query: `site:linkedin.com/in "{company_name}" "{role_keyword}" "{location}"`
2. Runs via Tavily (existing) — returns name, title snippet, LinkedIn URL
3. For top candidates (up to `max_results`), calls Apify LinkedIn Profile Scraper to get full profile: work history, education, headline, location
4. Returns enriched results with both search snippet and full profile data

**Output:**
```json
{
  "status": "success",
  "data": {
    "candidates": [
      {
        "full_name": "Tom Rivera",
        "title": "Senior Project Manager",
        "linkedin_url": "https://linkedin.com/in/tomrivera",
        "headline": "Senior PM | Solar & Renewable Energy",
        "location": "Houston, TX",
        "experience": [
          {"company": "Signal Energy", "title": "Senior PM", "duration": "2023-present"},
          {"company": "Blattner Energy", "title": "Project Manager", "duration": "2019-2023"}
        ],
        "source": "linkedin"
      }
    ]
  }
}
```

**API keys:** `TAVILY_API_KEY` (existing), `APIFY_API_TOKEN` (new)

### Tool 2: `lookup_hubspot_contacts`

**Source:** HubSpot API (private app token from `hubspot_settings` table)

**Input:**
```python
class LookupHubSpotInput(BaseModel):
    company_name: str
    company_domain: str | None = None
```

**Behavior:**
1. Search HubSpot companies by name/domain
2. Get associated contacts for matching company
3. Include deal history and last activity date for each contact

**Output:**
```json
{
  "status": "success",
  "data": {
    "company_found": true,
    "hubspot_company_id": "12345",
    "contacts": [
      {
        "full_name": "Jane Doe",
        "title": "VP Construction",
        "email": "jane@signalenergy.com",
        "phone": "+1-555-0100",
        "last_activity": "2025-08-15",
        "deals": [{"name": "Signal Energy Q3", "stage": "closed-won"}],
        "hubspot_contact_id": "67890"
      }
    ]
  }
}
```

### Tool 3: `search_exa_people`

**Source:** Exa API (AI-powered semantic web search)

**Input:**
```python
class SearchExaInput(BaseModel):
    query: str  # Natural language, e.g. "Signal Energy solar project manager Texas"
    max_results: int = Field(10, ge=1, le=20)
```

**Behavior:** Runs Exa search with `type="auto"`, returns web pages mentioning people at the target company. Agent extracts names/roles from results.

**API key:** `EXA_API_KEY` (new)

### Tool 4: `scrape_epc_website`

**Source:** `fetch_page` (existing tool, reused internally)

**Input:**
```python
class ScrapeEpcWebsiteInput(BaseModel):
    url: str  # e.g. "https://signalenergy.com/about" or "https://signalenergy.com/team"
```

**Behavior:** Fetches the page, returns the content. The agent itself extracts names and roles from the page text (no separate parsing — the model is good at this).

**Note:** This is a thin wrapper on `fetch_page` with a contact-discovery-specific description so the agent knows when to use it.

### Tool 5: `save_contact`

**Source:** Supabase (`contacts` + `project_contacts` tables)

**Input:**
```python
class SaveContactInput(BaseModel):
    entity_id: str          # EPC entity UUID
    project_id: int | None = None
    full_name: str
    title: str | None = None
    linkedin_url: str | None = None
    linkedin_headline: str | None = None
    linkedin_location: str | None = None
    linkedin_experience: list[dict] | None = None
    source_method: str      # 'linkedin', 'hubspot', 'exa', 'epc_website', 'osha', 'web_search'
    source_url: str | None = None
    hubspot_contact_id: str | None = None
    relevance_note: str | None = None  # "Named as site manager in OSHA filing"
```

**Behavior:**
1. Upsert into `contacts` (dedup by entity_id + lower(full_name))
2. If `project_id` provided, insert into `project_contacts` (dedup by project_id + contact_id)
3. If `hubspot_contact_id` provided, store for future sync tracking
4. Returns the contact ID

### Tool 6: `classify_contact`

**Source:** Claude API (structured output, not full agent call)

**Input:**
```python
class ClassifyContactInput(BaseModel):
    contact_id: str
```

**Behavior:**
1. Reads contact from DB (name, title, linkedin_experience, source)
2. Reads the associated EPC entity and project for context
3. Calls Claude with structured output requesting 4 boolean checks + reasoning:
   - `role_aligned`: Is this a construction/operations/PM/procurement role?
   - `is_decision_maker`: VP/Director/Senior level with purchasing authority?
   - `project_relevant`: Tied to this project, region, or solar division?
   - `persona_fit`: Overall match to "person who buys autonomous layout robots for solar farms"
4. Writes results to `contact_persona_scores` table
5. Returns the scores and reasoning

**Model:** Uses Haiku for classification (cheap, fast, structured output is reliable)

### Tool 7: `enrich_contact_email`

**Source:** EnrichmentAPI (primary) → Apollo (fallback)

**Input:**
```python
class EnrichEmailInput(BaseModel):
    contact_id: str
    linkedin_url: str
```

**Behavior:**
1. Call EnrichmentAPI with LinkedIn URL
2. If no result, fall back to Apollo
3. Update `contacts.email` and `contacts.email_source`
4. Return email or null

**API keys:** `ENRICHMENT_API_KEY`, `APOLLO_API_KEY` (both new)

### Tool 8: `enrich_contact_phone`

**Source:** LeadMagic → Prospeo → ContactOut → PDL (waterfall, same as The Hog)

**Input:**
```python
class EnrichPhoneInput(BaseModel):
    contact_id: str
    linkedin_url: str
```

**Behavior:** Waterfall through providers until phone found. Update `contacts.phone` and `contacts.phone_source`.

**API keys:** `LEADMAGIC_API_KEY`, `PROSPEO_API_KEY`, `CONTACTOUT_API_KEY`, `PDL_API_KEY` (all new)

## Tool Implementation Pattern

All 8 new tools use Pydantic input validation and consistent output envelope.

**Input validation** — each tool module exports an `Input` class (Pydantic BaseModel). The registry validates before dispatch:

```python
# In tools/__init__.py execute_tool()
if hasattr(mod, 'Input'):
    try:
        validated = mod.Input(**tool_input)
        tool_input = validated.model_dump()
    except ValidationError as exc:
        return {"error": f"Invalid input: {exc.errors()}", "error_category": "validation_error"}
```

**Output envelope** — every new tool returns:
```python
{"status": "success", "data": {...}, "source": "linkedin"}
{"status": "error", "error": "...", "error_category": "api_error"}
{"status": "partial", "data": {...}, "errors": ["Apify timed out"], "source": "linkedin"}
```

Existing tools (27) are unchanged — they keep their current output shapes. The validation hook is backwards-compatible (only triggers when `Input` class exists).

## Data Model

### Migration 025: Extend contacts + add persona scoring + project linkage

**Extend `contacts` table:**
```sql
ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS phone TEXT,
  ADD COLUMN IF NOT EXISTS email_source TEXT,
  ADD COLUMN IF NOT EXISTS phone_source TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_headline TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_location TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_experience JSONB,
  ADD COLUMN IF NOT EXISTS profile_scraped_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS hubspot_contact_id TEXT;
```

**New table: `project_contacts`**
```sql
CREATE TABLE project_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  relevance_note TEXT,
  discovered_via TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(project_id, contact_id)
);
```

**New table: `contact_persona_scores`**
```sql
CREATE TABLE contact_persona_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,

  ai_role_aligned BOOLEAN,
  ai_is_decision_maker BOOLEAN,
  ai_project_relevant BOOLEAN,
  ai_persona_fit BOOLEAN,
  ai_reasoning JSONB,
  ai_classified_at TIMESTAMPTZ,

  user_role_aligned BOOLEAN,
  user_is_decision_maker BOOLEAN,
  user_project_relevant BOOLEAN,
  user_persona_fit BOOLEAN,
  user_override_at TIMESTAMPTZ,

  is_match BOOLEAN GENERATED ALWAYS AS (
    COALESCE(user_role_aligned, ai_role_aligned) IS TRUE AND
    COALESCE(user_is_decision_maker, ai_is_decision_maker) IS TRUE AND
    COALESCE(user_project_relevant, ai_project_relevant) IS TRUE AND
    COALESCE(user_persona_fit, ai_persona_fit) IS TRUE
  ) STORED,

  match_score NUMERIC GENERATED ALWAYS AS (
    (CASE WHEN COALESCE(user_role_aligned, ai_role_aligned) THEN 0.25 ELSE 0 END +
     CASE WHEN COALESCE(user_is_decision_maker, ai_is_decision_maker) THEN 0.25 ELSE 0 END +
     CASE WHEN COALESCE(user_project_relevant, ai_project_relevant) THEN 0.25 ELSE 0 END +
     CASE WHEN COALESCE(user_persona_fit, ai_persona_fit) THEN 0.25 ELSE 0 END)
  ) STORED,

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(contact_id)
);
```

### Relationships

```
projects ──1:N──▶ project_contacts ◀──N:1── contacts ──1:1──▶ contact_persona_scores
                                                │
                                            entity_id
                                                │
                                           entities (EPCs)
```

- Contacts are entity-scoped (existing pattern) — one record per person per EPC
- `project_contacts` links contacts to specific projects with discovery provenance
- Persona scores are per-contact (single persona for v1), not per-project-contact
- Human overrides stored in separate columns, `COALESCE` prefers human over AI

## Agent Configuration

### Contact Discovery Sub-Agent

```python
# agents/contact_discovery.py

CONTACT_DISCOVERY_TOOLS = [
    "lookup_hubspot_contacts",
    "query_knowledge_base",
    "search_linkedin",
    "search_exa_people",
    "scrape_epc_website",
    "search_osha",
    "web_search",
    "web_search_broad",
    "fetch_page",
    "save_contact",
    "classify_contact",
    "enrich_contact_email",
    "enrich_contact_phone",
]

def build_contact_discovery_runtime(entity, project, api_key) -> AgentRuntime:
    return AgentRuntime(
        system_prompt=build_contact_discovery_prompt(entity, project),
        tools=get_tools(CONTACT_DISCOVERY_TOOLS),
        hooks=[ContactSaveHook(), ToolHealthHook()],
        compactor=Compactor(max_tokens=60_000, preserve_recent=4),
        escalation=EscalationPolicy(max_iterations=30, escalation_mode="autonomous"),
        api_key=api_key,
    )
```

### Sub-Agent Launcher Tool

```python
# tools/run_contact_discovery.py

DEFINITION = {
    "name": "run_contact_discovery",
    "description": "Find and score contacts at an EPC company for a solar project.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "EPC entity UUID"},
            "project_id": {"type": "integer", "description": "Project ID"},
        },
        "required": ["entity_id", "project_id"]
    }
}

async def execute(tool_input: dict) -> dict:
    entity = await get_entity(tool_input["entity_id"])
    project = await get_project(tool_input["project_id"])
    runtime = build_contact_discovery_runtime(entity, project, api_key)
    result = await runtime.run_turn(
        messages=[user_message(
            f"Find contacts at {entity['name']} for project: {project['project_name']} "
            f"({project['state']}, {project['mw_capacity']}MW)"
        )],
        on_event=noop,
    )
    return extract_contacts(result)
```

## Contact Discovery Prompt

~40 lines. Domain knowledge + buyer persona + source guidance. No prescribed phases.

```
You are a contact discovery specialist for Civ Robotics, which sells
autonomous layout robots to solar farm EPC contractors.

Given an EPC company and a solar project, find the people at that company
who would be involved in purchasing or deploying construction technology
for this project.

## Who you're looking for

TARGET ROLES (high → low priority):
- VP/Director of Construction or Operations
- Senior Project Manager assigned to this project or region
- Director of Procurement / Equipment
- Innovation / Technology adoption leads
- Site Superintendent on this specific project

NOT TARGETS: HR, Finance, Legal, Marketing, IT, junior engineers

DECISION-MAKER SIGNALS: "VP", "Director", "Senior", "Head of",
manages budgets, approves equipment purchases, mentioned in press
releases about project milestones.

## What you know about the buyer

Civ Robotics sells to people who:
- Manage large utility-scale solar projects (50MW+)
- Are frustrated with manual layout staking (slow, error-prone)
- Have authority to approve equipment/service purchases
- Are in construction/operations, not development/finance

## Source reliability for contacts

1. HubSpot CRM (existing relationship — highest value)
2. EPC company website team/leadership pages
3. LinkedIn profiles with matching company + role
4. OSHA site inspection records (names site supervisors)
5. Press releases / conference speakers (names project leads)
6. Exa web search (broad fallback)

## After finding contacts

- Save each contact with save_contact
- Classify each with classify_contact
- Enrich top-scoring contacts (≥ 0.5) with email and phone
- Don't enrich contacts that score below 0.5 (waste of API credits)
```

## Hook: ContactSaveHook

```python
# hooks/contact_save.py

class ContactSaveHook:
    """Post-tool hook for save_contact — handles dedup logging and discovery status."""

    async def pre_tool(self, tool_name, tool_input, context) -> HookAction:
        return Continue(tool_input)

    async def post_tool(self, tool_name, tool_input, result, context) -> dict:
        if tool_name == "save_contact" and result.get("status") == "success":
            # Update entity discovery status
            await update_entity_discovery_status(
                entity_id=tool_input["entity_id"],
                status="in_progress"
            )
        return result
```

## New File Structure (on top of runtime revamp)

```
agent/src/
├── agents/
│   ├── chat.py                      # EXISTS (revamp)
│   ├── research.py                  # EXISTS (revamp)
│   └── contact_discovery.py         # NEW (~30 lines)
├── hooks/
│   └── contact_save.py              # NEW (~25 lines)
├── tools/
│   ├── run_contact_discovery.py     # NEW (~40 lines)
│   ├── search_linkedin.py           # NEW (~80 lines)
│   ├── search_exa_people.py         # NEW (~50 lines)
│   ├── scrape_epc_website.py        # NEW (~30 lines, thin wrapper)
│   ├── lookup_hubspot_contacts.py   # NEW (~60 lines)
│   ├── save_contact.py              # NEW (~50 lines)
│   ├── classify_contact.py          # NEW (~70 lines)
│   ├── enrich_contact_email.py      # NEW (~60 lines)
│   └── enrich_contact_phone.py      # NEW (~70 lines)
supabase/migrations/
│   └── 025_contact_discovery.sql    # NEW
```

**Estimated new code:** ~550 lines across 11 files + 1 migration
**Existing code modified:** `tools/__init__.py` (add Pydantic validation hook + register new tools)

## New Environment Variables

| Variable | Required | Provider |
|----------|----------|----------|
| `APIFY_API_TOKEN` | Yes (for LinkedIn scrape) | Apify |
| `EXA_API_KEY` | Yes (for people search) | Exa |
| `ENRICHMENT_API_KEY` | Optional (email waterfall) | EnrichmentAPI |
| `APOLLO_API_KEY` | Optional (email fallback) | Apollo |
| `LEADMAGIC_API_KEY` | Optional (phone waterfall) | LeadMagic |
| `PROSPEO_API_KEY` | Optional (phone waterfall) | Prospeo |
| `CONTACTOUT_API_KEY` | Optional (phone waterfall) | ContactOut |
| `PDL_API_KEY` | Optional (phone waterfall) | People Data Labs |

Email and phone enrichment tools gracefully degrade — if no API keys are set, they return `{"status": "error", "error": "No enrichment API keys configured"}` and the agent skips enrichment.

## Dependency

This spec depends on the Agent Runtime Revamp landing first. Specifically:
- `AgentRuntime` class with hook system
- Manager pattern (tools can spawn sub-agents)
- `run_research` tool as the pattern to follow

Contact discovery tools can be built in parallel with the revamp (they're standalone modules), but wiring them into the sub-agent requires the runtime.

## What This Doesn't Change

- **Frontend** — No changes in this spec. Contact results are presented by the chat agent as text. A future spec may add a contacts UI panel.
- **Existing `find_contacts` tool** — Deprecated but not deleted. It continues to work for users who call it directly. `run_contact_discovery` is the replacement.
- **Existing contacts table** — Extended, not replaced. Existing contact data preserved.
- **HubSpot push flow** — Unchanged. `push_to_hubspot` still works. Contacts discovered here can be pushed via the existing flow.

## What's NOT in v1

- **Multi-persona support** — Single hardcoded persona ("solar EPC robot buyer"). Configurable personas are a future enhancement.
- **Automatic triggering** — Contact discovery is always user-initiated or agent-suggested. No automatic "EPC discovered → find contacts" pipeline.
- **Background processing** — All discovery runs synchronously within the sub-agent. No BullMQ/async task queue.
- **Contact dedup across EPCs** — If Tom Rivera moves from Signal Energy to Blattner, he's two separate contacts. Cross-entity identity resolution is future work.
- **Frontend contacts panel** — Results shown in chat only. A dedicated contacts dashboard is a separate spec.
