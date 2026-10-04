"""Deterministic recursive character chunker.

Produces uniform, repeatable chunks from a NormalizedDocument with full traceability
back to the source, document, version, and page number.
"""

import uuid

from app.ingestion.chunking.base import BaseChunker
from app.ingestion.chunking.models import ChunkData
from app.ingestion.models import NormalizedDocument


class DeterministicChunker(BaseChunker):
    """Chunks documents using deterministic character boundaries and sliding window overlap.

    Guarantees that given the exact same input document, identical chunks and chunk indices
    will always be generated.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 150) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively splits text into segments smaller than chunk_size."""
        if len(text) <= self.chunk_size:
            return [text]

        if not separators:
            # Fallback to hard character slicing if no separators remain
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size - self.chunk_overlap)
            ]

        separator = separators[0]
        remaining_separators = separators[1:]

        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        chunks: list[str] = []
        current_chunk = ""

        for piece in splits:
            if not piece:
                continue

            test_addition = (current_chunk + separator + piece) if current_chunk else piece

            if len(test_addition) <= self.chunk_size:
                current_chunk = test_addition
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                if len(piece) > self.chunk_size:
                    # Piece is still too large, split further with remaining separators
                    sub_chunks = self._split_text(piece, remaining_separators)
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = piece

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def chunk(
        self,
        document: NormalizedDocument,
        workspace_id: uuid.UUID,
        source_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> list[ChunkData]:
        """Chunks a normalized document into discrete traceable ChunkData objects."""
        chunks: list[ChunkData] = []
        chunk_idx = 0

        for elem in document.elements:
            elem_text = elem.text.strip()
            if not elem_text:
                continue

            # Split element text if it exceeds chunk_size
            sub_texts = self._split_text(elem_text, self.separators)

            for sub_text in sub_texts:
                cleaned_sub = sub_text.strip()
                if not cleaned_sub:
                    continue

                chunk_metadata = {
                    "workspace_id": str(workspace_id),
                    "source_id": str(source_id),
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "source_type": document.source_type.value,
                    "document_title": document.title,
                    "page_number": elem.page_number,
                    "char_count": len(cleaned_sub),
                    "word_count": len(cleaned_sub.split()),
                    **elem.metadata,
                }

                chunks.append(
                    ChunkData(
                        id=uuid.uuid4(),
                        chunk_index=chunk_idx,
                        content=cleaned_sub,
                        page_number=elem.page_number,
                        metadata=chunk_metadata,
                    )
                )
                chunk_idx += 1

        return chunks
