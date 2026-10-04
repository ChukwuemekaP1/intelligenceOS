"""Mock Embedding Provider for offline development and fast testing."""

import hashlib
import math

from app.providers.embedding.base import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """Generates deterministic, unit-normalized pseudo-embeddings based on text hashing.

    Guarantees reproducible vectors for testing without making external network calls.
    """

    def __init__(self, dimension: int = 768) -> None:
        self._dimension = dimension
        self._is_healthy = True

    @property
    def dimension(self) -> int:
        return self._dimension

    def set_healthy(self, healthy: bool) -> None:
        """Allows test suites to simulate downstream embedding provider downtime."""
        self._is_healthy = healthy

    def _generate_vector(self, text: str) -> list[float]:
        """Generates a deterministic float vector from text hash and normalizes to unit length."""
        # Use SHA-256 hash as seed to deterministically generate floats
        seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []

        for i in range(self._dimension):
            byte_val = seed_bytes[i % len(seed_bytes)]
            val = (float(byte_val) / 255.0) * 2.0 - 1.0 + (float(i) / float(self._dimension))
            vector.append(val)

        # L2-normalize vector for cosine similarity
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [round(x / norm, 6) for x in vector]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def health_check(self) -> bool:
        return self._is_healthy
