"""Tests for Finding and ReflectionResult models (research v2)."""

from src.models import Finding, ReflectionResult


class TestFinding:
    def test_creation(self):
        f = Finding(
            text="McCarthy Building Companies selected as EPC for 200MW project",
            source_url="https://example.com/article",
            source_tool="tavily_search",
            reliability="high",
            iteration=1,
        )
        assert f.text.startswith("McCarthy")
        assert f.source_tool == "tavily_search"
        assert f.reliability == "high"
        assert f.iteration == 1

    def test_defaults(self):
        f = Finding(
            text="some info",
            source_url="https://x.com",
            source_tool="web_search",
        )
        assert f.reliability == "medium"
        assert f.iteration == 0

    def test_serialization_roundtrip(self):
        f = Finding(
            text="OSHA record at site",
            source_url="https://osha.gov/record/123",
            source_tool="osha_inspection",
            reliability="high",
            iteration=3,
        )
        data = f.model_dump()
        f2 = Finding(**data)
        assert f2 == f


class TestReflectionResult:
    def test_creation(self):
        r = ReflectionResult(
            summary="Found McCarthy as likely EPC from press release",
            gaps=["No second independent source", "Need to verify scale"],
            should_continue=True,
            next_search_topic="McCarthy Building Companies solar portfolio MW",
        )
        assert r.should_continue is True
        assert len(r.gaps) == 2
        assert r.next_search_topic.startswith("McCarthy")

    def test_stop_condition(self):
        r = ReflectionResult(
            summary="Confirmed EPC with 2 independent sources",
            gaps=[],
            should_continue=False,
        )
        assert r.should_continue is False
        assert r.next_search_topic is None

    def test_defaults(self):
        r = ReflectionResult(summary="Minimal result")
        assert r.gaps == []
        assert r.should_continue is True
        assert r.next_search_topic is None

    def test_serialization_roundtrip(self):
        r = ReflectionResult(
            summary="test",
            gaps=["gap1"],
            should_continue=True,
            next_search_topic="next query",
        )
        data = r.model_dump()
        r2 = ReflectionResult(**data)
        assert r2 == r
