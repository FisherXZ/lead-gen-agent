"""Tests for the firecrawl_extract tool and its evidence extraction mapping."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.evidence import EvidenceStore, extract_findings_from_tool_result
from src.models import Finding


# ---------------------------------------------------------------------------
# Tool input validation / early errors (no API key, no URL, etc.)
# ---------------------------------------------------------------------------


class TestFirecrawlExtractValidation:
    async def test_empty_url(self):
        from src.tools.firecrawl_extract import execute

        result = await execute({"url": ""})
        assert "error" in result
        assert "Empty" in result["error"]

    async def test_invalid_scheme(self):
        from src.tools.firecrawl_extract import execute

        result = await execute({"url": "ftp://example.com/file"})
        assert "error" in result
        assert "http" in result["error"]

    async def test_missing_api_key(self, monkeypatch):
        from src.tools.firecrawl_extract import execute

        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        result = await execute({"url": "https://example.com/pr"})
        assert "error" in result
        assert "FIRECRAWL_API_KEY" in result["error"]

    async def test_sdk_not_installed(self, monkeypatch):
        """When firecrawl-py is not installed, tool returns a structured error."""
        from src.tools.firecrawl_extract import execute

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")

        # Simulate ImportError by removing firecrawl from sys.modules and
        # patching importlib to raise
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "firecrawl":
                raise ImportError("No module named 'firecrawl'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            # Remove cached module if present
            sys.modules.pop("firecrawl", None)
            result = await execute({"url": "https://example.com/pr"})

        assert "error" in result
        assert "firecrawl-py" in result["error"]


# ---------------------------------------------------------------------------
# Successful extraction (mocked SDK)
# ---------------------------------------------------------------------------


class TestFirecrawlExtractSuccess:
    async def test_happy_path(self, monkeypatch):
        """SDK returns structured data → tool returns extracted dict."""
        from src.tools.firecrawl_extract import execute

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")

        # Build a fake SDK response: result.data.json is the structured extraction
        fake_json = {
            "epc_contractor": "McCarthy Building Companies",
            "project_name": "Lone Star Solar",
            "mw_capacity": 200.0,
            "developer": "NextEra Energy",
            "announcement_date": "2025-06-15",
            "source_confidence": "high",
            "key_quote": "McCarthy selected as EPC for the 200MW project",
        }
        fake_response = SimpleNamespace(
            data=SimpleNamespace(json=fake_json)
        )

        mock_scrape = AsyncMock(return_value=fake_response)

        class FakeFirecrawl:
            def __init__(self, api_key):
                self.api_key = api_key
                self.scrape = mock_scrape

        # Inject the fake class as the firecrawl module
        fake_module = SimpleNamespace(AsyncFirecrawl=FakeFirecrawl)
        with patch.dict(sys.modules, {"firecrawl": fake_module}):
            result = await execute({"url": "https://example.com/pr"})

        assert "error" not in result
        assert result["extracted"]["epc_contractor"] == "McCarthy Building Companies"
        assert result["extracted"]["mw_capacity"] == 200.0
        assert result["source_tool"] == "firecrawl_extract"
        mock_scrape.assert_called_once()

    async def test_sdk_raises_exception(self, monkeypatch):
        """Network / API errors wrap into a structured error dict."""
        from src.tools.firecrawl_extract import execute

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")

        class FakeFirecrawl:
            def __init__(self, api_key):
                self.scrape = AsyncMock(side_effect=RuntimeError("network down"))

        fake_module = SimpleNamespace(AsyncFirecrawl=FakeFirecrawl)
        with patch.dict(sys.modules, {"firecrawl": fake_module}):
            result = await execute({"url": "https://example.com/pr"})

        assert "error" in result
        assert "network down" in result["error"]

    async def test_dict_shaped_response(self, monkeypatch):
        """Some SDK versions return dicts instead of objects — handle both."""
        from src.tools.firecrawl_extract import execute

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")

        # Dict-shaped response
        dict_response = {
            "data": {
                "json": {
                    "epc_contractor": "Mortenson",
                    "mw_capacity": 150.0,
                    "source_confidence": "medium",
                }
            }
        }

        class FakeFirecrawl:
            def __init__(self, api_key):
                self.scrape = AsyncMock(return_value=dict_response)

        fake_module = SimpleNamespace(AsyncFirecrawl=FakeFirecrawl)
        with patch.dict(sys.modules, {"firecrawl": fake_module}):
            result = await execute({"url": "https://example.com/pr"})

        assert "error" not in result
        assert result["extracted"]["epc_contractor"] == "Mortenson"


# ---------------------------------------------------------------------------
# Evidence extraction mapping
# ---------------------------------------------------------------------------


class TestFirecrawlEvidenceMapping:
    def test_high_confidence_extraction_becomes_high_reliability_finding(self):
        store = EvidenceStore()
        result = {
            "url": "https://example.com/pr",
            "extracted": {
                "epc_contractor": "McCarthy Building Companies",
                "project_name": "Lone Star Solar",
                "mw_capacity": 200.0,
                "developer": "NextEra Energy",
                "announcement_date": "2025-06-15",
                "source_confidence": "high",
                "key_quote": "McCarthy selected as EPC",
            },
            "source_tool": "firecrawl_extract",
        }

        extract_findings_from_tool_result(
            "firecrawl_extract",
            {"url": "https://example.com/pr"},
            result,
            store,
            iteration=1,
        )

        assert len(store.findings) == 1
        f: Finding = store.findings[0]
        assert f.source_tool == "firecrawl_extract"
        assert f.reliability == "high"
        assert "McCarthy" in f.text
        assert "200" in f.text and "MW" in f.text
        assert "NextEra Energy" in f.text
        assert f.source_url == "https://example.com/pr"

    def test_medium_confidence_default(self):
        store = EvidenceStore()
        result = {
            "url": "https://example.com/portfolio",
            "extracted": {
                "epc_contractor": "Some EPC",
                "source_confidence": "medium",
            },
        }

        extract_findings_from_tool_result(
            "firecrawl_extract",
            {"url": "https://example.com/portfolio"},
            result,
            store,
        )
        assert store.findings[0].reliability == "medium"

    def test_missing_confidence_defaults_to_medium(self):
        store = EvidenceStore()
        result = {
            "url": "https://example.com/x",
            "extracted": {"epc_contractor": "X", "source_confidence": "invalid_value"},
        }
        extract_findings_from_tool_result(
            "firecrawl_extract",
            {"url": "https://example.com/x"},
            result,
            store,
        )
        assert store.findings[0].reliability == "medium"

    def test_empty_extraction_skipped(self):
        store = EvidenceStore()
        result = {"url": "https://example.com/empty", "extracted": {}}
        extract_findings_from_tool_result(
            "firecrawl_extract",
            {"url": "https://example.com/empty"},
            result,
            store,
        )
        assert len(store.findings) == 0

    def test_error_result_skipped(self):
        store = EvidenceStore()
        result = {"error": "FIRECRAWL_API_KEY not set"}
        extract_findings_from_tool_result(
            "firecrawl_extract",
            {"url": "https://example.com/x"},
            result,
            store,
        )
        assert len(store.findings) == 0


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestFirecrawlRegistration:
    def test_tool_is_registered(self):
        from src.tools import get_tool_names

        assert "firecrawl_extract" in get_tool_names()

    def test_tool_in_research_tools(self):
        from src.research import RESEARCH_TOOLS

        assert "firecrawl_extract" in RESEARCH_TOOLS
