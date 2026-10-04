"""CSV Parser implementation.

Parses structured tabular data (CSV) into human-readable, searchable text elements
while preserving row indices and header relationships.
"""

import csv
import io
from typing import Any

from app.ingestion.models import NormalizedDocument, NormalizedElement
from app.ingestion.parsers.base import BaseParser, ParserError
from app.models.source import SourceType


class CsvParser(BaseParser):
    """Parses tabular CSV files into text elements preserving row numbers and column headers."""

    async def parse(
        self,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedDocument:
        meta = metadata or {}
        filename = meta.get("filename", "Data.csv")

        if not content:
            raise ParserError("CSV content is empty.")

        # Decode content with UTF-8, fallback to latin-1 if invalid utf-8 sequences exist
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as exc:
                raise ParserError(f"Failed to decode CSV text: {exc}") from exc

        try:
            stream = io.StringIO(text)
            # Sniff delimiter safely or default to comma
            sample = text[:2048]
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel

            reader = csv.reader(stream, dialect=dialect)
            rows = [row for row in reader if any(cell.strip() for cell in row)]

            if not rows:
                raise ParserError("CSV file contains no valid rows or data.")

            headers = [h.strip() for h in rows[0]]
            data_rows = rows[1:]

            elements: list[NormalizedElement] = []
            elem_idx = 0

            # If there are no data rows (only header), include the header description
            if not data_rows:
                header_text = "Columns: " + ", ".join(headers)
                elements.append(
                    NormalizedElement(
                        element_index=0,
                        text=header_text,
                        page_number=1,
                        metadata={"row_index": 0, "is_header": True},
                    )
                )
            else:
                for row_idx, row in enumerate(data_rows, start=1):
                    # Format row as: Column1: Value1 | Column2: Value2
                    row_pairs: list[str] = []
                    for col_idx, cell in enumerate(row):
                        header = (
                            headers[col_idx] if col_idx < len(headers) else f"Column{col_idx + 1}"
                        )
                        val = cell.strip()
                        if val:
                            row_pairs.append(f"{header}: {val}")

                    if row_pairs:
                        row_text = " | ".join(row_pairs)
                        elements.append(
                            NormalizedElement(
                                element_index=elem_idx,
                                text=row_text,
                                page_number=row_idx,
                                metadata={
                                    "row_index": row_idx,
                                    "total_rows": len(data_rows),
                                },
                            )
                        )
                        elem_idx += 1

            if not elements:
                raise ParserError("No extractable data rows found in CSV.")

            return NormalizedDocument(
                title=filename,
                source_type=SourceType.CSV,
                elements=elements,
                raw_metadata={
                    "filename": filename,
                    "columns": headers,
                    "total_data_rows": len(data_rows),
                },
            )

        except ParserError:
            raise
        except Exception as exc:
            raise ParserError(f"Unexpected error while parsing CSV: {exc}") from exc
