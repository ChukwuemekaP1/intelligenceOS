"""Document model representing parsed units of knowledge within a Source.

A Document represents a logical knowledge entity (e.g. an uploaded file or fetched web page).
It maintains a relationship to its parent Source and one or more DocumentVersions.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.document_version import DocumentVersion
    from app.models.source import Source
    from app.models.workspace import Workspace


class Document(Base, TimestampMixin):
    """Represents a discrete document belonging to a Source and Workspace.

    Acts as an umbrella parent for one or more version snapshots (DocumentVersion).
    """

    __tablename__ = "documents"

    # Primary identifier (UUIDv4)
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Reference to the parent Source
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Workspace isolation key: ensures fast and reliable multi-tenant filtering
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Metadata dictionary for document-level attributes (title, mime type, size, etc.)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    # Relationships
    source: Mapped["Source"] = relationship(
        "Source",
        back_populates="documents",
    )
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )
