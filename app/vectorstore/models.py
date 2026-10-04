"""Data models for vector store payloads and points."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VectorPoint(BaseModel):
    """Represents a vector embedding point with mandatory traceability payload metadata."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(
        ...,
        description="Point ID in vector store, matching Chunk.id.",
    )
    vector: list[float] = Field(
        ...,
        description="Embedding vector coordinates.",
    )
    payload: dict[str, Any] = Field(
        ...,
        description=(
            "Metadata payload containing at minimum: workspace_id, source_id, "
            "document_id, document_version_id, chunk_id, source_type, page_number, text."
        ),
    )
