"""Text and Markdown Parser implementation.

Parses plain text (.txt) and markdown (.md) documents into canonical NormalizedDocument elements.
"""

from typing import Any

from app.ingestion.models import NormalizedDocument, NormalizedElement
from app.ingestion.parsers.base import BaseParser, ParserError
from app.models.source import SourceType


class TextParser(BaseParser):
    """Parses plain text and Markdown files into searchable text elements."""

    async def parse(
        self,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedDocument:
        meta = metadata or {}
        filename = meta.get("filename", "document.txt")

        if not content:
            raise ParserError("Text document content is empty.")

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise ParserError(f"Failed to decode text document: {exc}") from exc

        # Extract title from first heading or metadata or filename
        title = meta.get("title")
        if not title:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines and lines[0].startswith("#"):
                title = lines[0].lstrip("#").strip()
            else:
                title = filename

        # Split into paragraphs as individual normalized elements
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]

        if not any(p for p in paragraphs):
            raise ParserError("Text document contains no readable content.")

        elements: list[NormalizedElement] = []
        for idx, para in enumerate(paragraphs):
            if not para:
                continue
            elements.append(
                NormalizedElement(
                    element_index=idx,      # FIX: was `index=idx` (wrong field name)
                    text=para,              # FIX: was `content=para` (wrong field name)
                    page_number=None,
                    metadata={"filename": filename, "paragraph_index": idx},
                )
            )

        if not elements:
            raise ParserError("Text document contains no readable content.")

        return NormalizedDocument(
            title=title,
            source_type=SourceType.TEXT,   # FIX: was SourceType.TEXT.value (string, not enum)
            elements=elements,
            raw_metadata=meta,
        )
