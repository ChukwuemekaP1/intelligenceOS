"""Abstract Base Class for Embedding Providers.

Provides an isolated interface for generating vector embeddings from text strings,
mirroring the LLM provider pattern from Phase 1.
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The dimensionality of vectors produced by this provider (e.g., 768)."""
        pass

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generates embedding vectors for a batch of text documents.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of float vectors, where len(vector) == self.dimension.

        Raises:
            EmbeddingAuthenticationError: If API credentials are invalid.
            EmbeddingRateLimitError: If provider rate limits are exceeded.
            EmbeddingInvalidRequestError: If input texts are malformed.
            EmbeddingServiceUnavailableError: If provider cannot be reached.
            EmbeddingProviderError: On any other downstream provider error.
        """
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generates an embedding vector for a single query string.

        Args:
            text: Query string to embed.

        Returns:
            Float vector of length self.dimension.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifies downstream provider availability and credentials validity."""
        pass
