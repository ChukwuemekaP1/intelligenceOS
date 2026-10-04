"""Image OCR Parser implementation using Pillow and pytesseract.

Extracts textual content from scanned or photographic image formats (PNG, JPEG, TIFF, WEBP).
Applies decompression bomb protection and formats the result into a NormalizedDocument.
"""

import io
from typing import Any

import pytesseract
from PIL import Image, UnidentifiedImageError

from app.core.logging import get_logger
from app.ingestion.models import NormalizedDocument, NormalizedElement
from app.ingestion.parsers.base import BaseParser, ParserError
from app.models.source import SourceType

logger = get_logger("app.ingestion.parsers.image")

# Protect against decompression bomb attacks
Image.MAX_IMAGE_PIXELS = 50_000_000


class ImageParser(BaseParser):
    """Parses images using Optical Character Recognition (OCR)."""

    async def parse(
        self,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedDocument:
        meta = metadata or {}
        filename = meta.get("filename", "image.png")

        if not content:
            raise ParserError("Image content is empty.")

        try:
            stream = io.BytesIO(content)
            img = Image.open(stream)
            img_format = img.format or "UNKNOWN"
            width, height = img.size

            # Check if testing mock OCR text is provided
            mock_ocr_text = meta.get("mock_ocr_text")
            if mock_ocr_text is not None:
                extracted_text = str(mock_ocr_text)
            else:
                try:
                    # Run pytesseract OCR
                    extracted_text = pytesseract.image_to_string(img)
                except pytesseract.TesseractNotFoundError:
                    # Occurs when the tesseract binary is not installed on host
                    logger.warning("Tesseract OCR binary not found on system PATH.")
                    raise ParserError(
                        "Tesseract OCR is not installed on the host system. "
                        "Please install tesseract-ocr to enable image parsing."
                    ) from None
                except Exception as ocr_err:
                    raise ParserError(f"OCR processing failed: {ocr_err}") from ocr_err

            cleaned_text = extracted_text.strip()
            if not cleaned_text:
                raise ParserError("No readable text could be recognized in the image.")

            elements = [
                NormalizedElement(
                    element_index=0,
                    text=cleaned_text,
                    page_number=1,
                    metadata={
                        "format": img_format,
                        "width": width,
                        "height": height,
                    },
                )
            ]

            return NormalizedDocument(
                title=filename,
                source_type=SourceType.IMAGE,
                elements=elements,
                raw_metadata={
                    "filename": filename,
                    "image_format": img_format,
                    "resolution": f"{width}x{height}",
                },
            )

        except ParserError:
            raise
        except UnidentifiedImageError as exc:
            raise ParserError("Uploaded file is not a recognized image format.") from exc
        except Exception as exc:
            raise ParserError(f"Unexpected error while processing image: {exc}") from exc
