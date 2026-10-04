"""Source model representing ingested data origins (PDF, Website, CSV, Image).

This module defines the Source entity, which tracks the origin of raw knowledge,
the ingestion status, workspace ownership, and associated metadata.
"""

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.workspace import Workspace


class SourceType(StrEnum):
    """Enumeration of supported knowledge source types."""

    PDF = "pdf"
    WEBSITE = "website"
    CSV = "csv"
    IMAGE = "image"


class ProcessingStatus(StrEnum):
    """Lifecycle statuses for asynchronous knowledge ingestion."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Source(Base, TimestampMixin):
    """Represents a knowledge source provided to a workspace.

    Each source belongs to a specific workspace and has a determined source type.
    A source is the parent container for one or more documents.
    """

    __tablename__ = "sources"

    # Primary identifier (UUIDv4)
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Workspace isolation foreign key: guarantees multi-tenant workspace separation
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Type of source (e.g., pdf, website, csv, image)
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    # Human-readable name or identifier (e.g. filename, website URL, or title)
    name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
    )

    # Ingestion status: PENDING -> PROCESSING -> COMPLETED or FAILED
    status: Mapped[str] = mapped_column(
        String(32),
        default=ProcessingStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    # JSON metadata dictionary: stores custom attributes, error details, URLs, etc.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="sources",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="source",
        cascade="all, delete-orphan",
    )
