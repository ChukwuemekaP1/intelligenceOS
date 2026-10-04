"""Lightweight evaluation hooks and telemetry structures for Phase 5 benchmarking."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.rag import Citation, RetrievedChunk


class CandidateEvalRecord(BaseModel):
    """Evaluation snapshot of a retrieved candidate."""

    chunk_id: uuid.UUID
    initial_rank: int
    rerank_rank: int | None = None
    initial_score: float
    rerank_score: float | None = None
    source_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content_preview: str


class RAGEvaluationPayload(BaseModel):
    """Evaluation payload capturing complete RAG lifecycle telemetry for offline evaluation."""

    query: str
    workspace_id: uuid.UUID
    initial_candidates_count: int
    final_candidates_count: int
    retrieved_candidates: list[CandidateEvalRecord] = Field(default_factory=list)
    final_context_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    latency_ms: dict[str, float] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def record_execution(
        cls,
        query: str,
        workspace_id: uuid.UUID,
        initial_candidates: list[RetrievedChunk],
        reranked_candidates: list[RetrievedChunk],
        final_context_chunks: list[RetrievedChunk],
        answer: str,
        citations: list[Citation],
        latency_breakdown: dict[str, float],
        extra_metadata: dict[str, Any] | None = None,
    ) -> "RAGEvaluationPayload":
        """Constructs an evaluation payload from RAG pipeline execution data."""
        rerank_map = {c.id: (rank, c.score) for rank, c in enumerate(reranked_candidates, start=1)}

        candidate_records: list[CandidateEvalRecord] = []
        for rank, c in enumerate(initial_candidates, start=1):
            rerank_info = rerank_map.get(c.id)
            rerank_rank = rerank_info[0] if rerank_info else None
            rerank_score = rerank_info[1] if rerank_info else None

            candidate_records.append(
                CandidateEvalRecord(
                    chunk_id=c.id,
                    initial_rank=rank,
                    rerank_rank=rerank_rank,
                    initial_score=c.score,
                    rerank_score=rerank_score,
                    source_id=c.source_id,
                    document_id=c.document_id,
                    chunk_index=c.chunk_index,
                    content_preview=c.content[:120].strip(),
                )
            )

        return cls(
            query=query,
            workspace_id=workspace_id,
            initial_candidates_count=len(initial_candidates),
            final_candidates_count=len(final_context_chunks),
            retrieved_candidates=candidate_records,
            final_context_chunk_ids=[c.id for c in final_context_chunks],
            answer=answer,
            citations=citations,
            latency_ms=latency_breakdown,
            metadata=extra_metadata or {},
        )
