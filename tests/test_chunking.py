"""Tests for Deterministic Text Chunking and Traceability Metadata."""

import uuid

from app.ingestion.chunking.deterministic import DeterministicChunker
from app.ingestion.models import NormalizedDocument, NormalizedElement
from app.models.source import SourceType


def test_deterministic_chunking_reproducibility() -> None:
    """Verifies that DeterministicChunker produces identical results given identical inputs."""
    chunker = DeterministicChunker(chunk_size=100, chunk_overlap=20)

    doc = NormalizedDocument(
        title="Test Doc",
        source_type=SourceType.PDF,
        elements=[
            NormalizedElement(
                element_index=0,
                text="This is the first sentence. Here is another sentence that adds more details.",
                page_number=1,
            ),
            NormalizedElement(
                element_index=1,
                text="Page two has extensive descriptions of the IntelligenceOS platform.",
                page_number=2,
            ),
        ],
    )

    ws_id = uuid.uuid4()
    src_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    run1 = chunker.chunk(doc, ws_id, src_id, doc_id, ver_id)
    run2 = chunker.chunk(doc, ws_id, src_id, doc_id, ver_id)

    assert len(run1) == len(run2)
    for c1, c2 in zip(run1, run2, strict=True):
        assert c1.chunk_index == c2.chunk_index
        assert c1.content == c2.content
        assert c1.page_number == c2.page_number
        assert c1.metadata["workspace_id"] == c2.metadata["workspace_id"]


def test_traceability_metadata_preservation() -> None:
    """Verifies that all required IDs and page numbers are embedded in chunk metadata."""
    chunker = DeterministicChunker(chunk_size=200, chunk_overlap=30)

    doc = NormalizedDocument(
        title="Architecture Manual",
        source_type=SourceType.PDF,
        elements=[
            NormalizedElement(
                element_index=0,
                text="System architecture overview on page 5.",
                page_number=5,
            )
        ],
    )

    ws_id = uuid.uuid4()
    src_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    chunks = chunker.chunk(doc, ws_id, src_id, doc_id, ver_id)
    assert len(chunks) == 1

    chunk = chunks[0]
    assert chunk.chunk_index == 0
    assert chunk.page_number == 5

    meta = chunk.metadata
    assert meta["workspace_id"] == str(ws_id)
    assert meta["source_id"] == str(src_id)
    assert meta["document_id"] == str(doc_id)
    assert meta["document_version_id"] == str(ver_id)
    assert meta["source_type"] == "pdf"
    assert meta["page_number"] == 5
    assert meta["char_count"] > 0
    assert meta["word_count"] > 0
