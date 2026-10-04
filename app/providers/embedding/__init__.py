"""Embedding provider abstraction package for IntelligenceOS."""

from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingInvalidRequestError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingServiceUnavailableError,
)
from app.providers.embedding.factory import get_embedding_provider, reset_embedding_provider
from app.providers.embedding.gemini import GeminiEmbeddingProvider
from app.providers.embedding.mock import MockEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingAuthenticationError",
    "EmbeddingRateLimitError",
    "EmbeddingInvalidRequestError",
    "EmbeddingServiceUnavailableError",
    "GeminiEmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
    "reset_embedding_provider",
]
