"""Confidence aggregation and upgrade logic.

Computes a final confidence level based on the number and quality of
independent sources, potentially upgrading the agent's raw confidence.
"""

from __future__ import annotations

from .models import EpcSource

RELIABILITY_SCORE = {"high": 3, "medium": 2, "low": 1}
CONFIDENCE_RANK = {"confirmed": 3, "likely": 2, "possible": 1, "unknown": 0}


def compute_confidence_upgrade(
    sources: list[EpcSource],
    raw_confidence: str,
    epc_contractor: str | None = None,
) -> tuple[str, int, str | None]:
    """Compute a confidence upgrade based on source independence and quality.

    Returns:
        (final_confidence, independent_source_count, warning_or_none)

    Rules (only upgrade, never downgrade):
      - possible + 2+ independent sources with total reliability >= 5 -> likely
      - likely + 2+ independent sources with at least one high reliability -> confirmed
      - Single source with reliability="low" -> warning

    Guard: if epc_contractor is None, empty, or "unknown", confidence is never
    upgraded. An honest "unknown" with many supporting sources should remain
    "unknown" — the sources support context, not an EPC identity.
    """
    # Count independent sources: distinct (url, source_method) pairs,
    # excluding search: prefix URLs
    seen: set[tuple[str | None, str | None]] = set()
    for s in sources:
        url = s.url if s.url and not s.url.startswith("search:") else None
        key = (url, s.source_method)
        # Only count as independent if we have a real URL or distinct method
        if url or s.source_method:
            seen.add(key)

    independent_count = len(seen)

    # Guard: don't upgrade confidence if no actual EPC was identified.
    # An honest "unknown" with many supporting sources should remain "unknown"
    # — the sources support context, not an EPC identity.
    if not epc_contractor or epc_contractor.strip().lower() in ("", "unknown"):
        # Compute warning for single low-rel source case, but skip upgrade
        warning = None
        if len(sources) == 1 and sources[0].reliability == "low":
            warning = "Unverified \u2014 single low-reliability source"
        return raw_confidence, independent_count, warning

    # Compute total reliability score
    total_reliability = sum(RELIABILITY_SCORE.get(s.reliability, 1) for s in sources)
    has_high = any(s.reliability == "high" for s in sources)

    final_confidence = raw_confidence
    warning: str | None = None

    # Upgrade rules
    current_rank = CONFIDENCE_RANK.get(raw_confidence, 0)

    if (
        current_rank <= CONFIDENCE_RANK["possible"]
        and independent_count >= 2
        and total_reliability >= 5
    ):
        final_confidence = "likely"
        current_rank = CONFIDENCE_RANK["likely"]

    if (
        raw_confidence == "likely"  # Only upgrade from agent-reported "likely", not auto-upgraded
        and independent_count >= 2
        and has_high
    ):
        final_confidence = "confirmed"

    # Warning for single low-reliability source
    if len(sources) == 1 and sources[0].reliability == "low":
        warning = "Unverified \u2014 single low-reliability source"

    return final_confidence, independent_count, warning
