"""Tests for fetch_page EPC keyword extraction."""

from __future__ import annotations

import pytest

from src.tools.fetch_page import _extract_relevant_sections, _MAX_CHARS, _EPC_KEYWORDS


class TestExtractRelevantSections:
    def test_returns_only_keyword_paragraphs(self):
        """Article with EPC keywords in 2/8 paragraphs -> returns only those 2."""
        paragraphs = [
            "The weather was nice on Tuesday.",
            "Local officials met to discuss zoning.",
            "McCarthy Building was awarded the EPC contract for a 200MW solar farm.",
            "Stock markets closed higher on Friday.",
            "The project will reach commercial operation date by Q4 2026.",
            "A new restaurant opened downtown.",
            "City council approved the budget.",
            "Traffic was diverted due to road work.",
        ]
        text = "\n\n".join(paragraphs)
        result = _extract_relevant_sections(text)

        assert "McCarthy Building" in result
        assert "commercial operation" in result
        assert "weather was nice" not in result
        assert "restaurant opened" not in result

    def test_zero_keywords_falls_back_to_truncation(self):
        """Article with zero EPC keywords -> falls back to head truncation."""
        filler = "This paragraph is about cooking recipes and nothing else."
        paragraphs = [filler] * 100
        text = "\n\n".join(paragraphs)
        assert len(text) > _MAX_CHARS

        result = _extract_relevant_sections(text)

        assert result.endswith("[... truncated]")
        assert len(result) <= _MAX_CHARS + 50

    def test_short_text_with_no_keywords_returned_as_is(self):
        """Short article with no keywords, under _MAX_CHARS -> returned as-is."""
        text = "This is a short unrelated article.\n\nNothing to see here."
        result = _extract_relevant_sections(text)
        assert result == text

    def test_empty_text_returns_empty(self):
        """Empty text -> returns empty string."""
        assert _extract_relevant_sections("") == ""

    def test_keyword_matching_is_case_insensitive(self):
        """Keywords match regardless of case."""
        text = "BLATTNER ENERGY awarded SOLAR EPC contract.\n\nUnrelated paragraph about gardening."
        result = _extract_relevant_sections(text)
        assert "BLATTNER" in result

    def test_result_capped_at_max_chars(self):
        """Even if many paragraphs match, result is capped at _MAX_CHARS."""
        para = "McCarthy was awarded the EPC contract for a 500MW solar farm near Austin."
        paragraphs = [para] * 200
        text = "\n\n".join(paragraphs)

        result = _extract_relevant_sections(text)
        assert len(result) <= _MAX_CHARS + 50
        assert result.endswith("[... truncated]")

    def test_preserves_paragraph_order(self):
        """Relevant paragraphs appear in original order."""
        text = (
            "Filler paragraph one.\n\n"
            "Primoris was named EPC for Phase 1.\n\n"
            "Another filler paragraph.\n\n"
            "Rosendin will handle the electrical construction scope.\n\n"
            "Final filler."
        )
        result = _extract_relevant_sections(text)
        assert result.index("Primoris") < result.index("Rosendin")

    def test_header_shows_extraction_counts(self):
        """Result includes a header with extraction counts."""
        paragraphs = [
            "Unrelated content here.",
            "Blattner was selected as the EPC contractor.",
            "More unrelated content.",
        ]
        text = "\n\n".join(paragraphs)
        result = _extract_relevant_sections(text)
        assert "[Extracted 1/3 paragraphs matching EPC keywords]" in result

    def test_known_epc_companies_in_keywords(self):
        """All specified EPC company names are in the keyword set."""
        expected = [
            "blattner", "mccarthy", "mortenson", "primoris",
            "rosendin", "swinerton", "mas energy", "signal energy",
            "strata solar", "sunpin solar",
        ]
        for name in expected:
            assert name in _EPC_KEYWORDS, f"{name} missing from _EPC_KEYWORDS"
