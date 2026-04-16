"""OpenAI embedding provider for semantic similarity filtering.

Uses text-embedding-3-small ($0.02/1M tokens) — the cheapest, most
cost-effective embedding model for our context filtering needs.
"""

from __future__ import annotations

import logging
import math
import os

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")


class EmbeddingProvider:
    """Async OpenAI embedding client with batching."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.model = model or EMBEDDING_MODEL
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = None  # lazy init

    def _ensure_client(self):
        """Lazy-init the OpenAI client so we don't require key at import time."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package not installed. Run: pip install openai"
                )
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one API call. Returns list of vectors."""
        if not texts:
            return []
        client = self._ensure_client()
        response = await client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Convenience wrapper."""
        results = await self.embed([text])
        return results[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
