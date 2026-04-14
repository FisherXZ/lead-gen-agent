"""Deterministic extraction of structured negative evidence from timed-out research runs.

When a research agent hits MAX_ITERATIONS without calling report_findings, this
module extracts everything it learned from the agent_log and recent_tool_outputs.
No LLM call. Pure dict traversal + regex matching. Cost: <50ms, 0 tokens.
"""

from __future__ import annotations

import re

from .models import EpcSource, NegativeEvidence


# Known EPC contractors for candidate detection in scratchpad notes
KNOWN_EPCS = [
    "McCarthy Building", "Mortenson", "Blattner", "Signal Energy", "SOLV Energy",
    "Primoris", "Rosendin", "Strata Solar", "RES", "Renewable Energy Systems",
    "NextEra", "Invenergy", "Array Technologies", "GameChange Solar",
    "Swinerton", "Burns McDonnell", "Burns & McDonnell", "Quanta Services",
    "MasTec", "Tetra Tech", "Black & Veatch", "Bechtel", "Fluor",
    "SunPower", "First Solar", "Canadian Solar", "JinkoSolar",
    "LONGi", "Trina Solar", "BayWa", "Enel", "Acciona", "Iberdrola",
    "EDF Renewables", "TotalEnergies", "bp", "Shell", "Clearway",
    "AES", "Duke Energy Renewables", "Avangrid", "Orsted",
    "Leeward Renewable Energy", "Lightsource bp", "Silicon Ranch",
    "Cypress Creek Renewables", "Scout Clean Energy", "Savion",
    "174 Power Global", "D.E. Shaw Renewable Investments",
]

_ELIMINATION_RE = re.compile(
    r"\b(ruled out|eliminated|not\b|no match|doesn't match|does not match|"
    r"no evidence|couldn't find|could not find|unlikely|wrong|incorrect)\b",
    re.IGNORECASE,
)

_OBSTACLE_RE = re.compile(
    r"(dead end|stuck|cannot find|no public|pre-financial|early stage|"
    r"not announced|no information|blocked|unable to)",
    re.IGNORECASE,
)


def synthesize_timeout_salvage(
    agent_log: list[dict],
    project: dict,
    recent_tool_outputs: list[dict],
) -> dict:
    """Extract structured negative evidence from a timed-out research run.

    Returns dict with keys matching the spec: summary, queries_tried,
    sources_consulted, candidate_names_considered, entities_eliminated,
    self_identified_obstacles, next_recommended_action, supporting_evidence,
    gaps, sources, negative_evidence.
    """
    queries_tried = [
        e["input"]["query"]
        for e in agent_log
        if e.get("tool") in {"web_search", "web_search_broad"}
    ]

    sources_consulted = [
        e["input"]["url"]
        for e in agent_log
        if e.get("tool") == "fetch_page"
    ]

    scratchpad_notes = [
        e["input"]["note"]
        for e in agent_log
        if e.get("tool") == "research_scratchpad"
    ]

    # Detect candidate EPC names mentioned in scratchpad
    all_scratchpad_text = " ".join(scratchpad_notes)
    candidates_considered: list[str] = []
    entities_eliminated: list[str] = []

    for epc in KNOWN_EPCS:
        if epc.lower() in all_scratchpad_text.lower():
            candidates_considered.append(epc)
            # Check if this EPC was explicitly eliminated
            for note in scratchpad_notes:
                if epc.lower() in note.lower() and _ELIMINATION_RE.search(note):
                    entities_eliminated.append(epc)
                    break

    # Self-identified obstacles from scratchpad
    obstacles = [note for note in scratchpad_notes if _OBSTACLE_RE.search(note)]

    # Determine recommended next action
    if obstacles and any(
        "pre-financial" in o.lower()
        or "early stage" in o.lower()
        or "not announced" in o.lower()
        for o in obstacles
    ):
        next_action = "defer"
    elif len(queries_tried) < 5:
        next_action = "triage_retry"
    else:
        next_action = "manual_review"

    # Build human-readable summary
    project_name = project.get("project_name", "Unknown")
    parts = [
        f"Research hit iteration cap without identifying EPC for {project_name}.",
        f"Agent tried {len(queries_tried)} queries across {len(sources_consulted)} sources.",
    ]
    if candidates_considered:
        parts.append(f"Candidate contractors considered: {', '.join(candidates_considered)}.")
    if entities_eliminated:
        parts.append(f"Explicitly eliminated: {', '.join(entities_eliminated)}.")
    if obstacles:
        parts.append(f'Primary obstacle identified by agent: "{obstacles[0][:200]}".')
    parts.append(f"Recommended next step: {next_action}.")
    summary = " ".join(parts)

    # Supporting evidence: non-obstacle scratchpad notes
    supporting_evidence = [
        note[:500] for note in scratchpad_notes if not _OBSTACLE_RE.search(note)
    ]

    # Gaps: what was still missing
    gaps: list[str] = []
    if not candidates_considered:
        gaps.append("No EPC candidates identified during research")
    if not sources_consulted:
        gaps.append("No web pages fetched during research")
    for obs in obstacles[:3]:
        gaps.append(obs[:300])

    # Build EpcSource objects
    epc_sources = [
        EpcSource(
            channel="web_search",
            excerpt=f"Fetched during timeout research for {project_name}",
            url=url,
            reliability="low",
        )
        for url in sources_consulted[:10]
    ]

    # Build NegativeEvidence objects
    neg_evidence = []
    for epc in entities_eliminated:
        # Find the most relevant query for this EPC
        relevant_query = next(
            (q for q in queries_tried if epc.lower().split()[0].lower() in q.lower()),
            queries_tried[0] if queries_tried else f"search for {epc}",
        )
        neg_evidence.append(
            NegativeEvidence(
                search_query=relevant_query,
                expected_to_find=epc,
                what_was_found="nothing",
            )
        )

    return {
        "summary": summary,
        "queries_tried": queries_tried,
        "sources_consulted": sources_consulted,
        "candidate_names_considered": candidates_considered,
        "entities_eliminated": entities_eliminated,
        "self_identified_obstacles": obstacles,
        "next_recommended_action": next_action,
        "supporting_evidence": supporting_evidence,
        "gaps": gaps,
        "sources": epc_sources,
        "negative_evidence": neg_evidence,
    }
