"""Abstract Base Class for Vector Storage providers.

Enforces workspace isolation by requiring explicit workspace_id parameters across all operations.
"""

import uuid
from abc import ABC, abstractmethod

from app.vectorstore.models import VectorPoint


class VectorStoreError(Exception):
    """Base exception for vector database operations."""

    pass


class VectorStore(ABC):
    """Interface abstraction for vector databases (Qdrant).

    All operations enforce tenant isolation at the service design layer.
    """

    @abstractmethod
    async def ensure_collection(self) -> None:
        """Verifies or provisions the underlying collection and payload indexes."""
        pass

    @abstractmethod
    async def upsert_points(
        self,
        workspace_id: uuid.UUID,
        points: list[VectorPoint],
    ) -> None:
        """Upserts vector points into the store, guaranteeing all points belong to workspace_id.

        Args:
            workspace_id: The tenant workspace UUID.
            points: List of VectorPoints with embeddings and metadata payloads.

        Raises:
            VectorStoreError: If tenant validation fails or database error occurs.
        """
        pass

    @abstractmethod
    async def delete_by_document_version(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> None:
        """Deletes all vector points associated with a document version in the workspace.

        Args:
            workspace_id: The tenant workspace UUID.
            document_version_id: The version UUID whose points should be removed.
        """
        pass

    @abstractmethod
    async def delete_by_source(
        self,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> None:
        """Deletes all vector points originating from a specific source within the workspace.

        Args:
            workspace_id: The tenant workspace UUID.
            source_id: The source UUID whose points should be removed.
        """
        pass

    @abstractmethod
    async def count_points(self, workspace_id: uuid.UUID) -> int:
        """Returns the total number of vector points belonging to the workspace.

        Args:
            workspace_id: The tenant workspace UUID.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Checks connectivity and operational readiness of the vector store."""
        pass
