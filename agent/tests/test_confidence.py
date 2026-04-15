"""Tests for confidence.py — confidence upgrade logic."""

from __future__ import annotations

from src.confidence import compute_confidence_upgrade
from src.models import EpcSource


def _make_source(
    url: str = "https://example.com", reliability: str = "medium", source_method: str | None = None
) -> EpcSource:
    return EpcSource(
        channel="web_search",
        excerpt="test excerpt",
        url=url,
        reliability=reliability,
        source_method=source_method,
    )


class TestNoUpgrade:
    def test_no_upgrade_when_conditions_not_met(self):
        """Single medium source with 'possible' should stay 'possible'."""
        sources = [_make_source(reliability="medium")]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert final == "possible"
        assert warning is None

    def test_unknown_stays_unknown(self):
        """Unknown confidence with no sources stays unknown."""
        final, count, warning = compute_confidence_upgrade([], "unknown")

        assert final == "unknown"
        assert count == 0


class TestPossibleToLikely:
    def test_upgrade_with_two_independent_high_reliability(self):
        """possible + 2 independent sources with total reliability >= 5 -> likely."""
        sources = [
            _make_source(url="https://a.com", reliability="high"),
            _make_source(url="https://b.com", reliability="medium"),
        ]
        final, count, warning = compute_confidence_upgrade(
            sources, "possible", epc_contractor="Sundt Construction"
        )

        assert final == "likely"
        assert count == 2

    def test_upgrade_with_three_medium_sources(self):
        """possible + 3 medium sources (reliability 6) -> likely."""
        sources = [
            _make_source(url="https://a.com", reliability="medium"),
            _make_source(url="https://b.com", reliability="medium"),
            _make_source(url="https://c.com", reliability="medium"),
        ]
        final, count, warning = compute_confidence_upgrade(
            sources, "possible", epc_contractor="Sundt Construction"
        )

        assert final == "likely"
        assert count == 3


class TestLikelyToConfirmed:
    def test_upgrade_with_two_independent_one_high(self):
        """likely + 2 independent sources with one high -> confirmed."""
        sources = [
            _make_source(url="https://a.com", reliability="high"),
            _make_source(url="https://b.com", reliability="medium"),
        ]
        final, count, warning = compute_confidence_upgrade(
            sources, "likely", epc_contractor="Sundt Construction"
        )

        assert final == "confirmed"
        assert count == 2


class TestNoSkipToConfirmed:
    def test_possible_does_not_jump_to_confirmed(self):
        """possible should NOT jump directly to confirmed, even with high reliability sources."""
        sources = [
            _make_source(url="https://a.com", reliability="high"),
            _make_source(url="https://b.com", reliability="high"),
        ]
        # Total reliability = 6 (>= 5), so possible -> likely
        # But since raw_confidence was "possible" (not "likely"), should NOT go to confirmed
        final, count, warning = compute_confidence_upgrade(
            sources, "possible", epc_contractor="Sundt Construction"
        )

        assert final == "likely"
        assert final != "confirmed"


class TestSingleLowReliabilityWarning:
    def test_single_low_source_gives_warning(self):
        """Single source with low reliability should produce a warning."""
        sources = [_make_source(reliability="low")]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert warning is not None
        assert "low-reliability" in warning.lower() or "unverified" in warning.lower()

    def test_multiple_sources_no_warning(self):
        """Multiple sources should not trigger the single-low warning."""
        sources = [
            _make_source(url="https://a.com", reliability="low"),
            _make_source(url="https://b.com", reliability="low"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert warning is None


class TestIndependenceCounting:
    def test_same_url_different_method_counts_as_one(self):
        """Same URL with different source_method should count as 1 independent source."""
        sources = [
            _make_source(url="https://a.com", source_method="web_search"),
            _make_source(url="https://a.com", source_method="web_search"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert count == 1

    def test_different_urls_count_as_independent(self):
        """Different URLs should count as separate independent sources."""
        sources = [
            _make_source(url="https://a.com"),
            _make_source(url="https://b.com"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert count == 2

    def test_search_prefix_urls_not_independent(self):
        """URLs with search: prefix should not count as independent sources (url becomes None)."""
        sources = [
            _make_source(url="search:some query", source_method=None),
            _make_source(url="search:another query", source_method=None),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        # search: URLs get url=None, and with no source_method, they don't count
        assert count == 0

    def test_search_prefix_with_different_methods_count(self):
        """search: URLs with distinct source_methods should count independently."""
        sources = [
            _make_source(url="search:q1", source_method="web_search"),
            _make_source(url="search:q2", source_method="fetch_page"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert count == 2


class TestEpcGuard:
    """Guard: confidence must NOT upgrade when no actual EPC contractor was identified."""

    def test_no_upgrade_when_epc_is_none(self):
        """2 high-reliability sources + possible → stays possible when epc is None."""
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="high", source_method="brave_search"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible", epc_contractor=None)

        assert final == "possible"
        assert count == 2
        assert warning is None

    def test_no_upgrade_when_epc_is_unknown_string(self):
        """Guard fires for epc_contractor='Unknown' (case-insensitive)."""
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="high", source_method="brave_search"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible", epc_contractor="Unknown")

        assert final == "possible"
        assert count == 2
        assert warning is None

    def test_no_upgrade_when_epc_is_empty_string(self):
        """Guard fires for epc_contractor='' (empty string)."""
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="high", source_method="brave_search"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible", epc_contractor="")

        assert final == "possible"
        assert count == 2
        assert warning is None

    def test_no_upgrade_when_epc_is_whitespace(self):
        """Guard fires for epc_contractor='   ' (whitespace-only string)."""
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="high", source_method="brave_search"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible", epc_contractor="   ")

        assert final == "possible"
        assert count == 2
        assert warning is None

    def test_upgrade_works_when_epc_is_real(self):
        """Upgrade still fires when a real EPC contractor is identified."""
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="high", source_method="brave_search"),
        ]
        final, count, warning = compute_confidence_upgrade(
            sources, "possible", epc_contractor="McCarthy Building Companies"
        )

        assert final == "likely"
        assert count == 2

    def test_likely_to_confirmed_with_real_epc(self):
        """likely + 2 independent sources (one high) + real EPC → confirmed."""
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="medium", source_method="brave_search"),
        ]
        final, count, warning = compute_confidence_upgrade(
            sources, "likely", epc_contractor="Mortenson"
        )

        assert final == "confirmed"
        assert count == 2

    def test_warning_for_single_low_source_with_unknown_epc(self):
        """Warning still fires for single low-reliability source even when guard blocks upgrade."""
        sources = [
            _make_source(url="https://a.com", reliability="low", source_method="tavily_search"),
        ]
        final, count, warning = compute_confidence_upgrade(sources, "possible", epc_contractor=None)

        assert final == "possible"
        assert count == 1
        assert warning == "Unverified \u2014 single low-reliability source"

    def test_default_epc_param_preserves_guard_behavior(self):
        """Omitting epc_contractor (default=None) triggers the guard — intentional behavior.

        Note: This is a deliberate breaking change for callers that pass no epc_contractor.
        Old callers that relied on the upgrade without specifying an EPC now get the guard
        applied, which is correct — there is no point upgrading confidence for an unknown EPC.
        The only call site (parsing.py) has been updated to pass epc_contractor explicitly.
        """
        sources = [
            _make_source(url="https://a.com", reliability="high", source_method="tavily_search"),
            _make_source(url="https://b.com", reliability="high", source_method="brave_search"),
        ]
        # Called without epc_contractor — guard fires, no upgrade
        final, count, warning = compute_confidence_upgrade(sources, "possible")

        assert final == "possible"  # guard fires; no upgrade without named EPC
