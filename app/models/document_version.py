"""DocumentVersion model representing an immutable snapshot of a Document.

This module tracks version information, object-storage references for raw files,
processing statuses, and error messages for failures.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import TimestampMixin
from app.models.source import ProcessingStatus

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.document import Document


class DocumentVersion(Base, TimestampMixin):
    """Represents a specific version and processing state of a Document.

    Links directly to raw object storage (storage_key) and child vector chunks.
    """

    __tablename__ = "document_versions"

    # Primary identifier (UUIDv4)
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Reference to parent Document
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version sequence number (starts at 1)
    version_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    # Object storage reference path (e.g. 'workspaces/{ws_id}/sources/{src_id}/file.pdf')
    storage_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        index=True,
    )

    # Ingestion status of this version: PENDING, PROCESSING, COMPLETED, FAILED
    status: Mapped[str] = mapped_column(
        String(32),
        default=ProcessingStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    # Sanitized error diagnostics on failure (safe for debugging without leaking secrets)
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="versions",
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document_version",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )
