"""Chunk model representing a discrete segment of text ready for vector search.

Chunks are stored in PostgreSQL for textual content and relational traceability,
while their high-dimensional vector embeddings are stored exclusively in Qdrant.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.document_version import DocumentVersion
    from app.models.workspace import Workspace


class Chunk(Base, TimestampMixin):
    """Represents a discrete indexed text chunk derived from a DocumentVersion.

    Note: As per architecture requirements, vector embeddings are NOT stored
    in PostgreSQL; they reside strictly inside Qdrant with synchronized IDs and metadata.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_chunks_version_index",
        ),
    )

    # Primary identifier (UUIDv4) - used as the Point ID in Qdrant
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Reference to parent DocumentVersion
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Workspace isolation key: ensures strict tenant separation
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Deterministic sequence index within the document version (0, 1, 2, ...)
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Raw extracted and normalized text content of this chunk
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Traceability metadata (page_number, source_type, source_id, document_id, word_count, etc.)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    # Relationships
    document_version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion",
        back_populates="chunks",
    )
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
    )

    @property
    def page_number(self) -> int | None:
        """Convenience property extracting page_number from chunk metadata."""
        if self.metadata_ and "page_number" in self.metadata_:
            val = self.metadata_["page_number"]
            return int(val) if val is not None else None
        return None
