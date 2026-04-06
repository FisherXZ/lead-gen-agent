"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import (
    AgentResult,
    BatchDiscoverRequest,
    DiscoverRequest,
    EpcSource,
    ReviewRequest,
)

# -- DiscoverRequest ----------------------------------------------------------


class TestDiscoverRequest:
    def test_valid(self):
        req = DiscoverRequest(project_id="proj-001")
        assert req.project_id == "proj-001"

    def test_missing_project_id(self):
        with pytest.raises(ValidationError):
            DiscoverRequest()


# -- BatchDiscoverRequest -----------------------------------------------------


class TestBatchDiscoverRequest:
    def test_valid_single(self):
        req = BatchDiscoverRequest(project_ids=["proj-001"])
        assert req.project_ids == ["proj-001"]

    def test_valid_multiple(self):
        ids = ["proj-001", "proj-002", "proj-003"]
        req = BatchDiscoverRequest(project_ids=ids)
        assert len(req.project_ids) == 3

    def test_empty_list_is_valid_schema(self):
        # Schema allows it; endpoint validates non-empty
        req = BatchDiscoverRequest(project_ids=[])
        assert req.project_ids == []

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            BatchDiscoverRequest()


# -- ReviewRequest ------------------------------------------------------------


class TestReviewRequest:
    def test_accepted(self):
        req = ReviewRequest(action="accepted")
        assert req.action == "accepted"

    def test_rejected(self):
        req = ReviewRequest(action="rejected")
        assert req.action == "rejected"

    def test_arbitrary_string_allowed_by_schema(self):
        # The model is a plain str; endpoint validates valid values
        req = ReviewRequest(action="invalid")
        assert req.action == "invalid"


# -- EpcSource ----------------------------------------------------------------


class TestEpcSource:
    def test_required_fields(self):
        src = EpcSource(channel="trade_publication", excerpt="Some text")
        assert src.channel == "trade_publication"
        assert src.excerpt == "Some text"
        assert src.reliability == "medium"
        assert src.publication is None
        assert src.date is None
        assert src.url is None

    def test_all_fields(self):
        src = EpcSource(
            channel="news_article",
            publication="Reuters",
            date="2025-06-01",
            url="https://example.com",
            excerpt="EPC contract awarded",
            reliability="high",
        )
        assert src.publication == "Reuters"
        assert src.reliability == "high"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            EpcSource(channel="news_article")  # missing excerpt


# -- AgentResult --------------------------------------------------------------


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult()
        assert r.epc_contractor is None
        assert r.confidence == "unknown"
        assert r.sources == []
        assert r.reasoning == ""
        assert r.related_leads == []
        assert r.searches_performed == []

    def test_full(self):
        src = EpcSource(channel="web_search", excerpt="found it")
        r = AgentResult(
            epc_contractor="Blattner Energy",
            confidence="confirmed",
            sources=[src],
            reasoning="Two independent sources",
            related_leads=[{"developer": "X", "epc": "Y"}],
            searches_performed=["query 1", "query 2"],
        )
        assert r.epc_contractor == "Blattner Energy"
        assert len(r.sources) == 1
        assert r.sources[0].channel == "web_search"

    def test_model_dump_sources(self):
        src = EpcSource(channel="permit_filing", excerpt="permit text")
        r = AgentResult(sources=[src])
        dumped = r.sources[0].model_dump()
        assert dumped["channel"] == "permit_filing"
        assert dumped["reliability"] == "medium"
