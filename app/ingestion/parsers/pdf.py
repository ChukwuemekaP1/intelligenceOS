"""PDF Parser implementation using pypdf.

Extracts text from multi-page PDF documents and preserves page-level traceability.
"""

import io
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.logging import get_logger
from app.ingestion.models import NormalizedDocument, NormalizedElement
from app.ingestion.parsers.base import BaseParser, ParserError
from app.models.source import SourceType

logger = get_logger("app.ingestion.parsers.pdf")


class PdfParser(BaseParser):
    """Parses PDF binary content into normalized elements, preserving page numbers."""

    async def parse(
        self,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedDocument:
        meta = metadata or {}
        filename = meta.get("filename", "Document.pdf")

        if not content:
            raise ParserError("PDF content is empty.")

        try:
            stream = io.BytesIO(content)
            reader = PdfReader(stream)

            # Check if PDF is password-protected/encrypted
            if reader.is_encrypted:
                try:
                    # Attempt decrypt with empty password for passively encrypted files
                    if not reader.decrypt(""):
                        raise ParserError("Cannot parse password-protected PDF.")
                except Exception as exc:
                    raise ParserError("Cannot parse encrypted PDF document.") from exc

            num_pages = len(reader.pages)
            if num_pages == 0:
                raise ParserError("PDF contains no readable pages.")

            # Attempt to retrieve document metadata title
            doc_title = filename
            if reader.metadata and reader.metadata.title:
                clean_title = str(reader.metadata.title).strip()
                if clean_title:
                    doc_title = clean_title

            elements: list[NormalizedElement] = []
            elem_idx = 0

            for page_num_0, page in enumerate(reader.pages):
                page_num_1 = page_num_0 + 1
                try:
                    page_text = page.extract_text() or ""
                except Exception as page_err:
                    logger.warning(f"Error extracting text from PDF page {page_num_1}: {page_err}")
                    page_text = ""

                cleaned_text = page_text.strip()
                if cleaned_text:
                    elements.append(
                        NormalizedElement(
                            element_index=elem_idx,
                            text=cleaned_text,
                            page_number=page_num_1,
                            metadata={
                                "page": page_num_1,
                                "total_pages": num_pages,
                            },
                        )
                    )
                    elem_idx += 1

            if not elements:
                # If all pages contained scanned images or empty text, provide a descriptive message
                raise ParserError(
                    "No extractable text found in PDF. Scanned documents may require OCR."
                )

            return NormalizedDocument(
                title=doc_title,
                source_type=SourceType.PDF,
                elements=elements,
                raw_metadata={
                    "total_pages": num_pages,
                    "filename": filename,
                },
            )

        except ParserError:
            raise
        except PdfReadError as exc:
            raise ParserError(f"Corrupted or invalid PDF file: {exc}") from exc
        except Exception as exc:
            raise ParserError(f"Unexpected error while parsing PDF: {exc}") from exc
