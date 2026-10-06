"""Pydantic schemas for knowledge ingestion sources, documents, and chunks."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


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
    # Derived convenience fields — populated from metadata_ by the validator below
    chunk_count: int = Field(default=0, description="Number of indexed chunks (0 until COMPLETED)")
    error_message: str | None = Field(
        default=None, description="Last error detail if status=failed"
    )
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _derive_computed_fields(self) -> "SourceResponse":
        # title falls back to name when not explicitly stored
        if not self.title and self.name:
            self.title = self.name

        # chunk_count is written by ingestion_service on COMPLETED
        if self.metadata and "total_chunks" in self.metadata:
            try:
                self.chunk_count = int(self.metadata["total_chunks"])
            except (TypeError, ValueError):
                self.chunk_count = 0

        # error_message is written by the failure handler into metadata_["error"]
        if not self.error_message and self.metadata and "error" in self.metadata:
            self.error_message = str(self.metadata["error"])[:500]

        return self


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
    page_number: int | None = Field(default=None)
    char_count: int = Field(default=0)
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _derive_chunk_fields(self) -> "ChunkResponse":
        # page_number lives inside metadata_ — surface it at the top level
        if self.page_number is None and self.metadata:
            pn = self.metadata.get("page_number")
            if pn is not None:
                try:
                    self.page_number = int(pn)
                except (TypeError, ValueError):
                    pass

        # char_count derived from content length if not pre-stored
        if self.char_count == 0 and self.content:
            stored = self.metadata.get("char_count") if self.metadata else None
            if stored is not None:
                try:
                    self.char_count = int(stored)
                except (TypeError, ValueError):
                    self.char_count = len(self.content)
            else:
                self.char_count = len(self.content)

        return self
