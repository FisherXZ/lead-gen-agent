"""LinkedIn people search tool.

Searches LinkedIn for people at a company using Tavily site-scoped queries,
then optionally enriches top candidates via the Apify LinkedIn Profile Scraper.

Graceful degradation: if APIFY_API_TOKEN is not set, returns search-only
results (LinkedIn URLs + name/title snippets) without profile enrichment.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ._base import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 4
_APIFY_BASE = "https://api.apify.com/v2"
_APIFY_ACTOR = "apify~linkedin-profile-scraper"
_APIFY_TIMEOUT = 120  # seconds to wait for Apify run to finish

DEFINITION = {
    "name": "search_linkedin",
    "description": (
        "Search LinkedIn for people at an EPC company and enrich their profiles. "
        "Constructs role-specific LinkedIn searches (e.g. site:linkedin.com/in), "
        "extracts candidate profile URLs from results, and optionally fetches full "
        "profiles via Apify. Returns names, titles, LinkedIn URLs, and experience "
        "history for contacts matching VP/Director/PM-level roles. Use this after "
        "identifying a target EPC company to find the right people to contact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "EPC company to search (e.g. 'Signal Energy', 'Blattner Energy').",
            },
            "role_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Job titles/roles to search for.",
                "default": ["project manager", "VP construction", "director operations"],
            },
            "location": {
                "type": "string",
                "description": "State or region filter (e.g. 'Texas', 'California'). Optional.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum candidates to return (1–20, default 5).",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["company_name"],
    },
}


class Input(BaseModel):
    company_name: str = Field(..., description="EPC company to search")
    role_keywords: list[str] = Field(
        default=["project manager", "VP construction", "director operations"],
        description="Job titles/roles to search for",
    )
    location: str | None = Field(None, description="State or region filter")
    max_results: int = Field(5, ge=1, le=20)


# ---------------------------------------------------------------------------
# Public execute
# ---------------------------------------------------------------------------


async def execute(tool_input: dict) -> dict:
    """Run LinkedIn people search, optionally enriching via Apify."""
    inp = Input(**tool_input)

    cache_params = {
        "company_name": inp.company_name,
        "role_keywords": sorted(inp.role_keywords),
        "location": inp.location,
        "max_results": inp.max_results,
    }
    cached = cache_get("search_linkedin", cache_params)
    if cached is not None:
        return {"status": "success", "data": cached, "source": "linkedin", "cached": True}

    # Build queries and search
    queries = _build_search_queries(inp.company_name, inp.role_keywords, inp.location)

    import asyncio
    search_tasks = [_run_web_search(q, max_results=inp.max_results) for q in queries]
    search_results = await asyncio.gather(*search_tasks)
    all_search_results: list[dict] = []
    for result in search_results:
        all_search_results.extend(result.get("results", []))

    # Extract LinkedIn URLs from search hits
    candidates = _extract_candidates(all_search_results)
    # Limit to max_results unique candidates
    candidates = candidates[: inp.max_results]

    # Enrich via Apify if token is available
    apify_token = os.environ.get("APIFY_API_TOKEN")
    enriched = False

    if apify_token and candidates:
        urls = [c["linkedin_url"] for c in candidates]
        try:
            profiles = await _enrich_with_apify(urls, apify_token)
            if profiles:
                candidates = _merge_apify_profiles(candidates, profiles)
                enriched = True
        except Exception as exc:
            logger.warning("Apify enrichment failed, falling back to search-only: %s", exc)

    data = {"candidates": candidates, "enriched": enriched}
    cache_set("search_linkedin", cache_params, data, ttl_hours=_CACHE_TTL_HOURS)

    return {"status": "success", "data": data, "source": "linkedin"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_search_queries(
    company_name: str,
    role_keywords: list[str],
    location: str | None,
) -> list[str]:
    """Build one Tavily query per role keyword."""
    queries = []
    for role in role_keywords:
        q = f'site:linkedin.com/in "{company_name}" "{role}"'
        if location:
            q += f" {location}"
        queries.append(q)
    return queries


def _extract_candidates(search_results: list[dict]) -> list[dict]:
    """Parse LinkedIn profile URLs and name/title from Tavily results."""
    seen_urls: set[str] = set()
    candidates: list[dict] = []

    for result in search_results:
        url = result.get("url", "")
        if not _is_linkedin_profile_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title_text = result.get("title", "")
        content_text = result.get("content", "")

        name, job_title = _parse_name_title(title_text, content_text)

        candidates.append(
            {
                "full_name": name,
                "title": job_title,
                "linkedin_url": url,
                "headline": title_text,
                "location": None,
                "experience": [],
                "source": "linkedin",
            }
        )

    return candidates


def _is_linkedin_profile_url(url: str) -> bool:
    """Return True if the URL is a LinkedIn person profile (/in/ path)."""
    return "linkedin.com/in/" in url


def _parse_name_title(title_text: str, content_text: str) -> tuple[str, str]:
    """Best-effort extraction of name and job title from LinkedIn search snippets.

    LinkedIn search result titles typically look like:
      "Tom Rivera - Senior Project Manager at Signal Energy | LinkedIn"
      "Jane Doe – VP Construction | LinkedIn"
    """
    name = ""
    job_title = ""

    # Strip " | LinkedIn" suffix
    clean = title_text.replace("| LinkedIn", "").replace("- LinkedIn", "").strip()

    # Split on first " - " or " – "
    for sep in (" - ", " – ", " | "):
        if sep in clean:
            parts = clean.split(sep, 1)
            name = parts[0].strip()
            rest = parts[1].strip()
            # Rest may be "VP Construction at Signal Energy" — take up to " at "
            if " at " in rest:
                job_title = rest.split(" at ")[0].strip()
            else:
                job_title = rest.strip()
            break

    if not name:
        name = clean

    return name, job_title


async def _run_web_search(query: str, max_results: int = 5) -> dict:
    """Delegate to the web_search tool's execute function."""
    from . import web_search

    return await web_search.execute({"query": query, "max_results": max_results})


async def _enrich_with_apify(urls: list[str], token: str) -> list[dict]:
    """Call Apify LinkedIn Profile Scraper and wait for results.

    Returns a list of raw Apify profile dicts.
    """
    actor_url = f"{_APIFY_BASE}/acts/{_APIFY_ACTOR}/runs"
    run_input = {
        "startUrls": [{"url": u} for u in urls],
        "proxy": {"useApifyProxy": True},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            actor_url,
            json=run_input,
            params={"token": token},
        )
        resp.raise_for_status()
        run_data = resp.json()

    run_id = run_data["data"]["id"]
    dataset_id = run_data["data"]["defaultDatasetId"]

    # Poll until run finishes (or timeout)
    deadline = time.time() + _APIFY_TIMEOUT
    async with httpx.AsyncClient(timeout=30) as client:
        while time.time() < deadline:
            status_resp = await client.get(
                f"{_APIFY_BASE}/acts/{_APIFY_ACTOR}/runs/{run_id}",
                params={"token": token},
            )
            status_resp.raise_for_status()
            status = status_resp.json()["data"]["status"]
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break
            await _async_sleep(3)

        if status != "SUCCEEDED":
            raise RuntimeError(f"Apify run {run_id} ended with status: {status}")

        # Fetch dataset items
        items_resp = await client.get(
            f"{_APIFY_BASE}/datasets/{dataset_id}/items",
            params={"token": token, "format": "json"},
        )
        items_resp.raise_for_status()
        return items_resp.json()


async def _async_sleep(seconds: float) -> None:
    """Async sleep wrapper (allows mocking in tests)."""
    import asyncio

    await asyncio.sleep(seconds)


def _merge_apify_profiles(candidates: list[dict], profiles: list[dict]) -> list[dict]:
    """Merge Apify enrichment data into the candidate list.

    Matches by LinkedIn URL. Apify profiles may use slightly different URL
    formats so we normalise by stripping trailing slashes.
    """
    profile_by_url: dict[str, dict] = {}
    for p in profiles:
        raw_url = p.get("url") or p.get("linkedInUrl") or p.get("profileUrl") or ""
        normalised = raw_url.rstrip("/")
        if normalised:
            profile_by_url[normalised] = p

    enriched_candidates: list[dict] = []
    for candidate in candidates:
        normalised_url = candidate["linkedin_url"].rstrip("/")
        profile = profile_by_url.get(normalised_url)

        if not profile:
            enriched_candidates.append(candidate)
            continue

        # Extract experience list
        experience: list[dict] = []
        positions = profile.get("positions") or {}
        for pos in (positions.get("positionHistory") or []):
            exp_entry: dict[str, Any] = {
                "company": pos.get("companyName", ""),
                "title": pos.get("title", ""),
                "duration": _format_apify_duration(pos.get("startEndDate", {})),
            }
            experience.append(exp_entry)

        enriched_candidates.append(
            {
                "full_name": profile.get("fullName") or candidate["full_name"],
                "title": profile.get("jobTitle") or candidate["title"],
                "linkedin_url": candidate["linkedin_url"],
                "headline": profile.get("headline") or candidate["headline"],
                "location": profile.get("addressWithCountry") or candidate["location"],
                "experience": experience,
                "source": "linkedin",
            }
        )

    return enriched_candidates


def _format_apify_duration(start_end: dict) -> str:
    """Format Apify startEndDate dict into a readable string."""
    start = start_end.get("start") or {}
    end = start_end.get("end") or {}
    start_year = start.get("year")
    end_year = end.get("year")

    if start_year and end_year:
        return f"{start_year}-{end_year}"
    if start_year:
        return f"{start_year}-present"
    return ""
