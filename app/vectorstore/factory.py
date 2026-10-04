"""Factory for resolving the configured VectorStore."""

from app.core.config import Settings, get_settings
from app.vectorstore.base import VectorStore
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.qdrant import QdrantVectorStore

_vector_store_instance: VectorStore | None = None


def get_vector_store(settings: Settings | None = None) -> VectorStore:
    """Returns the singleton instance of the configured VectorStore."""
    global _vector_store_instance
    if _vector_store_instance is not None:
        return _vector_store_instance

    if settings is None:
        settings = get_settings()

    if settings.ENVIRONMENT == "testing":
        _vector_store_instance = MockVectorStore()
    else:
        _vector_store_instance = QdrantVectorStore(settings=settings)

    return _vector_store_instance


def reset_vector_store() -> None:
    """Resets the singleton vector store instance (used in test fixtures)."""
    global _vector_store_instance
    _vector_store_instance = None
