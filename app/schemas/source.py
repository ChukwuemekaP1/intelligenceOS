"""Pydantic schemas for knowledge ingestion sources, documents, and chunks."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class UrlSourceCreate(BaseModel):
    """Schema for submitting a website URL source."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl = Field(
        ...,
        description="Public HTTP or HTTPS website URL to fetch and ingest.",
        examples=["https://example.com/docs"],
    )
    title: str | None = Field(
        default=None,
        max_length=255,
        description="Optional human-readable label or title for the source.",
        examples=["Example Documentation"],
    )
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional alias for title.",
        examples=["Example Documentation"],
    )


class SourceResponse(BaseModel):
    """API response model representing a knowledge source."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    source_type: str
    name: str
    title: str = Field(default="")
    status: str
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs) -> "SourceResponse":
        # Ensure title defaults to name if not explicitly set
        instance = super().model_validate(obj, *args, **kwargs)
        if not instance.title and instance.name:
            instance.title = instance.name
        return instance


class DocumentVersionResponse(BaseModel):
    """API response model for a document version snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    storage_key: str | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    """API response model for a logical knowledge document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    workspace_id: uuid.UUID
    metadata: dict[str, Any] = Field(alias="metadata_")
    versions: list[DocumentVersionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ChunkResponse(BaseModel):
    """API response model for an indexed text chunk."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_version_id: uuid.UUID
    workspace_id: uuid.UUID
    chunk_index: int
    content: str
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime
