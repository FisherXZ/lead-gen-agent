"""Reverse-lookup EPC sweep — search per-EPC across structured sources, match to projects.

Instead of "for each project, find the EPC" (forward lookup), this module does
"for each known EPC, find their projects" (reverse lookup) and matches results
against the project queue.

Architecture:
  ┌──────────────────────────────────────────────────────┐
  │  load_epcs() → entities WHERE 'epc' in entity_type  │
  │                                                       │
  │  For each EPC (sequential):                           │
  │    gather(                                            │
  │      edgar_source.search(epc),   ← concurrent        │
  │      osha_source.search(epc),    ← concurrent        │
  │      portfolio_source.search(epc) ← concurrent       │
  │    )                                                  │
  │    ↓                                                  │
  │    deduplicate candidates                             │
  │    ↓                                                  │
  │    match_candidates_to_projects()                     │
  │    ├── strong match → create discovery (pending)      │
  │    ├── ambiguous → Haiku disambiguation               │
  │    └── no match → skip                                │
  └──────────────────────────────────────────────────────┘

Discoveries created by the sweep land as:
  review_status = "pending", confidence = "possible"
  source = structured source reference
  reasoning = "Reverse-lookup match: [details]"
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import anthropic

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SweepCandidate:
    """A potential project-EPC match found by a sweep source."""

    project_name_hint: str
    state: str = ""
    mw_hint: float = 0
    source_type: str = ""
    source_url: str = ""
    excerpt: str = ""
    epc_name: str = ""


@dataclass
class SweepMatch:
    """A confirmed match between a candidate and a project."""

    project_id: str
    project_name: str
    epc_name: str
    confidence: str  # "possible" for all sweep matches
    source_type: str
    source_url: str
    excerpt: str
    match_method: str  # "name", "geocode", "haiku_disambiguation"
    match_score: float = 0.0


@dataclass
class SweepProgress:
    """Progress update for SSE streaming."""

    epc_name: str
    status: str  # "searching", "matching", "completed", "error"
    candidates_found: int = 0
    matches_found: int = 0
    message: str = ""


@dataclass
class SweepResult:
    """Final result of the entire reverse sweep."""

    epcs_processed: int = 0
    total_candidates: int = 0
    total_matches: int = 0
    discoveries_created: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SweepSource Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SweepSource(Protocol):
    """Interface for reverse-sweep data sources.

    Each source searches for an EPC's projects and returns candidates.
    """

    name: str

    async def search(self, epc_name: str, **kwargs: Any) -> list[SweepCandidate]:
        """Search for projects associated with this EPC. Returns candidates."""
        ...


# ---------------------------------------------------------------------------
# Source adapters (wrap existing tools)
# ---------------------------------------------------------------------------


class EdgarSweepSource:
    """Search SEC EDGAR for an EPC's contract disclosures."""

    name = "sec_edgar"

    async def search(self, epc_name: str, **kwargs: Any) -> list[SweepCandidate]:
        from .tools.search_sec_edgar import execute

        candidates = []
        for query in [
            f'"{epc_name}" "EPC contractor" solar',
            f'"{epc_name}" "EPC agreement" solar',
        ]:
            result = await execute({"query": query, "max_results": 5})
            if "error" in result:
                logger.info("EDGAR search failed for %s: %s", epc_name, result["error"])
                continue

            for hit in result.get("results", []):
                candidates.append(
                    SweepCandidate(
                        project_name_hint=hit.get("snippet", "")[:200],
                        source_type="sec_edgar",
                        source_url=hit.get("url", ""),
                        excerpt=hit.get("snippet", ""),
                        epc_name=epc_name,
                    )
                )

        return candidates


class OshaSweepSource:
    """Search OSHA inspection records for an EPC's construction sites."""

    name = "osha"

    async def search(self, epc_name: str, **kwargs: Any) -> list[SweepCandidate]:
        from .tools.search_osha import execute

        result = await execute({"employer_name": epc_name, "max_results": 20})
        if "error" in result:
            logger.info("OSHA search failed for %s: %s", epc_name, result["error"])
            return []

        candidates = []
        for record in result.get("results", []):
            address = record.get("address", "")
            state = record.get("state", "")
            candidates.append(
                SweepCandidate(
                    project_name_hint=f"Construction site: {address}",
                    state=state,
                    source_type="osha_inspection",
                    source_url=record.get("detail_url", ""),
                    excerpt=(
                        f"{record.get('employer_name', '')} inspected at "
                        f"{address} on {record.get('inspection_date', '')}"
                    ),
                    epc_name=epc_name,
                )
            )

        return candidates


class PortfolioSweepSource:
    """Fetch an EPC's portfolio page and extract project mentions."""

    name = "portfolio"

    async def search(self, epc_name: str, **kwargs: Any) -> list[SweepCandidate]:
        from .tools.fetch_page import execute

        entity = kwargs.get("entity")
        if not entity:
            return []

        metadata = entity.get("metadata") or {}
        portfolio_url = metadata.get("portfolio_url")
        if not portfolio_url:
            return []

        result = await execute({"url": portfolio_url})
        if "error" in result:
            logger.info("Portfolio fetch failed for %s: %s", epc_name, result["error"])
            return []

        # Parse project mentions from the portfolio text
        text = result.get("text", "")
        candidates = []
        # Simple heuristic: look for MW mentions near project names
        import re

        for match in re.finditer(r"(\d{2,4})\s*MW", text):
            # Grab surrounding context
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()
            mw = float(match.group(1))
            candidates.append(
                SweepCandidate(
                    project_name_hint=context[:200],
                    mw_hint=mw,
                    source_type="epc_portfolio",
                    source_url=portfolio_url,
                    excerpt=context[:300],
                    epc_name=epc_name,
                )
            )

        return candidates


# ---------------------------------------------------------------------------
# Project matching
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """Normalize a string for fuzzy comparison."""
    import re

    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def match_candidates_to_projects(
    candidates: list[SweepCandidate],
    projects: list[dict],
) -> tuple[list[SweepMatch], list[tuple[SweepCandidate, dict]]]:
    """Match candidates against the project table.

    Returns:
        (strong_matches, ambiguous_pairs)
        - strong_matches: high-confidence matches ready to create discoveries
        - ambiguous_pairs: (candidate, project) pairs needing Haiku disambiguation
    """
    strong: list[SweepMatch] = []
    ambiguous: list[tuple[SweepCandidate, dict]] = []

    for candidate in candidates:
        best_project = None
        best_score = 0.0
        best_method = ""

        for project in projects:
            score, method = _score_match(candidate, project)
            if score > best_score:
                best_score = score
                best_project = project
                best_method = method

        if best_project is None:
            continue

        if best_score >= 0.7:
            strong.append(
                SweepMatch(
                    project_id=best_project["id"],
                    project_name=best_project.get("project_name", ""),
                    epc_name=candidate.epc_name,
                    confidence="possible",
                    source_type=candidate.source_type,
                    source_url=candidate.source_url,
                    excerpt=candidate.excerpt,
                    match_method=best_method,
                    match_score=best_score,
                )
            )
        elif best_score >= 0.4:
            ambiguous.append((candidate, best_project))

    return strong, ambiguous


def _score_match(candidate: SweepCandidate, project: dict) -> tuple[float, str]:
    """Score how well a candidate matches a project. Returns (score, method)."""
    score = 0.0
    method = "none"

    project_name = project.get("project_name", "")
    project_state = project.get("state", "")
    project_mw = project.get("mw_capacity", 0) or 0
    project_developer = project.get("developer", "")

    hint = candidate.project_name_hint
    hint_norm = _normalize(hint)

    # Name match: project name appears in the candidate hint
    if project_name:
        pname_norm = _normalize(project_name)
        if pname_norm and pname_norm in hint_norm:
            score += 0.5
            method = "name"
        elif len(pname_norm) > 5:
            # Partial match — check if major words overlap
            pname_words = set(pname_norm.split()) - {
                "solar",
                "project",
                "energy",
                "power",
                "llc",
                "inc",
            }
            hint_words = set(hint_norm.split())
            if pname_words and pname_words.issubset(hint_words):
                score += 0.3
                method = "partial_name"

    # Developer match
    if project_developer:
        dev_norm = _normalize(project_developer)
        if dev_norm and dev_norm in hint_norm:
            score += 0.2
            method = method or "developer"

    # State match
    if candidate.state and project_state:
        if candidate.state.upper() == project_state.upper():
            score += 0.15
        else:
            score -= 0.2  # State mismatch is a strong negative signal

    # MW match (within ±30%)
    if candidate.mw_hint > 0 and project_mw > 0:
        ratio = min(candidate.mw_hint, project_mw) / max(candidate.mw_hint, project_mw)
        if ratio >= 0.7:
            score += 0.1
        elif ratio < 0.5:
            score -= 0.1

    # OSHA geocode match (if candidate has lat/lon from geocoding)
    # This is handled by the caller pre-geocoding OSHA addresses

    return min(score, 1.0), method


# ---------------------------------------------------------------------------
# Haiku disambiguation
# ---------------------------------------------------------------------------


async def disambiguate_with_haiku(
    candidate: SweepCandidate,
    project: dict,
    api_key: str | None = None,
) -> str:
    """Ask Haiku whether a candidate matches a project.

    Returns: "yes", "no", or "unsure"
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "unsure"

    prompt = f"""You are matching solar project data. Does this SEC/OSHA \
record refer to the same project in our database?

**Record found:**
{candidate.excerpt[:500]}
Source: {candidate.source_type}
EPC: {candidate.epc_name}

**Project in database:**
Name: {project.get("project_name", "Unknown")}
Developer: {project.get("developer", "Unknown")}
State: {project.get("state", "Unknown")}
Capacity: {project.get("mw_capacity", "Unknown")} MW

Answer ONLY "yes", "no", or "unsure". Consider: name similarity, state \
match, MW capacity match (DC vs AC can differ by 20-30%), and developer match."""

    try:
        client = anthropic.AsyncAnthropic(api_key=key)
        response = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip().lower()
        if "yes" in answer:
            return "yes"
        elif "no" in answer:
            return "no"
        return "unsure"
    except Exception as exc:
        logger.warning("Haiku disambiguation failed: %s", exc)
        return "unsure"


# ---------------------------------------------------------------------------
# Discovery creation
# ---------------------------------------------------------------------------


def _create_sweep_discovery(match: SweepMatch) -> dict | None:
    """Create an epc_discovery record from a sweep match.

    Returns the created discovery dict, or None if creation fails.
    """
    from .db import get_active_discovery, get_client

    # Skip if project already has a non-rejected discovery
    existing = get_active_discovery(match.project_id)
    if existing:
        logger.info(
            "Skipping %s — already has discovery (status: %s)",
            match.project_name,
            existing.get("review_status"),
        )
        return None

    client = get_client()
    discovery_data = {
        "project_id": match.project_id,
        "epc_contractor": match.epc_name,
        "confidence": match.confidence,
        "sources": [
            {
                "channel": match.source_type,
                "url": match.source_url,
                "excerpt": match.excerpt[:500],
                "reliability": "medium",
                "source_method": match.source_type,
            }
        ],
        "reasoning": json.dumps(
            {
                "summary": f"Reverse-lookup match: {match.epc_name} found via {match.source_type} "
                f"(match method: {match.match_method}, score: {match.match_score:.2f})",
                "supporting_evidence": [
                    f"Source: {match.source_type} — {match.excerpt[:200]}",
                    f"Match method: {match.match_method} with score {match.match_score:.2f}",
                ],
                "gaps": [
                    "This is an automated reverse-lookup match — human review required",
                    "Confidence is 'possible' — additional forward-lookup research recommended",
                ],
            }
        ),
        "review_status": "pending",
        "searches_performed": [f"reverse_sweep:{match.source_type}:{match.epc_name}"],
        "tokens_used": 0,
    }

    try:
        resp = client.table("epc_discoveries").insert(discovery_data).execute()
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.error("Failed to create sweep discovery for %s: %s", match.project_name, exc)
        return None


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

# Active sweep tracking (prevent duplicates)
_active_sweep_id: str | None = None


async def run_reverse_sweep(
    on_progress: Callable[[SweepProgress], Any] | None = None,
    api_key: str | None = None,
    sources: list[SweepSource] | None = None,
) -> SweepResult:
    """Run the full reverse-lookup sweep.

    For each seeded EPC entity:
    1. Query all sources concurrently
    2. Match candidates to projects
    3. Disambiguate ambiguous matches with Haiku
    4. Create pending discoveries for matches

    Args:
        on_progress: Optional async callback for SSE progress streaming.
        api_key: Optional Anthropic API key for Haiku disambiguation.
        sources: Optional list of SweepSource instances (defaults to all 3).

    Returns:
        SweepResult with counts and any errors.
    """
    global _active_sweep_id
    from .db import get_client

    result = SweepResult()

    if sources is None:
        sources = [EdgarSweepSource(), OshaSweepSource(), PortfolioSweepSource()]

    # Load seeded EPCs
    client = get_client()
    resp = (
        client.table("entities")
        .select("id, name, entity_type, metadata, aliases")
        .contains("entity_type", ["epc"])
        .order("name")
        .execute()
    )
    epcs = resp.data or []

    if not epcs:
        logger.info("No EPC entities found — run seed_epc_entities first")
        if on_progress:
            await on_progress(
                SweepProgress(
                    epc_name="",
                    status="completed",
                    message="No EPC entities found",
                )
            )
        return result

    # Load all projects for matching (projects without accepted EPC)
    projects_resp = (
        client.table("projects")
        .select("id, project_name, developer, state, county, mw_capacity, latitude, longitude")
        .is_("epc_company", "null")
        .order("mw_capacity", desc=True)
        .limit(2000)
        .execute()
    )
    projects = projects_resp.data or []
    logger.info("Loaded %d EPCs and %d unresearched projects", len(epcs), len(projects))

    # Process each EPC
    for epc in epcs:
        epc_name = epc["name"]
        result.epcs_processed += 1

        if on_progress:
            await on_progress(
                SweepProgress(
                    epc_name=epc_name,
                    status="searching",
                    message=f"Searching {len(sources)} sources for {epc_name}",
                )
            )

        # Search all sources concurrently for this EPC
        all_candidates: list[SweepCandidate] = []
        search_tasks = [source.search(epc_name, entity=epc) for source in sources]

        try:
            source_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        except Exception as exc:
            logger.error("Gather failed for %s: %s", epc_name, exc)
            result.errors.append(f"{epc_name}: gather failed — {exc}")
            continue

        for i, sr in enumerate(source_results):
            if isinstance(sr, Exception):
                logger.warning("Source %s failed for %s: %s", sources[i].name, epc_name, sr)
                result.errors.append(f"{epc_name}/{sources[i].name}: {sr}")
            elif isinstance(sr, list):
                all_candidates.extend(sr)

        result.total_candidates += len(all_candidates)

        if not all_candidates:
            if on_progress:
                await on_progress(
                    SweepProgress(
                        epc_name=epc_name,
                        status="completed",
                        candidates_found=0,
                        matches_found=0,
                        message=f"No candidates found for {epc_name}",
                    )
                )
            continue

        # Match candidates to projects
        if on_progress:
            await on_progress(
                SweepProgress(
                    epc_name=epc_name,
                    status="matching",
                    candidates_found=len(all_candidates),
                    message=(
                        f"Matching {len(all_candidates)} candidates "
                        f"against {len(projects)} projects"
                    ),
                )
            )

        strong_matches, ambiguous_pairs = match_candidates_to_projects(all_candidates, projects)

        # Disambiguate ambiguous matches with Haiku
        for candidate, project in ambiguous_pairs:
            answer = await disambiguate_with_haiku(candidate, project, api_key=api_key)
            if answer == "yes":
                strong_matches.append(
                    SweepMatch(
                        project_id=project["id"],
                        project_name=project.get("project_name", ""),
                        epc_name=candidate.epc_name,
                        confidence="possible",
                        source_type=candidate.source_type,
                        source_url=candidate.source_url,
                        excerpt=candidate.excerpt,
                        match_method="haiku_disambiguation",
                        match_score=0.5,
                    )
                )

        # Deduplicate matches by project_id
        seen_projects: set[str] = set()
        unique_matches: list[SweepMatch] = []
        for m in strong_matches:
            if m.project_id not in seen_projects:
                seen_projects.add(m.project_id)
                unique_matches.append(m)

        # Create discoveries
        for match in unique_matches:
            discovery = _create_sweep_discovery(match)
            if discovery:
                result.discoveries_created += 1
                result.total_matches += 1

        if on_progress:
            await on_progress(
                SweepProgress(
                    epc_name=epc_name,
                    status="completed",
                    candidates_found=len(all_candidates),
                    matches_found=len(unique_matches),
                    message=(
                        f"{epc_name}: {len(all_candidates)} candidates, "
                        f"{len(unique_matches)} matches"
                    ),
                )
            )

    return result
