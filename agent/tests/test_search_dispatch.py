"""Tests for search_dispatch — procedural search+scrape+filter pipeline.

All tests mock tool execute() functions to avoid real API calls.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.search_dispatch import parallel_search, smart_scrape, execute_sub_query
from src.evidence import EvidenceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_result(title: str, url: str, content: str, score: float = 0.8) -> dict:
    return {"title": title, "url": url, "content": content, "score": score}


# ---------------------------------------------------------------------------
# parallel_search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_search_dedupes_urls():
    """Tavily returns A,B; Brave returns B,C. Result: [A, B, C] (B not duplicated)."""
    tavily_results = {
        "results": [
            _make_search_result("Page A", "https://a.com", "content a", 0.9),
            _make_search_result("Page B", "https://b.com", "content b", 0.8),
        ]
    }
    brave_results = {
        "results": [
            _make_search_result("Page B", "https://b.com", "content b brave", 0.7),
            _make_search_result("Page C", "https://c.com", "content c", 0.6),
        ]
    }

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(return_value=tavily_results)
        mock_brave.execute = AsyncMock(return_value=brave_results)

        result = await parallel_search("test query", max_results=5)

    urls = [r["url"] for r in result]
    assert "https://a.com" in urls
    assert "https://b.com" in urls
    assert "https://c.com" in urls
    # B should appear exactly once
    assert urls.count("https://b.com") == 1
    assert len(result) == 3


@pytest.mark.asyncio
async def test_parallel_search_handles_provider_failure():
    """Tavily raises Exception; Brave returns results. Still returns Brave results. No crash."""
    brave_results = {
        "results": [
            _make_search_result("Page X", "https://x.com", "content x", 0.75),
        ]
    }

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(side_effect=Exception("Tavily API down"))
        mock_brave.execute = AsyncMock(return_value=brave_results)

        result = await parallel_search("test query")

    assert len(result) == 1
    assert result[0]["url"] == "https://x.com"


@pytest.mark.asyncio
async def test_parallel_search_both_fail():
    """Both providers raise Exception → returns []."""
    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(side_effect=Exception("Tavily down"))
        mock_brave.execute = AsyncMock(side_effect=Exception("Brave down"))

        result = await parallel_search("test query")

    assert result == []


@pytest.mark.asyncio
async def test_parallel_search_sorted_by_score():
    """Results are sorted by score descending."""
    tavily_results = {
        "results": [
            _make_search_result("Low", "https://low.com", "low", 0.3),
            _make_search_result("High", "https://high.com", "high", 0.95),
        ]
    }
    brave_results = {
        "results": [
            _make_search_result("Mid", "https://mid.com", "mid", 0.6),
        ]
    }

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(return_value=tavily_results)
        mock_brave.execute = AsyncMock(return_value=brave_results)

        result = await parallel_search("test query", max_results=5)

    assert result[0]["url"] == "https://high.com"
    assert result[-1]["url"] == "https://low.com"


@pytest.mark.asyncio
async def test_parallel_search_respects_max_results_cap():
    """Returns at most max_results * 2 items."""
    # 6 unique URLs between the two providers
    tavily_results = {
        "results": [_make_search_result(f"T{i}", f"https://t{i}.com", f"c{i}") for i in range(3)]
    }
    brave_results = {
        "results": [_make_search_result(f"B{i}", f"https://b{i}.com", f"c{i}") for i in range(3)]
    }

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(return_value=tavily_results)
        mock_brave.execute = AsyncMock(return_value=brave_results)

        # max_results=2 → cap is 4
        result = await parallel_search("test query", max_results=2)

    assert len(result) <= 4


# ---------------------------------------------------------------------------
# smart_scrape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_scrape_firecrawl_preferred(monkeypatch):
    """FIRECRAWL_API_KEY set + firecrawl_extract succeeds → returns structured text.
    fetch_page NOT called.
    """
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

    firecrawl_result = {
        "url": "https://example.com",
        "extracted": {
            "epc_contractor": "Acme Solar",
            "project_name": "Desert Sun Farm",
            "mw_capacity": 150,
            "developer": "SunDev LLC",
        },
        "source_tool": "firecrawl_extract",
    }

    with patch("src.search_dispatch.firecrawl_extract") as mock_fc, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_fc.execute = AsyncMock(return_value=firecrawl_result)
        mock_fp.execute = AsyncMock(return_value={"text": "should not be called", "length": 100})

        result = await smart_scrape("https://example.com", "Acme Solar EPC")

    assert result is not None
    assert result["url"] == "https://example.com"
    assert "Acme Solar" in result["text"]
    assert "Desert Sun Farm" in result["text"]
    # fetch_page should NOT have been called
    mock_fp.execute.assert_not_called()


@pytest.mark.asyncio
async def test_smart_scrape_falls_back_to_fetch_page(monkeypatch):
    """FIRECRAWL_API_KEY not set → tries fetch_page, returns its text."""
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    fetch_result = {
        "url": "https://example.com",
        "text": "This is a long article about solar EPC contractors building projects." * 5,
        "length": 350,
    }

    with patch("src.search_dispatch.firecrawl_extract") as mock_fc, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_fc.execute = AsyncMock(return_value={"error": "no key"})
        mock_fp.execute = AsyncMock(return_value=fetch_result)

        result = await smart_scrape("https://example.com", "solar EPC")

    assert result is not None
    assert result["url"] == "https://example.com"
    assert len(result["text"]) > 100
    # firecrawl should NOT have been called (no API key)
    mock_fc.execute.assert_not_called()


@pytest.mark.asyncio
async def test_smart_scrape_both_fail(monkeypatch):
    """firecrawl errors + fetch_page errors → returns None."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

    with patch("src.search_dispatch.firecrawl_extract") as mock_fc, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_fc.execute = AsyncMock(return_value={"error": "extraction failed"})
        mock_fp.execute = AsyncMock(return_value={"error": "page not reachable"})

        result = await smart_scrape("https://broken.com", "query")

    assert result is None


@pytest.mark.asyncio
async def test_smart_scrape_fetch_page_too_short(monkeypatch):
    """fetch_page returns text < 100 chars → returns None."""
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    with patch("src.search_dispatch.firecrawl_extract") as mock_fc, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_fc.execute = AsyncMock()
        mock_fp.execute = AsyncMock(return_value={"url": "https://x.com", "text": "too short", "length": 9})

        result = await smart_scrape("https://x.com", "query")

    assert result is None


# ---------------------------------------------------------------------------
# execute_sub_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_sub_query_end_to_end(monkeypatch):
    """Mock all three stages. Verify evidence gets findings added and count is correct."""
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    search_results = {
        "results": [
            _make_search_result("Result 1", "https://r1.com", "content about EPC", 0.9),
            _make_search_result("Result 2", "https://r2.com", "another EPC article", 0.8),
        ]
    }
    fetch_text = "Detailed article about EPC contractor building solar farm in Texas." * 10

    compressor = MagicMock()
    compressor.filter = AsyncMock(return_value=[
        {"url": "https://r1.com", "text": "Filtered relevant chunk about EPC", "score": 0.85},
        {"url": "https://r2.com", "text": "Another filtered chunk about solar", "score": 0.72},
    ])

    evidence = EvidenceStore()

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_tavily.execute = AsyncMock(return_value=search_results)
        mock_brave.execute = AsyncMock(return_value={"results": []})
        mock_fp.execute = AsyncMock(return_value={"url": "https://r1.com", "text": fetch_text, "length": len(fetch_text)})

        count = await execute_sub_query("EPC contractor Texas solar", evidence, compressor, iteration=1)

    assert count == 2
    assert len(evidence.findings) == 2
    assert evidence.findings[0].iteration == 1
    assert evidence.findings[0].source_tool == "parallel_search"


@pytest.mark.asyncio
async def test_execute_sub_query_no_results(monkeypatch):
    """Search returns empty → returns 0, no crash."""
    compressor = MagicMock()
    compressor.filter = AsyncMock(return_value=[])
    evidence = EvidenceStore()

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(return_value={"results": []})
        mock_brave.execute = AsyncMock(return_value={"results": []})

        count = await execute_sub_query("no results query", evidence, compressor)

    assert count == 0
    assert len(evidence.findings) == 0


@pytest.mark.asyncio
async def test_execute_sub_query_records_search():
    """Verify evidence.record_search(query) is called (query in searches_performed)."""
    compressor = MagicMock()
    compressor.filter = AsyncMock(return_value=[])
    evidence = EvidenceStore()

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave:
        mock_tavily.execute = AsyncMock(return_value={"results": []})
        mock_brave.execute = AsyncMock(return_value={"results": []})

        await execute_sub_query("Acme Solar EPC contractor", evidence, compressor)

    assert "Acme Solar EPC contractor" in evidence.searches_performed


@pytest.mark.asyncio
async def test_execute_sub_query_compressor_failure_fallback(monkeypatch):
    """compressor.filter raises → uses unfiltered fallback, still adds findings."""
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    search_results = {
        "results": [
            _make_search_result("Result 1", "https://fallback1.com", "content", 0.9),
        ]
    }
    fetch_text = "Long enough article content for the fallback path to work correctly here." * 5

    compressor = MagicMock()
    compressor.filter = AsyncMock(side_effect=Exception("Embedding service unavailable"))

    evidence = EvidenceStore()

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_tavily.execute = AsyncMock(return_value=search_results)
        mock_brave.execute = AsyncMock(return_value={"results": []})
        mock_fp.execute = AsyncMock(return_value={"url": "https://fallback1.com", "text": fetch_text, "length": len(fetch_text)})

        count = await execute_sub_query("fallback query", evidence, compressor)

    # Should still add findings via fallback path
    assert count >= 1
    assert len(evidence.findings) >= 1


@pytest.mark.asyncio
async def test_execute_sub_query_deduplicates_urls(monkeypatch):
    """Same URL from search + scrape doesn't create duplicate findings."""
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    search_results = {
        "results": [
            _make_search_result("Same page", "https://same.com", "content", 0.9),
        ]
    }
    fetch_text = "Article content that is long enough to pass the 100 char threshold for scraping." * 3

    compressor = MagicMock()
    # Return the same URL twice in compressed results
    compressor.filter = AsyncMock(return_value=[
        {"url": "https://same.com", "text": "First chunk", "score": 0.9},
        {"url": "https://same.com", "text": "Second chunk", "score": 0.85},
    ])

    evidence = EvidenceStore()

    with patch("src.search_dispatch.web_search") as mock_tavily, \
         patch("src.search_dispatch.brave_search") as mock_brave, \
         patch("src.search_dispatch.fetch_page") as mock_fp:
        mock_tavily.execute = AsyncMock(return_value=search_results)
        mock_brave.execute = AsyncMock(return_value={"results": []})
        mock_fp.execute = AsyncMock(return_value={"url": "https://same.com", "text": fetch_text, "length": len(fetch_text)})

        count = await execute_sub_query("dedup test", evidence, compressor)

    # EvidenceStore dedupes by URL, so only 1 finding should be added
    assert count == 1
    assert len(evidence.findings) == 1
