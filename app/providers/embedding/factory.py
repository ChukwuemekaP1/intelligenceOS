"""Factory for resolving the configured embedding provider."""

from app.core.config import Settings, get_settings
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.gemini import GeminiEmbeddingProvider
from app.providers.embedding.mock import MockEmbeddingProvider

_embedding_provider_instance: EmbeddingProvider | None = None


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Returns the singleton instance of the configured EmbeddingProvider."""
    global _embedding_provider_instance
    if _embedding_provider_instance is not None:
        return _embedding_provider_instance

    if settings is None:
        settings = get_settings()

    if settings.EMBEDDING_PROVIDER == "mock":
        _embedding_provider_instance = MockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    else:
        api_key_val = (
            settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
        )
        _embedding_provider_instance = GeminiEmbeddingProvider(
            api_key=api_key_val,
            model=settings.GEMINI_EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    return _embedding_provider_instance


def reset_embedding_provider() -> None:
    """Resets the singleton embedding provider instance (used in test fixtures)."""
    global _embedding_provider_instance
    _embedding_provider_instance = None
