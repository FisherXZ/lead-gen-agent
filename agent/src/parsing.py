"""Shared report_findings parser.

Used by both research.py (standalone/batch) and chat_agent.py to convert
the report_findings tool input into an AgentResult.
"""

from __future__ import annotations

from .confidence import compute_confidence_upgrade
from .models import AgentResult, EpcSource, NegativeEvidence


def parse_report_findings(tool_input: dict) -> AgentResult:
    """Parse report_findings tool input into an AgentResult.

    Handles URL fallback logic (search: prefix), source_method extraction,
    confidence upgrade computation, and negative evidence parsing.
    """
    searches_performed = tool_input.get("searches_performed", [])
    first_search = searches_performed[0] if searches_performed else None

    sources: list[EpcSource] = []
    for s in tool_input.get("sources", []):
        url = s.get("url") or None
        search_query: str | None = None

        # If URL is missing/empty, fall back to first search query with "search:" prefix
        if not url and first_search:
            url = f"search:{first_search}"
            search_query = first_search
        elif url and url.startswith("search:"):
            search_query = url[len("search:"):].strip() or None
            if not search_query:
                url = None

        sources.append(EpcSource(
            channel=s.get("channel", "web_search"),
            publication=s.get("publication"),
            date=s.get("date"),
            url=url,
            excerpt=s.get("excerpt", ""),
            reliability=s.get("reliability", "medium"),
            search_query=search_query,
            source_method=s.get("source_method"),
        ))

    # Parse negative evidence
    negative_evidence: list[NegativeEvidence] = []
    for ne in tool_input.get("negative_evidence", []):
        negative_evidence.append(NegativeEvidence(
            search_query=ne.get("search_query", ""),
            expected_to_find=ne.get("expected_to_find"),
            what_was_found=ne.get("what_was_found", "nothing"),
        ))

    # Compute confidence upgrade
    raw_confidence = tool_input.get("confidence", "unknown")
    final_confidence, independent_count, warning = compute_confidence_upgrade(
        sources, raw_confidence
    )

    return AgentResult(
        epc_contractor=tool_input.get("epc_contractor"),
        confidence=final_confidence,
        agent_confidence=raw_confidence,
        source_count=independent_count,
        confidence_warning=warning,
        sources=sources,
        reasoning=tool_input.get("reasoning", ""),
        related_leads=tool_input.get("related_findings", []),
        searches_performed=searches_performed,
        negative_evidence=negative_evidence,
    )
