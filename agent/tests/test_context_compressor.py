"""Tests for ContextCompressor — embedding-based relevance filtering."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.context_compressor import ContextCompressor, FAST_PATH_CHAR_THRESHOLD
from src.embeddings import EmbeddingProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_compressor(threshold: float = 0.42) -> ContextCompressor:
    """Return a ContextCompressor backed by a real (but un-inited) provider."""
    provider = EmbeddingProvider(api_key="fake-key")
    return ContextCompressor(embedding_provider=provider, similarity_threshold=threshold)


def make_doc(url: str, text: str) -> dict:
    return {"url": url, "text": text}


def small_docs(n: int = 2, chars_each: int = 100) -> list[dict]:
    """Create n docs whose total chars stay under the fast-path threshold."""
    return [make_doc(f"https://example.com/{i}", "x" * chars_each) for i in range(n)]


def large_doc_list(total_chars: int = FAST_PATH_CHAR_THRESHOLD + 1) -> list[dict]:
    """One big doc that forces the standard embedding path."""
    return [make_doc("https://big.com/1", "word " * (total_chars // 5))]


# ---------------------------------------------------------------------------
# 1. Fast path: small content → embedding never called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fast_path_small_content():
    compressor = make_compressor()
    docs = small_docs(n=2, chars_each=100)  # total 200 chars, well under 8000

    with patch.object(compressor.embeddings, "embed", new_callable=AsyncMock) as mock_embed:
        result = await compressor.filter(docs, "solar EPC contractor", max_results=10)

    mock_embed.assert_not_called()
    assert len(result) == 2
    assert all(r["score"] == 1.0 for r in result)
    assert {r["url"] for r in result} == {
        "https://example.com/0",
        "https://example.com/1",
    }


# ---------------------------------------------------------------------------
# 2. Fast path skipped for large content → embedding IS called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fast_path_skipped_for_large_content():
    compressor = make_compressor()
    docs = large_doc_list()

    # Provide enough vectors: query + however many chunks the big doc produces.
    # We use a side_effect that returns a list of all-zero vectors of the right length.
    async def fake_embed(texts):
        # High-similarity for all chunks: query=[1,0,0], chunks=[1,0,0]
        return [[1.0, 0.0, 0.0]] * len(texts)

    with patch.object(compressor.embeddings, "embed", side_effect=fake_embed) as mock_embed:
        await compressor.filter(docs, "solar farm", max_results=5)

    mock_embed.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Standard path filters by threshold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_standard_path_filters_by_threshold():
    """Only chunks with cosine >= 0.42 are returned."""
    compressor = make_compressor(threshold=0.42)

    # 5 docs, each large enough to avoid fast path individually, combined > 8000 chars
    docs = [make_doc(f"https://example.com/{i}", "solar EPC layout " * 200) for i in range(5)]

    # Query vector: [1, 0, 0]
    # Chunks 0,1 → high similarity vectors: [0.9, 0.1, 0.0]  (cosine ≈ 0.994)
    # Chunks 2,3,4 → low similarity vectors: [0.0, 1.0, 0.0]  (cosine = 0.0)
    query_vec = [1.0, 0.0, 0.0]
    high_vec = [0.9, 0.1, 0.0]
    low_vec = [0.0, 1.0, 0.0]

    async def fake_embed(texts):
        # texts[0] = query, rest = chunks (one per doc after chunking)
        n_chunks = len(texts) - 1
        # First two source docs → high relevance; rest → low
        chunk_vecs = []
        for i in range(n_chunks):
            chunk_vecs.append(high_vec if i < 2 else low_vec)
        return [query_vec] + chunk_vecs

    with patch.object(compressor.embeddings, "embed", side_effect=fake_embed):
        result = await compressor.filter(docs, "solar EPC contractor", max_results=10)

    # Only the first 2 chunks should survive the threshold
    assert len(result) == 2
    for r in result:
        assert r["score"] >= 0.42


# ---------------------------------------------------------------------------
# 4. Empty documents → []
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_documents():
    compressor = make_compressor()
    result = await compressor.filter([], "solar EPC")
    assert result == []


# ---------------------------------------------------------------------------
# 5. Empty query → []
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_query():
    compressor = make_compressor()
    docs = small_docs(n=2)
    result = await compressor.filter(docs, "")
    assert result == []


# ---------------------------------------------------------------------------
# 6. max_results limits output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_results_limits_output():
    """10 high-scoring chunks but max_results=3 → only top 3 returned."""
    compressor = make_compressor(threshold=0.42)

    # 10 large docs so we stay on the standard path
    docs = [make_doc(f"https://example.com/{i}", "solar farm layout robot " * 200) for i in range(10)]

    query_vec = [1.0, 0.0, 0.0]
    # Slightly varying scores so we can verify ordering
    chunk_vecs_template = []
    for i in range(10):
        # Score decreases from ~0.99 for i=0 to ~0.50 for i=9
        a = 1.0 - i * 0.05
        b = (1.0 - a ** 2) ** 0.5
        chunk_vecs_template.append([a, b, 0.0])

    async def fake_embed(texts):
        n_chunks = len(texts) - 1
        vecs = []
        for i in range(n_chunks):
            vecs.append(chunk_vecs_template[i % len(chunk_vecs_template)])
        return [query_vec] + vecs

    with patch.object(compressor.embeddings, "embed", side_effect=fake_embed):
        result = await compressor.filter(docs, "solar EPC", max_results=3)

    assert len(result) == 3
    # Should be sorted descending by score
    scores = [r["score"] for r in result]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# 7. Embedding failure → fallback with score=0.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embedding_failure_fallback():
    compressor = make_compressor()
    docs = large_doc_list()

    async def raise_error(texts):
        raise RuntimeError("OpenAI API unavailable")

    with patch.object(compressor.embeddings, "embed", side_effect=raise_error):
        result = await compressor.filter(docs, "solar farm", max_results=3)

    assert len(result) <= 3
    assert all(r["score"] == 0.0 for r in result)


# ---------------------------------------------------------------------------
# 8. Chunks carry the source URL of their parent document
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chunks_carry_source_url():
    compressor = make_compressor(threshold=0.0)  # accept everything

    url_a = "https://alpha.com/page"
    url_b = "https://beta.com/page"
    # Make total > 8000 chars to force standard path
    text = "solar EPC robot layout " * 200
    docs = [make_doc(url_a, text), make_doc(url_b, text)]

    async def fake_embed(texts):
        return [[1.0, 0.0, 0.0]] * len(texts)

    with patch.object(compressor.embeddings, "embed", side_effect=fake_embed):
        result = await compressor.filter(docs, "solar", max_results=50)

    returned_urls = {r["url"] for r in result}
    assert url_a in returned_urls
    assert url_b in returned_urls


# ---------------------------------------------------------------------------
# 9. Documents with empty text are skipped in both paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_text_documents_skipped():
    compressor = make_compressor()

    # Fast path: mix of empty and non-empty, total still small
    docs_small = [
        make_doc("https://example.com/empty", ""),
        make_doc("https://example.com/whitespace", "   "),
        make_doc("https://example.com/valid", "x" * 50),
    ]

    with patch.object(compressor.embeddings, "embed", new_callable=AsyncMock) as mock_embed:
        result = await compressor.filter(docs_small, "solar EPC", max_results=10)

    mock_embed.assert_not_called()  # still in fast path
    assert len(result) == 1
    assert result[0]["url"] == "https://example.com/valid"

    # Standard path: empty docs should produce no chunks
    docs_large = [
        make_doc("https://example.com/empty-big", ""),
        make_doc("https://example.com/real", "solar farm layout robot EPC " * 300),
    ]

    async def fake_embed(texts):
        return [[1.0, 0.0, 0.0]] * len(texts)

    with patch.object(compressor.embeddings, "embed", side_effect=fake_embed):
        result2 = await compressor.filter(docs_large, "solar", max_results=10)

    # Only chunks from the non-empty doc should appear
    assert all(r["url"] == "https://example.com/real" for r in result2)
