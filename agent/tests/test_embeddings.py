"""Tests for the EmbeddingProvider and cosine_similarity helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_response(vectors: list[list[float]]) -> SimpleNamespace:
    fake_embeddings = [SimpleNamespace(embedding=v) for v in vectors]
    return SimpleNamespace(data=fake_embeddings)


def _make_mock_client(vectors: list[list[float]]) -> MagicMock:
    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(return_value=_make_fake_response(vectors))
    return mock_client


# ---------------------------------------------------------------------------
# EmbeddingProvider tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_returns_vectors():
    from src.embeddings import EmbeddingProvider

    provider = EmbeddingProvider(api_key="fake-key")
    mock_client = _make_mock_client([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        provider._client = mock_client
        result = await provider.embed(["hello", "world"])

    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    assert result[1] == [0.4, 0.5, 0.6]


@pytest.mark.asyncio
async def test_embed_one_returns_single_vector():
    from src.embeddings import EmbeddingProvider

    provider = EmbeddingProvider(api_key="fake-key")
    mock_client = _make_mock_client([[0.7, 0.8, 0.9]])

    provider._client = mock_client
    result = await provider.embed_one("single text")

    assert result == [0.7, 0.8, 0.9]
    mock_client.embeddings.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_empty_list_returns_empty():
    from src.embeddings import EmbeddingProvider

    provider = EmbeddingProvider(api_key="fake-key")
    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock()
    provider._client = mock_client

    result = await provider.embed([])

    assert result == []
    mock_client.embeddings.create.assert_not_awaited()


def test_lazy_init_no_key_at_import():
    """EmbeddingProvider can be constructed without a key — only fails at embed time."""
    from src.embeddings import EmbeddingProvider

    # Should not raise
    provider = EmbeddingProvider()
    assert provider._client is None


# ---------------------------------------------------------------------------
# cosine_similarity tests
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical():
    from src.embeddings import cosine_similarity

    result = cosine_similarity([1.0, 0.0], [1.0, 0.0])
    assert abs(result - 1.0) < 1e-9


def test_cosine_similarity_orthogonal():
    from src.embeddings import cosine_similarity

    result = cosine_similarity([1.0, 0.0], [0.0, 1.0])
    assert abs(result - 0.0) < 1e-9


def test_cosine_similarity_opposite():
    from src.embeddings import cosine_similarity

    result = cosine_similarity([1.0, 0.0], [-1.0, 0.0])
    assert abs(result - (-1.0)) < 1e-9


def test_cosine_similarity_zero_vector():
    from src.embeddings import cosine_similarity

    result = cosine_similarity([0.0, 0.0], [1.0, 0.0])
    assert result == 0.0
