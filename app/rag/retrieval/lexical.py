"""Lexical keyword-based retriever searching relational chunk records."""

import math
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import Source
from app.rag.retrieval.base import BaseRetriever
from app.schemas.rag import RetrievedChunk

logger = get_logger("app.rag.retrieval.lexical")

# Common English stopwords to ignore in lexical candidate matching
STOPWORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


class LexicalRetriever(BaseRetriever):
    """Lexical keyword retriever performing term-frequency scoring over relational chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _extract_terms(self, query: str) -> list[str]:
        words = re.findall(r"\b[A-Za-z0-9_-]{2,}\b", query.lower())
        terms = [w for w in words if w not in STOPWORDS]
        return terms if terms else words

    async def retrieve(
        self,
        workspace_id: uuid.UUID,
        query: str,
        top_k: int = 20,
        similarity_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        terms = self._extract_terms(query)
        if not terms:
            return []

        # Query chunks belonging strictly to this workspace matching any term
        conditions = [Chunk.content.ilike(f"%{term}%") for term in terms[:10]]
        stmt = (
            select(Chunk, DocumentVersion, Document, Source)
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .join(Source, Document.source_id == Source.id)
            .where(
                Chunk.workspace_id == workspace_id,
                or_(*conditions),
            )
            .limit(top_k * 3)  # Retrieve wider candidate pool for BM25 ranking
        )

        res = await self.session.execute(stmt)
        rows = res.all()
        if not rows:
            return []

        scored_candidates: list[tuple[float, RetrievedChunk]] = []
        for chunk, doc_ver, doc, source in rows:
            content_lower = chunk.content.lower()
            total_words = max(len(content_lower.split()), 1)

            # Calculate BM25-style term frequency score
            score = 0.0
            for term in terms:
                count = content_lower.count(term)
                if count > 0:
                    tf = (count * 2.2) / (count + 1.2 * (0.25 + 0.75 * (total_words / 200.0)))
                    score += tf

            # Normalize score into range [0.0, 1.0] using sigmoid
            norm_score = round(1.0 / (1.0 + math.exp(-score + 2.0)), 4)

            if similarity_threshold is not None and norm_score < similarity_threshold:
                continue

            retrieved = RetrievedChunk(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                workspace_id=workspace_id,
                source_id=source.id,
                source_name=source.name,
                source_type=source.source_type,
                document_id=doc.id,
                document_version_id=doc_ver.id,
                version_number=doc_ver.version_number,
                page_number=chunk.page_number,
                content=chunk.content,
                score=norm_score,
                metadata=chunk.metadata_,
            )
            scored_candidates.append((norm_score, retrieved))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored_candidates[:top_k]]
