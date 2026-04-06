"""Knowledge base: entity resolution, context building, and write-back.

Read path (before research):
  build_knowledge_context(project) -> str

Write path (after research):
  process_discovery_into_kb(project_id, result, project) -> None

Profile management:
  rebuild_profile_if_stale(entity_id) -> str
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .db import get_client
from .models import AgentResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entity Resolution
# ---------------------------------------------------------------------------


def resolve_entity(name: str) -> dict | None:
    """Look up an entity by name (case-insensitive). Returns dict or None."""
    if not name:
        return None
    client = get_client()
    resp = client.table("entities").select("*").ilike("name", name).limit(1).execute()
    if resp.data:
        return resp.data[0]
    return None


def resolve_or_create_entity(name: str, entity_type: str) -> dict:
    """Find an entity by name, or create it. Merges entity_type if needed.

    entity_type should be 'developer' or 'epc'.
    """
    if not name:
        raise ValueError("Entity name is required")

    existing = resolve_entity(name)
    if existing:
        # Merge entity_type if not already present
        types = existing.get("entity_type", [])
        if entity_type not in types:
            client = get_client()
            client.table("entities").update({"entity_type": types + [entity_type]}).eq(
                "id", existing["id"]
            ).execute()
            existing["entity_type"] = types + [entity_type]
        return existing

    # Create new entity
    client = get_client()
    resp = (
        client.table("entities")
        .insert(
            {
                "name": name,
                "entity_type": [entity_type],
            }
        )
        .execute()
    )
    return resp.data[0]


# ---------------------------------------------------------------------------
# Read Path — called BEFORE agent research
# ---------------------------------------------------------------------------


def get_developer_engagements(entity_id: str) -> list[dict]:
    """Get all known EPC engagements for a developer entity."""
    client = get_client()
    resp = (
        client.table("epc_engagements")
        .select(
            "*, epc:epc_entity_id(id, name), project:project_id(project_name, mw_capacity, state)"
        )
        .eq("developer_entity_id", entity_id)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data


def get_project_research_attempts(project_id: str) -> list[dict]:
    """Get prior research attempts for a specific project."""
    client = get_client()
    resp = (
        client.table("research_attempts")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    return resp.data


def get_epcs_in_state(state: str) -> list[dict]:
    """Get EPC entities with confirmed/likely engagements in a given state."""
    if not state:
        return []
    client = get_client()
    resp = (
        client.table("epc_engagements")
        .select("*, epc:epc_entity_id(id, name), project:project_id(project_name, mw_capacity)")
        .ilike("state", f"%{state}%")
        .in_("confidence", ["confirmed", "likely"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return resp.data


def build_knowledge_context(project: dict) -> str | None:
    """Build knowledge context string for the agent before research.

    Returns a markdown string with what we already know, or None if nothing.
    Includes developer loyalty stats, negative knowledge from failed searches,
    and enriched state EPC stats with project counts and MW totals.
    """
    developer_name = project.get("developer")
    project_id = project.get("id")
    state = project.get("state")

    sections: list[str] = []

    # 1. Developer profile and engagements with loyalty stats
    if developer_name:
        dev_entity = resolve_entity(developer_name)
        if dev_entity:
            # Rebuild profile if stale
            if dev_entity.get("profile") is None or dev_entity.get("profile_rebuilt_at") is None:
                profile = rebuild_profile_if_stale(dev_entity["id"])
            else:
                profile = dev_entity.get("profile", "")

            if profile:
                sections.append(f"### Developer: {dev_entity['name']}\n{profile}")

            # Known engagements — grouped by EPC with loyalty stats
            engagements = get_developer_engagements(dev_entity["id"])
            if engagements:
                total = len(engagements)
                # Group by EPC name
                by_epc: dict[str, list[dict]] = {}
                for eng in engagements:
                    epc_name = (
                        eng.get("epc", {}).get("name", "Unknown EPC")
                        if isinstance(eng.get("epc"), dict)
                        else "Unknown EPC"
                    )
                    by_epc.setdefault(epc_name, []).append(eng)

                num_epcs = len(by_epc)
                lines = [f"Known EPC relationships ({total} engagements across {num_epcs} EPCs):"]

                strongest_epc = None
                strongest_pct = 0
                strongest_states = ""

                for epc_name, engs in sorted(by_epc.items(), key=lambda x: -len(x[1])):
                    count = len(engs)
                    pct = round(100 * count / total) if total else 0
                    states = sorted({e.get("state", "?") for e in engs})
                    state_str = ", ".join(states)
                    lines.append(
                        f"- {epc_name}: {count} of {total} projects ({pct}%) — {state_str}"
                    )

                    if pct > strongest_pct:
                        strongest_pct = pct
                        strongest_epc = epc_name
                        strongest_states = state_str

                if strongest_epc and strongest_pct > 50:
                    lines.append(
                        f"\nStrongest signal: This developer has a repeated "
                        f"relationship with {strongest_epc} in {strongest_states}."
                    )

                sections.append("\n".join(lines))

    # 2. Prior research on this project — surface tried searches for negative knowledge
    if project_id:
        attempts = get_project_research_attempts(project_id)
        if attempts:
            lines = ["### Prior Research on This Project"]
            for att in attempts:
                date = att["created_at"][:10] if att.get("created_at") else "?"
                outcome = att["outcome"]
                searches = att.get("searches_performed", [])
                num_searches = len(searches) if searches else 0
                epc_str = f" Found: {att['epc_found']}." if att.get("epc_found") else ""
                lines.append(f"- {date}: {outcome} after {num_searches} searches.{epc_str}")
                if searches and outcome in ("not_found", "inconclusive"):
                    lines.append("  Searches already tried (do NOT repeat):")
                    for s in searches[:8]:
                        lines.append(f'  - "{s}"')
                    lines.append(
                        "  Try different angles: developer website, "
                        "EPC portfolio pages, regulatory filings."
                    )
                neg_evidence = att.get("negative_evidence", [])
                if neg_evidence:
                    lines.append("  Negative evidence from prior research:")
                    for ne in neg_evidence[:5]:
                        query = ne.get("search_query", "?")
                        found = ne.get("what_was_found", "nothing")
                        lines.append(f'  - Searched "{query}" — result: {found}')
            sections.append("\n".join(lines))

    # 3. EPCs active in this state — aggregated with project count, MW, recency
    if state:
        state_epcs = get_epcs_in_state(state)
        if state_epcs:
            total_engagements = len(state_epcs)
            # Group by EPC for aggregate stats
            by_epc: dict[str, list[dict]] = {}
            for eng in state_epcs:
                epc_name = (
                    eng.get("epc", {}).get("name", "Unknown")
                    if isinstance(eng.get("epc"), dict)
                    else "Unknown"
                )
                by_epc.setdefault(epc_name, []).append(eng)

            lines = [f"### EPCs Active in {state} (from {total_engagements} known engagements)"]
            for epc_name, engs in sorted(by_epc.items(), key=lambda x: -len(x[1])):
                num_projects = len(engs)
                total_mw = sum(
                    (eng.get("project", {}) if isinstance(eng.get("project"), dict) else {}).get(
                        "mw_capacity", 0
                    )
                    or 0
                    for eng in engs
                )
                # Format MW: use GW if >= 1000
                mw_str = f"{total_mw / 1000:.1f}GW" if total_mw >= 1000 else f"{total_mw}MW"
                # Most recent date
                dates = [e.get("created_at", "")[:7] for e in engs if e.get("created_at")]
                most_recent = max(dates) if dates else "?"
                # Best confidence
                conf_rank = {"confirmed": 3, "likely": 2, "possible": 1}
                best_conf = max(
                    (e.get("confidence", "possible") for e in engs),
                    key=lambda c: conf_rank.get(c, 0),
                )
                lines.append(
                    f"- **{epc_name}**: {num_projects} projects, "
                    f"{mw_str} total, most recent {most_recent} ({best_conf})"
                )
            sections.append("\n".join(lines))

    if not sections:
        return None

    return "## What We Already Know\n\n" + "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Write Path — called AFTER agent research
# ---------------------------------------------------------------------------


def process_discovery_into_kb(
    project_id: str,
    result: AgentResult,
    project: dict,
) -> None:
    """Write agent research results into the knowledge base.

    Called at discovery time. Logs a research_attempt and marks the
    developer profile as stale. Does NOT create engagements — that
    happens in promote_discovery_to_kb() on acceptance.
    """
    client = get_client()
    developer_name = project.get("developer")

    # 1. Resolve developer entity (create if needed)
    dev_entity = None
    if developer_name:
        try:
            dev_entity = resolve_or_create_entity(developer_name, "developer")
        except Exception as e:
            logger.warning("Failed to resolve developer entity %s: %s", developer_name, e)

    # 2. Always insert research_attempt
    outcome = _classify_outcome(result)
    negative_evidence_data = (
        [ne.model_dump() for ne in result.negative_evidence] if result.negative_evidence else []
    )
    attempt_data = {
        "project_id": project_id,
        "developer_entity_id": dev_entity["id"] if dev_entity else None,
        "outcome": outcome,
        "epc_found": result.epc_contractor
        if result.epc_contractor and result.epc_contractor != "Unknown"
        else None,
        "confidence": result.confidence,
        "searches_performed": result.searches_performed,
        "reasoning": result.reasoning,
        "related_findings": result.related_leads,
        "negative_evidence": negative_evidence_data,
        "tokens_used": 0,  # filled by caller if needed
    }
    try:
        client.table("research_attempts").insert(attempt_data).execute()
    except Exception as e:
        logger.error("Failed to insert research_attempt: %s", e)

    # 3. Mark developer profile as stale
    if dev_entity:
        try:
            client.table("entities").update({"profile_rebuilt_at": None}).eq(
                "id", dev_entity["id"]
            ).execute()
        except Exception as e:
            logger.warning("Failed to mark profile stale: %s", e)


def promote_discovery_to_kb(
    project_id: str,
    result: AgentResult,
    project: dict,
) -> None:
    """Promote an accepted discovery into the knowledge base.

    Called ONLY when a discovery is accepted. Creates the EPC engagement
    and processes related leads.
    """
    client = get_client()
    developer_name = project.get("developer")
    state = project.get("state")

    dev_entity = None
    if developer_name:
        try:
            dev_entity = resolve_or_create_entity(developer_name, "developer")
        except Exception as e:
            logger.warning("Failed to resolve developer entity %s: %s", developer_name, e)

    # Create EPC engagement
    if (
        result.epc_contractor
        and result.confidence != "unknown"
        and result.epc_contractor != "Unknown"
    ):
        try:
            epc_entity = resolve_or_create_entity(result.epc_contractor, "epc")
            if dev_entity:
                _upsert_engagement(
                    client=client,
                    developer_entity_id=dev_entity["id"],
                    epc_entity_id=epc_entity["id"],
                    project_id=project_id,
                    confidence=result.confidence,
                    sources=[s.model_dump() for s in result.sources],
                    state=state,
                )
        except Exception as e:
            logger.error("Failed to create EPC engagement: %s", e)

    # Process related_leads into additional engagements
    for lead in result.related_leads:
        try:
            _process_related_lead(client, lead, state)
        except Exception as e:
            logger.warning("Failed to process related lead: %s", e)

    # Mark developer profile as stale (engagements changed)
    if dev_entity:
        try:
            client.table("entities").update({"profile_rebuilt_at": None}).eq(
                "id", dev_entity["id"]
            ).execute()
        except Exception as e:
            logger.warning("Failed to mark profile stale: %s", e)


def process_rejection_into_kb(
    discovery: dict,
    reason: str | None = None,
) -> None:
    """Record a rejection in the knowledge base.

    Creates a research_attempt with outcome 'rejected_by_reviewer',
    deletes any matching epc_engagement, and marks the developer
    profile as stale.
    """
    client = get_client()
    project_id = discovery.get("project_id")
    epc_contractor = discovery.get("epc_contractor")

    # Find developer entity for this project
    dev_entity = None
    if project_id:
        project = (
            client.table("projects").select("developer").eq("id", project_id).limit(1).execute()
        )
        if project.data and project.data[0].get("developer"):
            dev_entity = resolve_entity(project.data[0]["developer"])

    # Insert research_attempt with rejected outcome
    attempt_data = {
        "project_id": project_id,
        "developer_entity_id": dev_entity["id"] if dev_entity else None,
        "outcome": "rejected_by_reviewer",
        "epc_found": epc_contractor if epc_contractor and epc_contractor != "Unknown" else None,
        "confidence": discovery.get("confidence", "unknown"),
        "searches_performed": discovery.get("searches_performed", []),
        "reasoning": reason or "Rejected by reviewer",
        "related_findings": [],
        "tokens_used": 0,
    }
    try:
        client.table("research_attempts").insert(attempt_data).execute()
    except Exception as e:
        logger.error("Failed to insert rejection research_attempt: %s", e)

    # Delete matching epc_engagement if it exists
    if dev_entity and epc_contractor and epc_contractor != "Unknown":
        epc_entity = resolve_entity(epc_contractor)
        if epc_entity:
            try:
                client.table("epc_engagements").delete().eq(
                    "developer_entity_id", dev_entity["id"]
                ).eq("epc_entity_id", epc_entity["id"]).eq("project_id", project_id).execute()
            except Exception as e:
                logger.warning("Failed to delete epc_engagement on rejection: %s", e)

    # Mark developer profile as stale
    if dev_entity:
        try:
            client.table("entities").update({"profile_rebuilt_at": None}).eq(
                "id", dev_entity["id"]
            ).execute()
        except Exception as e:
            logger.warning("Failed to mark profile stale: %s", e)


def _classify_outcome(result: AgentResult) -> str:
    """Map agent result to research_attempt outcome."""
    if result.confidence in ("confirmed", "likely"):
        return "found"
    elif result.confidence == "possible":
        return "inconclusive"
    return "not_found"


def _upsert_engagement(
    *,
    client,
    developer_entity_id: str,
    epc_entity_id: str,
    project_id: str,
    confidence: str,
    sources: list[dict],
    state: str | None,
) -> None:
    """Insert engagement, or update confidence/sources if it already exists."""
    try:
        client.table("epc_engagements").insert(
            {
                "developer_entity_id": developer_entity_id,
                "epc_entity_id": epc_entity_id,
                "project_id": project_id,
                "confidence": confidence,
                "sources": sources,
                "state": state,
            }
        ).execute()
    except Exception:
        # Likely duplicate — update existing
        try:
            resp = (
                client.table("epc_engagements")
                .select("id, confidence")
                .eq("developer_entity_id", developer_entity_id)
                .eq("epc_entity_id", epc_entity_id)
                .eq("project_id", project_id)
                .limit(1)
                .execute()
            )
            if resp.data:
                existing = resp.data[0]
                # Only upgrade confidence, never downgrade
                rank = {"confirmed": 3, "likely": 2, "possible": 1}
                if rank.get(confidence, 0) > rank.get(existing["confidence"], 0):
                    client.table("epc_engagements").update(
                        {
                            "confidence": confidence,
                            "sources": sources,
                        }
                    ).eq("id", existing["id"]).execute()
        except Exception as e:
            logger.error("Engagement upsert fallback failed: %s", e, exc_info=True)
            raise


def _process_related_lead(client, lead: dict, state: str | None) -> None:
    """Process a single related_lead from agent findings into KB."""
    dev_name = lead.get("developer")
    epc_name = lead.get("epc_contractor") or lead.get("epc")
    confidence = lead.get("confidence", "possible")

    if not dev_name or not epc_name:
        logger.debug(
            "Skipping related lead — missing %s",
            "developer" if not dev_name else "epc_contractor",
        )
        return

    # Validate confidence value
    if confidence not in ("confirmed", "likely", "possible"):
        confidence = "possible"

    dev_entity = resolve_or_create_entity(dev_name, "developer")
    epc_entity = resolve_or_create_entity(epc_name, "epc")

    _upsert_engagement(
        client=client,
        developer_entity_id=dev_entity["id"],
        epc_entity_id=epc_entity["id"],
        project_id=None,  # related leads may not have a specific project
        confidence=confidence,
        sources=[{"channel": "related_finding", "excerpt": lead.get("excerpt", "")}],
        state=lead.get("state") or state,
    )


# ---------------------------------------------------------------------------
# Profile Rebuild (lazy, template-based)
# ---------------------------------------------------------------------------


def rebuild_profile_if_stale(entity_id: str) -> str:
    """Rebuild an entity's profile if stale. Returns the profile text."""
    client = get_client()

    # Fetch entity
    resp = client.table("entities").select("*").eq("id", entity_id).limit(1).execute()
    if not resp.data:
        return ""
    entity = resp.data[0]

    # If profile is fresh, return it
    if entity.get("profile") and entity.get("profile_rebuilt_at"):
        return entity["profile"]

    # Build profile from engagements + research attempts
    entity_type = entity.get("entity_type", [])
    lines = [f"# {entity['name']}", f"Type: {', '.join(entity_type)}", ""]

    if entity.get("aliases"):
        lines.append(f"Aliases: {', '.join(entity['aliases'])}")
        lines.append("")

    # Engagements where this entity is the developer
    if "developer" in entity_type:
        dev_engs = (
            client.table("epc_engagements")
            .select(
                "*, epc:epc_entity_id(name), project:project_id(project_name, mw_capacity, state)"
            )
            .eq("developer_entity_id", entity_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        ).data

        if dev_engs:
            lines.append("## Known EPC Relationships")
            # Group by EPC
            by_epc: dict[str, list[dict]] = {}
            for eng in dev_engs:
                epc_name = (
                    eng.get("epc", {}).get("name", "Unknown")
                    if isinstance(eng.get("epc"), dict)
                    else "Unknown"
                )
                by_epc.setdefault(epc_name, []).append(eng)

            for epc_name, engs in by_epc.items():
                projects_str = []
                for eng in engs:
                    proj = eng.get("project", {}) if isinstance(eng.get("project"), dict) else {}
                    pname = proj.get("project_name", "Unknown")
                    mw = proj.get("mw_capacity", "?")
                    st = eng.get("state", "?")
                    projects_str.append(f"{pname} ({mw}MW, {st}) [{eng['confidence']}]")
                lines.append(f"- **{epc_name}**: {', '.join(projects_str)}")
            lines.append("")

        # Research attempts
        attempts = (
            client.table("research_attempts")
            .select(
                "outcome, epc_found, confidence, searches_performed, "
                "created_at, project:project_id(project_name)"
            )
            .eq("developer_entity_id", entity_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        ).data

        if attempts:
            found = sum(1 for a in attempts if a["outcome"] == "found")
            not_found = sum(1 for a in attempts if a["outcome"] == "not_found")
            lines.append("## Research History")
            lines.append(f"{len(attempts)} attempts: {found} found, {not_found} not found")
            lines.append("")

    # Engagements where this entity is the EPC
    if "epc" in entity_type:
        epc_engs = (
            client.table("epc_engagements")
            .select(
                "*, developer:developer_entity_id(name), "
                "project:project_id(project_name, mw_capacity, state)"
            )
            .eq("epc_entity_id", entity_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        ).data

        if epc_engs:
            lines.append("## Projects as EPC")
            for eng in epc_engs:
                dev_name = (
                    eng.get("developer", {}).get("name", "Unknown")
                    if isinstance(eng.get("developer"), dict)
                    else "Unknown"
                )
                proj = eng.get("project", {}) if isinstance(eng.get("project"), dict) else {}
                pname = proj.get("project_name", "Unknown")
                mw = proj.get("mw_capacity", "?")
                st = eng.get("state", "?")
                lines.append(
                    f"- {pname} ({mw}MW, {st}) — developer: {dev_name} [{eng['confidence']}]"
                )
            lines.append("")

    profile = "\n".join(lines)

    # Save profile
    now = datetime.now(UTC).isoformat()
    client.table("entities").update(
        {
            "profile": profile,
            "profile_rebuilt_at": now,
        }
    ).eq("id", entity_id).execute()

    return profile


# ---------------------------------------------------------------------------
# Query helpers (for chat tool and API)
# ---------------------------------------------------------------------------


def get_entity_with_profile(entity_id: str) -> dict | None:
    """Get an entity by ID, rebuilding profile if stale."""
    client = get_client()
    resp = client.table("entities").select("*").eq("id", entity_id).limit(1).execute()
    if not resp.data:
        return None
    entity = resp.data[0]
    if not entity.get("profile") or not entity.get("profile_rebuilt_at"):
        entity["profile"] = rebuild_profile_if_stale(entity_id)
    return entity


def list_entities(entity_type: str | None = None, limit: int = 50) -> list[dict]:
    """List entities, optionally filtered by type."""
    client = get_client()
    query = client.table("entities").select("id, name, entity_type, created_at, updated_at")
    if entity_type:
        query = query.contains("entity_type", [entity_type])
    query = query.order("name").limit(limit)
    resp = query.execute()
    return resp.data


def query_knowledge_base(entity_name: str | None = None, state: str | None = None) -> str:
    """Query KB for chat tool. Returns formatted markdown."""
    sections: list[str] = []

    if entity_name:
        entity = resolve_entity(entity_name)
        if entity:
            profile = rebuild_profile_if_stale(entity["id"])
            if profile:
                sections.append(profile)
            else:
                sections.append(f"Entity '{entity['name']}' found but no profile data yet.")
        else:
            sections.append(f"No entity found matching '{entity_name}'.")

    if state:
        epcs = get_epcs_in_state(state)
        if epcs:
            seen: set[str] = set()
            lines = [f"## EPCs Active in {state}"]
            for eng in epcs:
                epc_name = (
                    eng.get("epc", {}).get("name", "Unknown")
                    if isinstance(eng.get("epc"), dict)
                    else "Unknown"
                )
                if epc_name in seen:
                    continue
                seen.add(epc_name)
                proj = eng.get("project", {}) if isinstance(eng.get("project"), dict) else {}
                proj_name = proj.get("project_name", "?")
                mw = proj.get("mw_capacity", "?")
                lines.append(f"- **{epc_name}**: {eng['confidence']} for {proj_name} ({mw}MW)")
            sections.append("\n".join(lines))
        else:
            sections.append(f"No known EPC activity in {state}.")

    if not sections:
        return "Please provide an entity name or state to query."

    return "\n\n".join(sections)
