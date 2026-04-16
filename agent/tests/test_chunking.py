"""Tests for the chunk_text recursive character splitter."""

from __future__ import annotations

import pytest

from src.chunking import chunk_text


def test_empty_text_returns_empty():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty():
    assert chunk_text("   ") == []
    assert chunk_text("\n\n\n") == []


def test_short_text_returns_single_chunk():
    text = "Short text that fits in one chunk."
    result = chunk_text(text, chunk_size=1000)
    assert result == [text]


def test_splits_on_double_newline():
    part_a = "First paragraph with enough text to matter."
    part_b = "Second paragraph with enough text to matter."
    text = part_a + "\n\n" + part_b
    result = chunk_text(text, chunk_size=60, overlap=0)
    # Both parts should appear across the chunks
    joined = " ".join(result)
    assert "First paragraph" in joined
    assert "Second paragraph" in joined
    # Should produce more than one chunk
    assert len(result) > 1


def test_splits_on_newline_when_no_double():
    lines = ["Line one here.", "Line two here.", "Line three here.", "Line four here."]
    text = "\n".join(lines)
    result = chunk_text(text, chunk_size=30, overlap=0)
    assert len(result) > 1
    joined = " ".join(result)
    for line in lines:
        assert line.strip() in joined


def test_splits_on_sentence_boundary():
    # Build text without any newlines; force splits at ". "
    sentences = [
        "Alpha sentence goes here",
        "Beta sentence goes here",
        "Gamma sentence goes here",
        "Delta sentence goes here",
    ]
    text = ". ".join(sentences) + "."
    result = chunk_text(text, chunk_size=50, overlap=0)
    assert len(result) > 1
    joined = " ".join(result)
    for s in sentences:
        assert s in joined


def test_chunk_size_respected():
    text = "word " * 500  # 2500 chars
    chunk_size = 200
    overlap = 20
    result = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    assert len(result) > 1
    for chunk in result:
        # Allow chunks to exceed chunk_size only by the overlap amount
        assert len(chunk) <= chunk_size + overlap, (
            f"Chunk length {len(chunk)} exceeds {chunk_size + overlap}"
        )


def test_overlap_provides_continuity():
    # Create text with clear word boundaries so overlap is deterministic
    words = [f"word{i:04d}" for i in range(200)]
    text = " ".join(words)
    overlap = 50
    result = chunk_text(text, chunk_size=200, overlap=overlap)
    assert len(result) > 1
    for i in range(1, len(result)):
        tail = result[i - 1][-overlap:]
        assert result[i].startswith(tail), (
            f"Chunk {i} does not start with tail of chunk {i - 1}.\n"
            f"Expected start: {tail!r}\n"
            f"Actual start:   {result[i][:overlap]!r}"
        )


def test_very_long_text():
    # 10,000 character text
    text = ("The quick brown fox jumps over the lazy dog. " * 230)[:10000]
    chunk_size = 500
    overlap = 50
    result = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= chunk_size + overlap, (
            f"Chunk length {len(chunk)} exceeds {chunk_size + overlap}"
        )
    # Rough content coverage: joined result should be at least as long as original
    # (overlap adds bytes, so joined > original is expected)
    assert sum(len(c) for c in result) >= len(text)
