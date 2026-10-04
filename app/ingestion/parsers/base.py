"""Base parser interface for IntelligenceOS knowledge ingestion.

All file and source adapters inherit from BaseParser and convert raw content bytes
into a standard NormalizedDocument representation.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.ingestion.models import NormalizedDocument


class ParserError(Exception):
    """Raised when parsing or extracting content from a raw source fails."""

    pass


class BaseParser(ABC):
    """Abstract contract for source parsers (PDF, CSV, Website, Image)."""

    @abstractmethod
    async def parse(
        self,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedDocument:
        """Parses raw source content into the normalized internal representation.

        Args:
            content: Raw byte payload of the source (file bytes or fetched response).
            metadata: Associated contextual metadata (e.g. filename, url, content_type).

        Returns:
            NormalizedDocument instance containing ordered structural text elements.

        Raises:
            ParserError: If parsing, decoding, or structural extraction fails.
        """
        pass
