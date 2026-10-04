"""Tests for Embedding Provider Abstraction (Mock & Gemini)."""

import math

import pytest

from app.core.config import Settings
from app.providers.embedding.exceptions import EmbeddingAuthenticationError
from app.providers.embedding.factory import get_embedding_provider, reset_embedding_provider
from app.providers.embedding.gemini import GeminiEmbeddingProvider
from app.providers.embedding.mock import MockEmbeddingProvider


@pytest.mark.asyncio
async def test_mock_embedding_provider_properties() -> None:
    """Verifies that MockEmbeddingProvider generates normalized, deterministic vectors."""
    provider = MockEmbeddingProvider(dimension=768)
    assert provider.dimension == 768

    texts = [
        "IntelligenceOS foundation and knowledge ingestion pipeline.",
        "Deterministic vector embeddings for semantic search.",
    ]

    embeddings = await provider.embed_texts(texts)
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 768
    assert len(embeddings[1]) == 768

    # Verify unit-length normalization (L2 norm should be approximately 1.0)
    norm = math.sqrt(sum(x * x for x in embeddings[0]))
    assert pytest.approx(norm, rel=1e-2) == 1.0

    # Verify determinism: same input text produces identical vector
    repeat_embeddings = await provider.embed_texts([texts[0]])
    assert embeddings[0] == repeat_embeddings[0]

    # Verify query embedding
    query_vec = await provider.embed_query("Query test")
    assert len(query_vec) == 768

    # Verify health check
    assert await provider.health_check() is True
    provider.set_healthy(False)
    assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_gemini_embedding_provider_missing_key() -> None:
    """Verifies that GeminiEmbeddingProvider raises error when unconfigured."""
    provider = GeminiEmbeddingProvider(api_key=None)
    with pytest.raises(EmbeddingAuthenticationError, match="Gemini API key is not configured"):
        await provider.embed_texts(["sample text"])


def test_embedding_factory() -> None:
    """Verifies that get_embedding_provider resolves correctly from settings."""
    reset_embedding_provider()
    mock_settings = Settings(EMBEDDING_PROVIDER="mock", EMBEDDING_DIMENSION=512)
    provider = get_embedding_provider(mock_settings)
    assert isinstance(provider, MockEmbeddingProvider)
    assert provider.dimension == 512
    reset_embedding_provider()
