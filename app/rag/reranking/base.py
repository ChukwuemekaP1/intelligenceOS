"""Base reranker interface for candidate refinement."""

from abc import ABC, abstractmethod

from app.schemas.rag import RetrievedChunk


class BaseReranker(ABC):
    """Abstract interface for candidate reranking."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Reranks initial retrieved candidates and returns the top_k most relevant chunks.

        Args:
            query: The user's search query.
            candidates: Initial retrieval candidate chunks.
            top_k: Number of final context candidates to return.

        Returns:
            Refined and ordered list of RetrievedChunk instances.
        """
        pass
