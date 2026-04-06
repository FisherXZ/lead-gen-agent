"""Contact discovery mini-agent.

Finds leadership contacts at EPC companies using existing search tools.
This is a focused agent task (like run_research but simpler):
  - 8 iteration max (vs 25 for EPC research)
  - Uses web_search, brave_search, fetch_page, search_sec_edgar
  - Returns structured contacts: name, title, LinkedIn URL, source

Concurrency: Module-level semaphore limits concurrent discoveries to 2
to prevent API rate limit bursts during batch acceptances.

Status tracking: Updates entities.contact_discovery_status so the
Actions dashboard can show progress/failure states.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .db import get_anthropic_client, get_client
from .tools import execute_tool, get_tools

logger = logging.getLogger(__name__)

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-4-6")
MAX_ITERATIONS = 8

# Limit concurrent contact discoveries to prevent API burst
_discovery_semaphore = asyncio.Semaphore(2)

# Tools available during contact discovery
CONTACT_TOOLS = [
    "web_search", "web_search_broad", "fetch_page",
    "search_sec_edgar", "fetch_sec_filing",
]

CONTACT_DISCOVERY_PROMPT = """\
You are a contact discovery agent for Civ Robotics. Your job is to find \
3-5 leadership contacts at the given EPC (Engineering, Procurement & \
Construction) company who would be relevant for selling autonomous solar \
layout robots.

## Target Roles (in priority order)
1. VP/Director of Procurement or Supply Chain
2. VP/Director of Solar or Renewables Division
3. VP/Director of Construction or Project Management
4. VP/Director of Innovation or Technology
5. Regional VP overseeing solar projects
6. C-suite (CEO, COO, CTO) — for smaller EPCs only

## Search Strategy
1. Search "[company] leadership team" or "[company] about us"
2. Fetch the company's /about, /team, or /leadership page
3. Search "[company] VP procurement solar" or "[company] director construction"
4. For publicly traded companies: search SEC proxy filings (DEF 14A) \
which list officers and directors
5. Search LinkedIn profiles: site:linkedin.com/in "[company]" VP solar

## Output Format
When you have found contacts, respond with a JSON array:
```json
[
  {
    "full_name": "John Smith",
    "title": "VP of Procurement",
    "linkedin_url": "https://www.linkedin.com/in/johnsmith",
    "source_url": "https://company.com/about/leadership",
    "source_method": "epc_website"
  }
]
```

Rules:
- Return ONLY the JSON array, no other text
- Include 1-5 contacts (quality over quantity)
- linkedin_url can be null if not found
- source_method must be one of: web_search, sec_filing, epc_website, page_fetch
- If you cannot find any contacts, return an empty array: []
- Do NOT make up contacts — only report people you actually found in sources
- Focus on people who make purchasing or technology adoption decisions
"""


@retry(
    retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=15),
    reraise=True,
    before_sleep=lambda rs: logging.getLogger(__name__).warning(
        "Contact discovery API retry #%d: %s", rs.attempt_number, rs.outcome.exception()
    ),
)
async def _call_api(client, **kwargs):
    return await client.messages.create(**kwargs)


async def discover_contacts(
    entity_id: str,
    entity_name: str,
    api_key: str | None = None,
    project: dict | None = None,
) -> list[dict]:
    """Find leadership contacts at an EPC company.

    Updates entity.contact_discovery_status throughout.
    If project is provided, generates outreach context for each contact.
    Returns list of contact dicts (may be empty).
    """
    client_db = get_client()

    # Set status to pending
    try:
        client_db.table("entities").update({
            "contact_discovery_status": "pending",
            "contact_discovery_error": None,
        }).eq("id", entity_id).execute()
    except Exception:
        logger.warning("Failed to set contact_discovery_status=pending for %s", entity_id)

    try:
        async with _discovery_semaphore:
            contacts = await _run_contact_agent(entity_name, api_key)
    except Exception as exc:
        logger.error("Contact discovery failed for %s: %s", entity_name, exc, exc_info=True)
        # Mark failed
        try:
            client_db.table("entities").update({
                "contact_discovery_status": "failed",
                "contact_discovery_error": str(exc)[:500],
            }).eq("id", entity_id).execute()
        except Exception:
            pass
        return []

    # Store contacts in DB
    from .db import store_contacts
    stored = store_contacts(entity_id, contacts)

    # Generate outreach context for each contact (if project provided)
    if stored and project:
        entity = {"name": entity_name, "id": entity_id}
        # Fetch entity profile for richer context
        try:
            from .knowledge_base import get_entity_with_profile
            full_entity = get_entity_with_profile(entity_id)
            if full_entity:
                entity = full_entity
        except Exception:
            pass

        for contact in stored:
            try:
                context = await generate_outreach_context(
                    project=project, entity=entity, contact=contact, api_key=api_key
                )
                if context:
                    client_db.table("contacts").update({
                        "outreach_context": context,
                    }).eq("id", contact["id"]).execute()
                    contact["outreach_context"] = context
            except Exception as exc:
                logger.warning(
                    "Outreach context failed for %s: %s", contact.get("full_name"), exc
                )

    # Mark completed
    try:
        from datetime import datetime, timezone
        client_db.table("entities").update({
            "contact_discovery_status": "completed",
            "contact_discovery_error": None,
            "contacts_discovered_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", entity_id).execute()
    except Exception:
        logger.warning("Failed to set contact_discovery_status=completed for %s", entity_id)

    return stored


async def _run_contact_agent(
    entity_name: str,
    api_key: str | None = None,
) -> list[dict]:
    """Run the agentic loop to find contacts."""
    client = get_anthropic_client(api_key)

    system_prompt = CONTACT_DISCOVERY_PROMPT
    user_msg = f"Find leadership contacts at: {entity_name}"
    messages = [{"role": "user", "content": user_msg}]

    tools = get_tools(CONTACT_TOOLS)

    for iteration in range(MAX_ITERATIONS):
        try:
            response = await _call_api(
                client,
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": system_prompt}],
                tools=tools,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            logger.error("Contact discovery auth error — invalid API key")
            return []
        except anthropic.APIError as exc:
            logger.error("Contact discovery API error: %s", exc)
            return []

        # Agent finished without tool use — parse the response
        if response.stop_reason == "end_turn":
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return _parse_contacts(text)

        # Process tool use blocks
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = await execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            except Exception as e:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"error": str(e)}),
                    "is_error": True,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # Max iterations — try to parse whatever we have
    logger.warning("Contact discovery for %s hit max iterations", entity_name)
    return []


def _parse_contacts(text: str) -> list[dict]:
    """Parse the agent's response into structured contacts.

    Expects a JSON array. Handles markdown code fences.
    """
    if not text:
        return []

    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    # Try to find JSON array in the text
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return _validate_contacts(data)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from within text
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return _validate_contacts(data)
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse contacts from agent response: %s", text[:200])
    return []


def _validate_contacts(contacts: list) -> list[dict]:
    """Validate and normalize contact dicts."""
    valid = []
    for c in contacts:
        if not isinstance(c, dict):
            continue
        name = (c.get("full_name") or "").strip()
        if not name:
            continue
        valid.append({
            "full_name": name,
            "title": (c.get("title") or "").strip() or None,
            "linkedin_url": (c.get("linkedin_url") or "").strip() or None,
            "source_url": (c.get("source_url") or "").strip() or None,
            "source_method": c.get("source_method", "web_search"),
        })
    return valid


async def generate_outreach_context(
    project: dict,
    entity: dict,
    contact: dict,
    api_key: str | None = None,
) -> str | None:
    """Generate a 'why to call' paragraph for a contact.

    Returns the context string, or None if generation fails.
    """
    client = get_anthropic_client(api_key)

    project_name = project.get("project_name", "Unknown")
    mw = project.get("mw_capacity", "?")
    state = project.get("state", "?")
    cod = project.get("expected_cod", "?")
    epc_name = entity.get("name", "Unknown")
    contact_name = contact.get("full_name", "Unknown")
    contact_title = contact.get("title", "Unknown")
    entity_profile = entity.get("profile", "")

    prompt = f"""Generate a 2-3 sentence "why to call" paragraph for a Civ Robotics sales rep.
Civ Robotics sells autonomous layout robots for solar farm construction.

Project: {project_name}, {mw}MW, {state}, expected COD {cod}
EPC contractor: {epc_name} (won this project)
Contact: {contact_name}, {contact_title}

Company context:
{entity_profile[:1000] if entity_profile else 'No prior history in our system.'}

Write a concise, professional paragraph explaining:
1. Why this lead is relevant (project specifics)
2. Why now (timing relative to construction start)
3. What Civ Robotics can offer (autonomous staking/layout for solar farms)

Be specific and actionable. No fluff."""

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text
        return text.strip() if text.strip() else None
    except Exception as exc:
        logger.warning("Outreach context generation failed: %s", exc)
        return None
