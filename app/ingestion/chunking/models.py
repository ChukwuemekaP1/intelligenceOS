"""Data transfer models for chunking."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChunkData(BaseModel):
    """Represents an extracted chunk prior to persistence and embedding."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the chunk, also used as the Qdrant Point ID.",
    )
    chunk_index: int = Field(
        ...,
        description="Zero-based sequence index of the chunk.",
    )
    content: str = Field(
        ...,
        description="Text content of the chunk.",
    )
    page_number: int | None = Field(
        default=None,
        description="Page number where this content originated, if available.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Traceability metadata including workspace, source, document, and version IDs.",
    )
