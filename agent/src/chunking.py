"""Recursive character text splitter for context compression.

Splits text into chunks of approximately chunk_size characters with
overlap. Splits on natural boundaries (double newlines, newlines,
periods, spaces) before falling back to character-level splits.

No external dependencies — pure stdlib.
"""

from __future__ import annotations


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> list[str]:
    """Split text into overlapping chunks on natural boundaries.

    Tries separators in order: \\n\\n, \\n, ". ", " ", "" (character).
    Each chunk is at most chunk_size characters. Adjacent chunks overlap
    by up to overlap characters for context continuity.

    Returns empty list if text is empty.
    """
    if not text or not text.strip():
        return []

    separators = ["\n\n", "\n", ". ", " ", ""]
    return _split_recursive(text, separators, chunk_size, overlap)


def _split_recursive(
    text: str,
    separators: list[str],
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Recursively split text using the best available separator."""
    if len(text) <= chunk_size:
        stripped = text.strip()
        return [stripped] if stripped else []

    # Find the best separator that actually exists in the text
    separator = ""
    for sep in separators:
        if sep == "":
            separator = ""
            break
        if sep in text:
            separator = sep
            break

    # Split on the chosen separator
    if separator:
        parts = text.split(separator)
    else:
        # Character-level split
        parts = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size - overlap)]
        return [p.strip() for p in parts if p.strip()]

    # Merge parts into chunks of ~chunk_size
    chunks = []
    current = ""
    for part in parts:
        candidate = current + separator + part if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current.strip():
                chunks.append(current.strip())
            current = part
            # If single part exceeds chunk_size, recursively split with next separator
            if len(current) > chunk_size:
                remaining_seps = separators[separators.index(separator) + 1 :]
                sub_chunks = _split_recursive(current, remaining_seps, chunk_size, overlap)
                chunks.extend(sub_chunks)
                current = ""
    if current.strip():
        chunks.append(current.strip())

    # Add overlap between adjacent chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:]
            overlapped.append(prev_tail + chunks[i])
        chunks = overlapped

    return chunks
