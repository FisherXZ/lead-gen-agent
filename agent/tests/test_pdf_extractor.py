"""Tests for PDF text extraction skill."""

import pymupdf

from src.skills.pdf.extractor import extract_text


def _make_pdf(pages: list[str]) -> bytes:
    """Create a minimal PDF with given page texts."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestExtractText:
    def test_single_page(self):
        pdf = _make_pdf(["Hello world"])
        result = extract_text(pdf)
        assert "Hello world" in result["text"]
        assert result["page_count"] == 1
        assert result["pages_extracted"] == 1

    def test_multi_page(self):
        pdf = _make_pdf(["Page one", "Page two", "Page three"])
        result = extract_text(pdf)
        assert "Page one" in result["text"]
        assert "Page three" in result["text"]
        assert result["page_count"] == 3
        assert result["pages_extracted"] == 3

    def test_max_pages_limit(self):
        pdf = _make_pdf([f"Page {i}" for i in range(10)])
        result = extract_text(pdf, max_pages=3)
        assert result["page_count"] == 10
        assert result["pages_extracted"] == 3
        assert "Page 0" in result["text"]
        assert "Page 2" in result["text"]
        # Page 3+ should not be extracted
        assert "Page 3" not in result["text"]

    def test_empty_page_skipped(self):
        doc = pymupdf.open()
        doc.new_page()  # empty page
        page2 = doc.new_page()
        page2.insert_text((72, 72), "Content here")
        pdf_bytes = doc.tobytes()
        doc.close()

        result = extract_text(pdf_bytes)
        assert result["page_count"] == 2
        # Empty page is skipped
        assert result["pages_extracted"] == 1
        assert "Content here" in result["text"]

    def test_epc_keywords_in_pdf(self):
        """Ensure EPC-relevant text survives extraction."""
        pdf = _make_pdf(
            ["McCarthy Building Companies awarded EPC contract for 200 MW solar project"]
        )
        result = extract_text(pdf)
        assert "McCarthy" in result["text"]
        assert "EPC" in result["text"]
