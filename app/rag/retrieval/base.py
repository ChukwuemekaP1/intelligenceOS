"""Base retriever interface for RAG candidate retrieval."""

import uuid
from abc import ABC, abstractmethod

from app.schemas.rag import RetrievedChunk


class BaseRetriever(ABC):
    """Abstract interface for candidate retrieval components.

    Enforces mandatory tenant workspace isolation on every retrieval request.
    """

    @abstractmethod
    async def retrieve(
        self,
        workspace_id: uuid.UUID,
        query: str,
        top_k: int = 20,
        similarity_threshold: float | None = None,
        source_ids: list[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieves candidates strictly belonging to workspace_id.

        Args:
            workspace_id: Mandatory tenant workspace UUID.
            query: User search query string.
            top_k: Maximum candidate count to retrieve.
            similarity_threshold: Optional minimum similarity threshold.
            source_ids: Optional list of source UUIDs to narrow retrieval scope.

        Returns:
            List of RetrievedChunk candidates ordered by relevance score descending.
        """
        pass
