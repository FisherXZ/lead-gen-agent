"""Tests for the timeout salvage extraction module."""

import pytest
from src.salvage import synthesize_timeout_salvage
from src.models import EpcSource, NegativeEvidence


def _make_log(*entries):
    """Build a minimal agent_log from tool call tuples."""
    log = []
    for entry in entries:
        if isinstance(entry, tuple):
            tool, input_data = entry
            log.append({"tool": tool, "input": input_data})
        else:
            log.append(entry)
    return log


SAMPLE_PROJECT = {"project_name": "Honey Creek Solar", "state": "IN", "mw_capacity": 200}


class TestExtractSearchQueries:
    def test_extracts_search_queries(self):
        """5 web_search entries -> queries_tried has 5 correct strings."""
        log = _make_log(
            ("web_search", {"query": "Honey Creek Solar EPC contractor"}),
            ("web_search", {"query": "Honey Creek Solar Indiana construction"}),
            ("web_search", {"query": "200MW solar Indiana EPC"}),
            ("web_search", {"query": "Honey Creek Solar permit filing"}),
            ("web_search", {"query": "Indiana solar farm construction company"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert len(result["queries_tried"]) == 5
        assert result["queries_tried"][0] == "Honey Creek Solar EPC contractor"
        assert result["queries_tried"][4] == "Indiana solar farm construction company"


class TestExtractFetchUrls:
    def test_extracts_fetch_urls(self):
        """3 fetch_page entries -> sources_consulted has 3 URLs."""
        log = _make_log(
            ("fetch_page", {"url": "https://example.com/page1"}),
            ("fetch_page", {"url": "https://solarnews.com/article"}),
            ("fetch_page", {"url": "https://permits.in.gov/honey-creek"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert len(result["sources_consulted"]) == 3
        assert "https://example.com/page1" in result["sources_consulted"]
        assert "https://permits.in.gov/honey-creek" in result["sources_consulted"]


class TestExtractScratchpadNotes:
    def test_extracts_scratchpad_notes(self):
        """2 research_scratchpad entries -> correctly extracted into processing."""
        log = _make_log(
            ("research_scratchpad", {"note": "Found mention of solar project in trade pub"}),
            ("research_scratchpad", {"note": "Developer is SunDev LLC, checking their portfolio"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        # Notes are used for supporting_evidence (non-obstacle notes)
        assert len(result["supporting_evidence"]) == 2
        assert "Found mention of solar project" in result["supporting_evidence"][0]


class TestCandidateDetection:
    def test_candidate_detection_regex(self):
        """Scratchpad mentions known EPCs -> both in candidates_considered."""
        log = _make_log(
            ("research_scratchpad", {"note": "Found McCarthy Building portfolio includes solar"}),
            ("research_scratchpad", {"note": "Checking Blattner projects in Indiana region"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert "McCarthy Building" in result["candidate_names_considered"]
        assert "Blattner" in result["candidate_names_considered"]


class TestEntityElimination:
    def test_entity_elimination(self):
        """Scratchpad says 'Ruled out McCarthy Building' -> in entities_eliminated AND candidates."""
        log = _make_log(
            ("web_search", {"query": "McCarthy Building Indiana solar"}),
            ("research_scratchpad", {"note": "Found McCarthy Building mentioned in Indiana permits"}),
            ("research_scratchpad", {"note": "Ruled out McCarthy Building - no Indiana projects match"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert "McCarthy Building" in result["candidate_names_considered"]
        assert "McCarthy Building" in result["entities_eliminated"]


class TestEmptyAgentLog:
    def test_empty_agent_log(self):
        """Empty list, empty project -> valid dict, '0 queries' in summary."""
        result = synthesize_timeout_salvage([], {}, [])
        assert "0 queries" in result["summary"]
        assert result["queries_tried"] == []
        assert result["sources_consulted"] == []
        assert result["candidate_names_considered"] == []
        assert result["entities_eliminated"] == []
        assert isinstance(result["summary"], str)


class TestNoScratchpadUsed:
    def test_no_scratchpad_used(self):
        """Only web_search entries, no scratchpad -> candidates empty, queries populated."""
        log = _make_log(
            ("web_search", {"query": "Honey Creek Solar EPC"}),
            ("web_search", {"query": "Honey Creek Solar contractor"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert len(result["queries_tried"]) == 2
        assert result["candidate_names_considered"] == []
        assert result["entities_eliminated"] == []
        assert result["self_identified_obstacles"] == []


class TestSummaryTextFormat:
    def test_summary_text_format(self):
        """Realistic log -> summary contains project name, query count, source count."""
        log = _make_log(
            ("web_search", {"query": "Honey Creek Solar EPC contractor"}),
            ("web_search", {"query": "Honey Creek Solar Indiana construction"}),
            ("web_search", {"query": "200MW solar Indiana EPC"}),
            ("fetch_page", {"url": "https://example.com/article1"}),
            ("fetch_page", {"url": "https://example.com/article2"}),
            ("research_scratchpad", {"note": "Dead end on developer website, no EPC listed"}),
            {"iteration": 0, "stop_reason": "tool_use", "input_tokens": 1234, "output_tokens": 567},
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert "Honey Creek Solar" in result["summary"]
        assert "3 queries" in result["summary"]
        assert "2 sources" in result["summary"]


class TestStructuredReasoningShape:
    def test_returns_structured_reasoning_shape(self):
        """Verify dict has all required keys."""
        result = synthesize_timeout_salvage([], SAMPLE_PROJECT, [])
        required_keys = {
            "summary",
            "queries_tried",
            "sources_consulted",
            "candidate_names_considered",
            "entities_eliminated",
            "self_identified_obstacles",
            "next_recommended_action",
            "supporting_evidence",
            "gaps",
            "sources",
            "negative_evidence",
        }
        assert required_keys == set(result.keys())


class TestReturnsValidNegativeEvidence:
    def test_returns_valid_negative_evidence(self):
        """Log with eliminated EPC -> each item isinstance NegativeEvidence."""
        log = _make_log(
            ("web_search", {"query": "McCarthy Building Indiana solar projects"}),
            ("web_search", {"query": "Blattner Energy Indiana EPC"}),
            ("research_scratchpad", {"note": "Found McCarthy Building in search results"}),
            ("research_scratchpad", {"note": "Ruled out McCarthy Building - wrong state, no evidence of Indiana work"}),
            ("research_scratchpad", {"note": "Blattner mentioned but eliminated - not active in this region"}),
        )
        result = synthesize_timeout_salvage(log, SAMPLE_PROJECT, [])
        assert len(result["negative_evidence"]) > 0
        for item in result["negative_evidence"]:
            assert isinstance(item, NegativeEvidence)
            assert item.search_query  # non-empty
            assert item.what_was_found == "nothing"
