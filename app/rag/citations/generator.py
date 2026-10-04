"""Citation extraction and mapping component."""

import re

from app.rag.prompts import INSUFFICIENT_EVIDENCE_PHRASE
from app.schemas.rag import Citation, RetrievedChunk


class CitationGenerator:
    """Extracts citation markers and maps supporting chunks into traceable Citation schemas."""

    @staticmethod
    def _create_snippet(text: str, max_chars: int = 180) -> str:
        clean = " ".join(text.split())
        if len(clean) <= max_chars:
            return clean
        return clean[:max_chars].rstrip() + "..."

    @classmethod
    def generate_citations(
        cls,
        answer: str,
        included_chunks: list[RetrievedChunk],
    ) -> list[Citation]:
        if not included_chunks:
            return []

        # If answer explicitly acknowledges insufficient evidence, return empty citations
        if INSUFFICIENT_EVIDENCE_PHRASE.lower() in answer.lower():
            return []

        # Detect citation markers like [Doc 1], [Doc 2], [1], [Document 1]
        explicit_doc_indices = set()
        matches = re.findall(r"\[(?:Doc|Document)?\s*(\d+)\]", answer, flags=re.IGNORECASE)
        for m in matches:
            try:
                idx = int(m)
                if 1 <= idx <= len(included_chunks):
                    explicit_doc_indices.add(idx)
            except ValueError:
                pass

        # If explicit markers found, cite those specific chunks; otherwise cite all included context
        target_chunks: list[RetrievedChunk] = []
        if explicit_doc_indices:
            for idx in sorted(explicit_doc_indices):
                target_chunks.append(included_chunks[idx - 1])
        else:
            target_chunks = list(included_chunks)

        citations: list[Citation] = []
        seen_chunks = set()

        for chunk in target_chunks:
            if chunk.id in seen_chunks:
                continue
            seen_chunks.add(chunk.id)

            citations.append(
                Citation(
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    source_id=chunk.source_id,
                    source_name=chunk.source_name,
                    source_type=chunk.source_type,
                    document_id=chunk.document_id,
                    document_version_id=chunk.document_version_id,
                    version_number=chunk.version_number,
                    page_number=chunk.page_number,
                    snippet=cls._create_snippet(chunk.content),
                    score=chunk.score,
                )
            )

        return citations
