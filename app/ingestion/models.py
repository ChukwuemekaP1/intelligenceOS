"""Normalized Internal Representation for Parsed Knowledge.

All disparate input formats (PDF, Website, CSV, Image) are converted into
this standard structure before passing to the downstream chunking and embedding pipelines.
This ensures downstream chunking and vector storage remain decoupled from origin formats.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.source import SourceType


class NormalizedElement(BaseModel):
    """Represents a discrete structural element (e.g. a page, table row, or web section)."""

    model_config = ConfigDict(frozen=True)

    element_index: int = Field(
        ...,
        description="Sequential index of the element within the parsed document.",
    )
    text: str = Field(
        ...,
        description="Cleaned, normalized text content of this element.",
    )
    page_number: int | None = Field(
        default=None,
        description="Source page number (1-indexed) if applicable (e.g., PDF or Image).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Origin-specific metadata (row_index, heading, table_name, etc.).",
    )


class NormalizedDocument(BaseModel):
    """The canonical internal representation of any ingested knowledge source.

    Downstream chunkers and embedders consume this object exclusively, guaranteeing
    uniform processing regardless of whether the source was a PDF, URL, CSV, or Image.
    """

    model_config = ConfigDict(frozen=True)

    title: str = Field(
        default="Untitled Document",
        description="Document title, original filename, or page title.",
    )
    source_type: SourceType = Field(
        ...,
        description="The source classification (PDF, WEBSITE, CSV, IMAGE).",
    )
    elements: list[NormalizedElement] = Field(
        default_factory=list,
        description="Ordered sequence of normalized text elements composing the document.",
    )
    raw_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="High-level metadata collected during extraction (author, mime, url, etc.).",
    )

    @property
    def full_text(self) -> str:
        """Returns all element text concatenated with newlines."""
        return "\n\n".join(elem.text for elem in self.elements if elem.text.strip())

    @property
    def total_characters(self) -> int:
        """Returns total character count across all elements."""
        return sum(len(elem.text) for elem in self.elements)
