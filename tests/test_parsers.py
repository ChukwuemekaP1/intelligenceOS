"""Tests for Source Parsers (PDF, CSV, Website with SSRF Protection, Image OCR)."""

import io

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.ingestion.parsers.base import ParserError
from app.ingestion.parsers.csv import CsvParser
from app.ingestion.parsers.factory import get_parser
from app.ingestion.parsers.image import ImageParser
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.parsers.website import WebsiteParser, validate_safe_url
from app.models.source import SourceType

MINIMAL_VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300]\n"
    b"  /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
    b"4 0 obj << /Length 53 >> stream\n"
    b"BT\n"
    b"/F1 12 Tf\n"
    b"72 250 Td\n"
    b"(Hello IntelligenceOS PDF) Tj\n"
    b"ET\n"
    b"endstream\n"
    b"endobj\n"
    b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
    b"xref\n"
    b"0 6\n"
    b"0000000000 65535 f\n"
    b"0000000009 00000 n\n"
    b"0000000058 00000 n\n"
    b"0000000115 00000 n\n"
    b"0000000244 00000 n\n"
    b"0000000348 00000 n\n"
    b"trailer << /Size 6 /Root 1 0 R >>\n"
    b"startxref\n"
    b"425\n"
    b"%%EOF"
)


@pytest.mark.asyncio
async def test_pdf_parser_success() -> None:
    """Verifies that PdfParser extracts text and tracks page numbers accurately."""
    parser = PdfParser()
    doc = await parser.parse(MINIMAL_VALID_PDF, {"filename": "whitepaper.pdf"})
    assert doc.source_type == SourceType.PDF
    assert len(doc.elements) == 1
    assert doc.elements[0].page_number == 1
    assert "Hello IntelligenceOS PDF" in doc.elements[0].text


@pytest.mark.asyncio
async def test_pdf_parser_empty_pages_error() -> None:
    """Verifies that blank scanned PDFs without extractable text raise ParserError."""
    parser = PdfParser()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    stream = io.BytesIO()
    writer.write(stream)
    pdf_bytes = stream.getvalue()

    with pytest.raises(ParserError, match="No extractable text found in PDF"):
        await parser.parse(pdf_bytes, {"filename": "test.pdf"})


@pytest.mark.asyncio
async def test_pdf_parser_empty_and_corrupt() -> None:
    """Verifies error handling for empty or corrupt PDF bytes."""
    parser = PdfParser()
    with pytest.raises(ParserError, match="PDF content is empty"):
        await parser.parse(b"", {})

    with pytest.raises(ParserError, match="Corrupted or invalid PDF"):
        await parser.parse(b"not a real pdf content", {})


@pytest.mark.asyncio
async def test_csv_parser_success() -> None:
    """Verifies that CsvParser transforms tabular rows into readable text elements."""
    parser = CsvParser()
    csv_data = (
        b"id,name,role,department\n"
        b"1,Alice,Engineer,Core\n"
        b"2,Bob,Product Manager,AI\n"
        b"3,Charlie,Designer,UX\n"
    )

    doc = await parser.parse(csv_data, {"filename": "employees.csv"})
    assert doc.source_type == SourceType.CSV
    assert len(doc.elements) == 3

    first_elem = doc.elements[0]
    assert first_elem.page_number == 1
    assert "id: 1" in first_elem.text
    assert "name: Alice" in first_elem.text
    assert "role: Engineer" in first_elem.text
    assert first_elem.metadata["row_index"] == 1


@pytest.mark.asyncio
async def test_csv_parser_empty() -> None:
    """Verifies that CsvParser rejects empty CSV data."""
    parser = CsvParser()
    with pytest.raises(ParserError, match="CSV content is empty"):
        await parser.parse(b"", {})


def test_ssrf_validator_blocks_internal_and_private_addresses() -> None:
    """Verifies that validate_safe_url aggressively blocks SSRF targets."""
    # Localhost and loopback
    with pytest.raises(ParserError, match="Access to restricted hostname"):
        validate_safe_url("http://localhost:8000/api")

    with pytest.raises(ParserError, match="Access to restricted hostname"):
        validate_safe_url("http://127.0.0.1/admin")

    # Cloud metadata endpoints
    with pytest.raises(ParserError):
        validate_safe_url("http://169.254.169.254/latest/meta-data")

    with pytest.raises(ParserError, match="Access to restricted hostname"):
        validate_safe_url("http://metadata.google.internal/computeMetadata/v1")

    # Invalid scheme
    with pytest.raises(ParserError, match="Prohibited URL scheme"):
        validate_safe_url("ftp://example.com/file.txt")

    with pytest.raises(ParserError, match="Prohibited URL scheme"):
        validate_safe_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_website_parser_html_extraction() -> None:
    """Verifies that WebsiteParser extracts clean text while stripping noisy tags."""
    parser = WebsiteParser()
    html_content = b"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>IntelligenceOS Architecture</title>
        <script>alert("malicious script");</script>
        <style>body { color: red; }</style>
      </head>
      <body>
        <nav><a href="/">Home Navigation</a></nav>
        <header>Header Banner</header>
        <h1>IntelligenceOS Core Design</h1>
        <p>IntelligenceOS provides autonomous agent orchestration and vector search.</p>
        <p>Phase 2 implements the robust asynchronous knowledge ingestion pipeline.</p>
        <footer>Copyright 2026 IntelligenceOS</footer>
      </body>
    </html>
    """

    doc = await parser.parse(html_content, {"url": "https://example.com/docs"})
    assert doc.source_type == SourceType.WEBSITE
    assert doc.title == "IntelligenceOS Architecture"

    # Verify script, style, nav, and footer were stripped
    full_text = doc.full_text
    assert "alert" not in full_text
    assert "Home Navigation" not in full_text
    assert "Copyright" not in full_text

    # Verify content was extracted
    assert "IntelligenceOS Core Design" in full_text
    assert "Phase 2 implements the robust asynchronous knowledge ingestion pipeline." in full_text


@pytest.mark.asyncio
async def test_image_parser_with_mock_ocr() -> None:
    """Verifies that ImageParser validates image headers and formats into NormalizedDocument."""
    parser = ImageParser()

    # Generate a valid PNG image in memory
    img = Image.new("RGB", (200, 100), color=(73, 109, 137))
    stream = io.BytesIO()
    img.save(stream, format="PNG")
    img_bytes = stream.getvalue()

    # Provide mock OCR text for testing
    doc = await parser.parse(
        img_bytes,
        {"filename": "diagram.png", "mock_ocr_text": "Recognized diagram text line 1"},
    )
    assert doc.source_type == SourceType.IMAGE
    assert doc.title == "diagram.png"
    assert len(doc.elements) == 1
    assert doc.elements[0].page_number == 1
    assert doc.elements[0].text == "Recognized diagram text line 1"


@pytest.mark.asyncio
async def test_image_parser_invalid_format() -> None:
    """Verifies error handling for non-image binary input."""
    parser = ImageParser()
    with pytest.raises(ParserError, match="not a recognized image format"):
        await parser.parse(b"this is not an image", {"filename": "bad.png"})


def test_parser_factory() -> None:
    """Verifies that get_parser returns the appropriate class for each SourceType."""
    assert isinstance(get_parser(SourceType.PDF), PdfParser)
    assert isinstance(get_parser(SourceType.CSV), CsvParser)
    assert isinstance(get_parser(SourceType.WEBSITE), WebsiteParser)
    assert isinstance(get_parser(SourceType.IMAGE), ImageParser)

    with pytest.raises(ParserError, match="Unsupported source type"):
        get_parser("unknown_type")
