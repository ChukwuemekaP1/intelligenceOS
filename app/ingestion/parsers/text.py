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
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines and lines[0].startswith("#"):
                title = lines[0].lstrip("#").strip()
            else:
                title = filename

        # Split into paragraphs as individual normalized elements
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]

        elements: list[NormalizedElement] = []
        for idx, para in enumerate(paragraphs):
            elements.append(
                NormalizedElement(
                    index=idx,
                    content=para,
                    element_type="heading" if para.startswith("#") else "paragraph",
                    metadata={"filename": filename, "paragraph_index": idx},
                )
            )

        return NormalizedDocument(
            source_type=SourceType.TEXT.value,
            title=title,
            elements=elements,
            raw_metadata=meta,
        )
