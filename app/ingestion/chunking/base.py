"""Abstract Base Class for text chunkers."""

import uuid
from abc import ABC, abstractmethod

from app.ingestion.chunking.models import ChunkData
from app.ingestion.models import NormalizedDocument


class BaseChunker(ABC):
    """Interface for chunking normalized documents into indexed chunks."""

    @abstractmethod
    def chunk(
        self,
        document: NormalizedDocument,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> list[ChunkData]:
        """Splits a NormalizedDocument into deterministic chunks with traceability metadata.

        Args:
            document: The normalized document representation.
            workspace_id: The tenant workspace ID.
            source_id: The source container ID.
            document_id: The logical document ID.
            document_version_id: The specific document version snapshot ID.

        Returns:
            List of ChunkData ready for embedding and storage.
        """
        pass
