"""Tests for EvidenceStore and extract_findings_from_tool_result."""

from src.evidence import EvidenceStore, extract_findings_from_tool_result
from src.models import Finding


# ---------------------------------------------------------------------------
# EvidenceStore
# ---------------------------------------------------------------------------


class TestEvidenceStore:
    def test_add_finding(self):
        store = EvidenceStore()
        added = store.add(Finding(
            text="McCarthy selected as EPC",
            source_url="https://example.com/pr",
            source_tool="tavily_search",
            reliability="high",
            iteration=1,
        ))
        assert added is True
        assert len(store.findings) == 1
        assert store.findings[0].source_tool == "tavily_search"

    def test_dedup_same_url(self):
        store = EvidenceStore()
        store.add(Finding(
            text="McCarthy selected as EPC",
            source_url="https://example.com/pr",
            source_tool="tavily_search",
            iteration=1,
        ))
        added = store.add(Finding(
            text="McCarthy named contractor for project",
            source_url="https://example.com/pr",
            source_tool="brave_search",
            iteration=2,
        ))
        assert added is False
        assert len(store.findings) == 1

    def test_different_urls_kept(self):
        store = EvidenceStore()
        store.add(Finding(
            text="McCarthy from Reuters",
            source_url="https://reuters.com/pr",
            source_tool="tavily_search",
            iteration=1,
        ))
        store.add(Finding(
            text="McCarthy portfolio",
            source_url="https://mccarthybuilding.com/solar",
            source_tool="page_fetch",
            iteration=2,
        ))
        assert len(store.findings) == 2

    def test_format_for_prompt(self):
        store = EvidenceStore()
        store.add(Finding(
            text="McCarthy selected as EPC for 200MW project",
            source_url="https://example.com/pr",
            source_tool="tavily_search",
            reliability="high",
            iteration=1,
        ))
        store.add(Finding(
            text="OSHA record shows McCarthy at site",
            source_url="https://osha.gov/record/123",
            source_tool="osha_inspection",
            reliability="high",
            iteration=2,
        ))
        text = store.format_for_prompt()
        assert "[1]" in text
        assert "[2]" in text
        assert "McCarthy selected" in text
        assert "OSHA record" in text

    def test_format_empty(self):
        store = EvidenceStore()
        text = store.format_for_prompt()
        assert "No findings" in text

    def test_visited_urls(self):
        store = EvidenceStore()
        store.add(Finding(
            text="something",
            source_url="https://example.com/a",
            source_tool="web_search",
            iteration=1,
        ))
        assert "https://example.com/a" in store.visited_urls
        assert "https://other.com" not in store.visited_urls

    def test_searches_performed(self):
        store = EvidenceStore()
        store.record_search("McCarthy solar EPC Texas")
        store.record_search("McCarthy Building solar portfolio")
        assert len(store.searches_performed) == 2
        assert "McCarthy solar EPC Texas" in store.searches_performed


# ---------------------------------------------------------------------------
# extract_findings_from_tool_result
# ---------------------------------------------------------------------------


class TestExtractFindings:
    def test_web_search_results(self):
        store = EvidenceStore()
        result = {
            "results": [
                {
                    "title": "McCarthy Wins Solar Contract",
                    "url": "https://example.com/article",
                    "content": "McCarthy Building Companies has been awarded the EPC contract for a 200MW solar project in Texas, according to a press release.",
                    "score": 0.92,
                },
                {
                    "title": "Short",
                    "url": "https://example.com/short",
                    "content": "Too short",  # <50 chars, should be skipped
                    "score": 0.5,
                },
            ]
        }
        extract_findings_from_tool_result(
            "web_search", {"query": "McCarthy solar EPC"}, result, store, iteration=1
        )
        assert len(store.findings) == 1
        assert "McCarthy Wins Solar Contract" in store.findings[0].text
        assert store.findings[0].source_tool == "tavily_search"
        assert "McCarthy solar EPC" in store.searches_performed

    def test_brave_search_results(self):
        store = EvidenceStore()
        result = {
            "results": [
                {
                    "title": "Mortenson Solar Portfolio",
                    "url": "https://mortenson.com/solar",
                    "content": "Mortenson has built over 10GW of solar projects across the United States, making them one of the top EPCs.",
                    "score": 0.88,
                },
            ]
        }
        extract_findings_from_tool_result(
            "web_search_broad", {"query": "Mortenson solar"}, result, store
        )
        assert len(store.findings) == 1
        assert store.findings[0].source_tool == "brave_search"

    def test_fetch_page_result(self):
        store = EvidenceStore()
        long_text = "A" * 200  # >100 chars threshold
        result = {"url": "https://example.com/page", "text": long_text, "length": 200}
        extract_findings_from_tool_result(
            "fetch_page", {"url": "https://example.com/page"}, result, store
        )
        assert len(store.findings) == 1
        assert store.findings[0].source_tool == "page_fetch"
        assert store.findings[0].source_url == "https://example.com/page"

    def test_fetch_page_truncates_long_content(self):
        store = EvidenceStore()
        long_text = "X" * 5000
        result = {"url": "https://example.com/long", "text": long_text, "length": 5000}
        extract_findings_from_tool_result(
            "fetch_page", {"url": "https://example.com/long"}, result, store
        )
        assert len(store.findings[0].text) == 2000

    def test_fetch_page_short_content_skipped(self):
        store = EvidenceStore()
        result = {"url": "https://example.com/tiny", "text": "Short", "length": 5}
        extract_findings_from_tool_result(
            "fetch_page", {"url": "https://example.com/tiny"}, result, store
        )
        assert len(store.findings) == 0

    def test_sec_edgar_results(self):
        store = EvidenceStore()
        result = {
            "results": [
                {
                    "company_name": "NextEra Energy",
                    "cik": "0000753308",
                    "form_type": "8-K",
                    "filing_date": "2025-06-15",
                    "accession_number": "0000753308-25-000012",
                    "primary_document": "filing.htm",
                    "description": "Material event — construction contract",
                    "url": "https://www.sec.gov/Archives/edgar/data/0000753308/000075330825000012/filing.htm",
                    "source_type": "sec_edgar",
                },
            ]
        }
        extract_findings_from_tool_result(
            "search_sec_edgar", {"company_name": "NextEra Energy"}, result, store
        )
        assert len(store.findings) == 1
        assert store.findings[0].source_tool == "sec_edgar"
        assert store.findings[0].reliability == "high"
        assert "8-K" in store.findings[0].text
        assert "NextEra Energy" in store.searches_performed

    def test_osha_results(self):
        store = EvidenceStore()
        result = {
            "results": [
                {
                    "employer_name": "McCarthy Building Companies",
                    "inspection_number": "1234567",
                    "sic_code": "1731",
                    "naics_code": "238210",
                    "address": "Austin, TX, 78701",
                    "city": "Austin",
                    "state": "TX",
                    "zip": "78701",
                    "inspection_date": "2025-03-15",
                    "detail_url": "https://www.osha.gov/pls/imis/establishment.inspection_detail?id=1234567",
                    "source_type": "osha_inspection",
                },
            ],
            "total_found": 1,
        }
        extract_findings_from_tool_result(
            "search_osha", {"employer_name": "McCarthy"}, result, store
        )
        assert len(store.findings) == 1
        assert store.findings[0].source_tool == "osha_inspection"
        assert store.findings[0].reliability == "high"
        assert "McCarthy Building Companies" in store.findings[0].text
        assert "Austin, TX" in store.findings[0].text

    def test_wiki_solar_found(self):
        store = EvidenceStore()
        result = {
            "found": True,
            "epc_name": "McCarthy Building Companies",
            "wiki_solar_rank": 5,
            "mw_installed": 3200,
            "ranking_source": "wiki_solar_2024",
            "source_type": "wiki_solar_ranking",
        }
        extract_findings_from_tool_result(
            "search_wiki_solar", {"epc_name": "McCarthy"}, result, store
        )
        assert len(store.findings) == 1
        assert "#5" in store.findings[0].text
        assert "3200MW" in store.findings[0].text

    def test_wiki_solar_not_found(self):
        store = EvidenceStore()
        result = {
            "found": False,
            "note": "'NoName Inc' not found in entity database.",
        }
        extract_findings_from_tool_result(
            "search_wiki_solar", {"epc_name": "NoName Inc"}, result, store
        )
        assert len(store.findings) == 0

    def test_wiki_solar_found_but_unranked(self):
        store = EvidenceStore()
        result = {
            "found": True,
            "ranked": False,
            "epc_name": "Small EPC Co",
            "entity_type": ["epc"],
            "note": "In KB but not in Wiki-Solar rankings.",
        }
        extract_findings_from_tool_result(
            "search_wiki_solar", {"epc_name": "Small EPC Co"}, result, store
        )
        assert len(store.findings) == 0  # No wiki_solar_rank → no finding

    def test_spw_found(self):
        store = EvidenceStore()
        result = {
            "found": True,
            "epc_name": "SOLV Energy",
            "spw_rank": 3,
            "spw_kw_installed": 5000000,
            "spw_markets": "utility",
            "spw_service_type": "EPC",
            "source_type": "spw_ranking",
        }
        extract_findings_from_tool_result(
            "search_spw", {"epc_name": "SOLV Energy"}, result, store
        )
        assert len(store.findings) == 1
        assert "#3" in store.findings[0].text
        assert "EPC" in store.findings[0].text

    def test_error_result_skipped(self):
        store = EvidenceStore()
        result = {"error": "Tavily search failed: timeout"}
        extract_findings_from_tool_result(
            "web_search", {"query": "test"}, result, store
        )
        assert len(store.findings) == 0
        assert len(store.searches_performed) == 0

    def test_unknown_tool_does_nothing(self):
        store = EvidenceStore()
        result = {"data": "something"}
        extract_findings_from_tool_result(
            "unknown_tool", {}, result, store
        )
        assert len(store.findings) == 0

    def test_iteration_tracking(self):
        store = EvidenceStore()
        result = {
            "results": [
                {
                    "title": "Test",
                    "url": "https://example.com/1",
                    "content": "A" * 60,
                    "score": 0.9,
                },
            ]
        }
        extract_findings_from_tool_result(
            "web_search", {"query": "test"}, result, store, iteration=3
        )
        assert store.findings[0].iteration == 3
