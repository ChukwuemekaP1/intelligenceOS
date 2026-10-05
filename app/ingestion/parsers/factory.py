"""Factory for selecting the appropriate parser based on source type."""

from app.ingestion.parsers.base import BaseParser, ParserError
from app.ingestion.parsers.csv import CsvParser
from app.ingestion.parsers.image import ImageParser
from app.ingestion.parsers.pdf import PdfParser
from app.ingestion.parsers.text import TextParser
from app.ingestion.parsers.website import WebsiteParser
from app.models.source import SourceType


def get_parser(source_type: SourceType | str) -> BaseParser:
    """Returns the dedicated parser instance for the given source type.

    Args:
        source_type: SourceType enum or string ('pdf', 'website', 'csv', 'image', 'text').

    Returns:
        Instance of BaseParser.

    Raises:
        ParserError: If the source type is unsupported.
    """
    normalized_type = str(source_type).lower()

    if normalized_type == SourceType.PDF.value:
        return PdfParser()
    if normalized_type == SourceType.WEBSITE.value:
        return WebsiteParser()
    if normalized_type == SourceType.CSV.value:
        return CsvParser()
    if normalized_type == SourceType.IMAGE.value:
        return ImageParser()
    if normalized_type == SourceType.TEXT.value:
        return TextParser()

    raise ParserError(f"Unsupported source type '{source_type}'.")
