"""Tests for parsing.py — report_findings parser."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.parsing import parse_report_findings
from src.models import AgentResult


class TestBasicParsing:
    def test_all_fields_present(self):
        """Parse a complete report_findings input with all fields."""
        result = parse_report_findings({
            "epc_contractor": "Blattner Energy",
            "confidence": "likely",
            "sources": [
                {
                    "channel": "trade_publication",
                    "publication": "Solar Power World",
                    "date": "2025-06-01",
                    "url": "https://example.com/article",
                    "excerpt": "Blattner awarded EPC contract",
                    "reliability": "high",
                    "source_method": "web_search",
                }
            ],
            "reasoning": "Found in trade publication.",
            "searches_performed": ["Blattner Sunrise Solar EPC"],
            "related_findings": [{"developer": "DevCo", "epc_contractor": "X"}],
            "negative_evidence": [
                {
                    "search_query": "Sunrise Solar EPC filing",
                    "expected_to_find": "regulatory filing",
                    "what_was_found": "nothing",
                }
            ],
        })

        assert isinstance(result, AgentResult)
        assert result.epc_contractor == "Blattner Energy"
        assert len(result.sources) == 1
        assert result.sources[0].channel == "trade_publication"
        assert result.sources[0].publication == "Solar Power World"
        assert result.sources[0].url == "https://example.com/article"
        assert result.sources[0].source_method == "web_search"
        assert result.reasoning == "Found in trade publication."
        assert result.searches_performed == ["Blattner Sunrise Solar EPC"]
        assert result.related_leads == [{"developer": "DevCo", "epc_contractor": "X"}]


class TestUrlFallback:
    def test_no_url_falls_back_to_search_prefix(self):
        """When source has no URL, fall back to search:<first_search>."""
        result = parse_report_findings({
            "epc_contractor": "Test EPC",
            "confidence": "possible",
            "sources": [{"channel": "web_search", "excerpt": "found something"}],
            "searches_performed": ["test query"],
        })

        assert result.sources[0].url == "search:test query"
        assert result.sources[0].search_query == "test query"

    def test_empty_search_prefix_becomes_none(self):
        """A source with url='search:' (empty query) should get url=None."""
        result = parse_report_findings({
            "epc_contractor": "Test EPC",
            "confidence": "possible",
            "sources": [
                {"channel": "web_search", "excerpt": "x", "url": "search:"}
            ],
            "searches_performed": [],
        })

        assert result.sources[0].url is None
        assert result.sources[0].search_query is None

    def test_search_prefix_extracts_query(self):
        """A source with url='search:some query' extracts search_query."""
        result = parse_report_findings({
            "epc_contractor": "Test EPC",
            "confidence": "possible",
            "sources": [
                {"channel": "web_search", "excerpt": "x", "url": "search:my query"}
            ],
            "searches_performed": [],
        })

        assert result.sources[0].url == "search:my query"
        assert result.sources[0].search_query == "my query"


class TestSourceMethod:
    def test_source_method_passed_through(self):
        """source_method from input is preserved on the EpcSource."""
        result = parse_report_findings({
            "epc_contractor": "Test EPC",
            "confidence": "possible",
            "sources": [
                {
                    "channel": "web_search",
                    "excerpt": "x",
                    "url": "https://example.com",
                    "source_method": "fetch_page",
                }
            ],
            "searches_performed": [],
        })

        assert result.sources[0].source_method == "fetch_page"


class TestNegativeEvidence:
    def test_negative_evidence_parsed(self):
        """Negative evidence list is parsed into NegativeEvidence models."""
        result = parse_report_findings({
            "confidence": "unknown",
            "reasoning": "nothing found",
            "searches_performed": ["q1"],
            "negative_evidence": [
                {
                    "search_query": "q1",
                    "expected_to_find": "EPC contract",
                    "what_was_found": "nothing",
                },
                {
                    "search_query": "q2",
                    "what_was_found": "different_project",
                },
            ],
        })

        assert len(result.negative_evidence) == 2
        assert result.negative_evidence[0].search_query == "q1"
        assert result.negative_evidence[0].expected_to_find == "EPC contract"
        assert result.negative_evidence[1].what_was_found == "different_project"


class TestConfidenceUpgradeCalled:
    @patch("src.parsing.compute_confidence_upgrade")
    def test_confidence_upgrade_is_called(self, mock_upgrade):
        """compute_confidence_upgrade is called with sources and raw confidence."""
        mock_upgrade.return_value = ("confirmed", 2, None)

        result = parse_report_findings({
            "epc_contractor": "Test EPC",
            "confidence": "likely",
            "sources": [
                {"channel": "web_search", "excerpt": "x", "url": "https://a.com", "reliability": "high"},
                {"channel": "news_article", "excerpt": "y", "url": "https://b.com", "reliability": "medium"},
            ],
            "searches_performed": ["q"],
        })

        mock_upgrade.assert_called_once()
        args = mock_upgrade.call_args
        assert len(args[0][0]) == 2  # 2 sources passed
        assert args[0][1] == "likely"  # raw confidence passed
        assert result.confidence == "confirmed"
        assert result.agent_confidence == "likely"
