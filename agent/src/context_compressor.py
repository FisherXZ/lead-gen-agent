"""Embedding-based context compressor for filtering scraped content.

Takes raw documents (URL + text), chunks them, embeds both chunks and
the query, and returns only chunks that exceed a cosine similarity
threshold. Includes a fast-path optimization that skips embedding when
total content is small.

Pattern adapted from GPT-Researcher's ContextCompressor:
- chunk_size=1000, overlap=100
- similarity_threshold=0.42
- fast path: skip when total chars < 8000 AND doc count <= max_results
"""

from __future__ import annotations

import logging

from .chunking import chunk_text
from .embeddings import EmbeddingProvider, cosine_similarity

logger = logging.getLogger(__name__)

# GPT-Researcher defaults
DEFAULT_SIMILARITY_THRESHOLD = 0.42
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 100
FAST_PATH_CHAR_THRESHOLD = 8000


class ContextCompressor:
    """Filter scraped documents by semantic relevance to a query."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.embeddings = embedding_provider
        self.threshold = similarity_threshold
        self.chunk_size = chunk_size
        self.overlap = overlap

    async def filter(
        self,
        documents: list[dict],  # [{"url": str, "text": str}]
        query: str,
        max_results: int = 10,
    ) -> list[dict]:
        """Return top-K relevant chunks from documents.

        Fast path: if total content < 8000 chars AND doc count <= max_results,
        return documents directly without embedding (content is already concise enough).

        Standard path: chunk -> embed -> cosine filter -> sort -> top-K.

        Returns: [{"url": str, "text": str, "score": float}]
        """
        if not documents or not query:
            return []

        # Fast path: small content set, skip expensive embedding
        total_chars = sum(len(d.get("text", "")) for d in documents)
        if total_chars < FAST_PATH_CHAR_THRESHOLD and len(documents) <= max_results:
            logger.debug(
                "Fast path: %d chars < %d threshold, skipping embedding",
                total_chars,
                FAST_PATH_CHAR_THRESHOLD,
            )
            return [
                {"url": d.get("url", ""), "text": d.get("text", ""), "score": 1.0}
                for d in documents
                if d.get("text", "").strip()
            ]

        # Standard path: chunk all documents
        all_chunks: list[dict] = []  # {"url": str, "text": str}
        for doc in documents:
            url = doc.get("url", "")
            text = doc.get("text", "")
            if not text.strip():
                continue
            chunks = chunk_text(text, self.chunk_size, self.overlap)
            for chunk in chunks:
                all_chunks.append({"url": url, "text": chunk})

        if not all_chunks:
            return []

        # Embed query + all chunks in one batch
        texts_to_embed = [query] + [c["text"] for c in all_chunks]
        try:
            embeddings = await self.embeddings.embed(texts_to_embed)
        except Exception as e:
            logger.warning("Embedding failed, returning unfiltered chunks: %s", e)
            # Fallback: return first max_results chunks unscored
            return [
                {"url": c["url"], "text": c["text"], "score": 0.0}
                for c in all_chunks[:max_results]
            ]

        query_vec = embeddings[0]
        chunk_vecs = embeddings[1:]

        # Score each chunk
        scored = []
        for i, chunk in enumerate(all_chunks):
            score = cosine_similarity(query_vec, chunk_vecs[i])
            if score >= self.threshold:
                scored.append(
                    {"url": chunk["url"], "text": chunk["text"], "score": score}
                )

        # Sort by score descending, return top-K
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:max_results]
