"""Hybrid retriever combining semantic vector search and lexical search via RRF."""

import asyncio
import uuid

from app.core.logging import get_logger
from app.rag.retrieval.base import BaseRetriever
from app.schemas.rag import RetrievedChunk

logger = get_logger("app.rag.retrieval.hybrid")


class HybridRetriever(BaseRetriever):
    """Hybrid candidate retriever executing concurrent dense and lexical retrieval via RRF."""

    def __init__(
        self,
        semantic_retriever: BaseRetriever,
        lexical_retriever: BaseRetriever,
        rrf_k: int = 60,
    ) -> None:
        self.semantic_retriever = semantic_retriever
        self.lexical_retriever = lexical_retriever
        self.rrf_k = rrf_k

    async def retrieve(
        self,
        workspace_id: uuid.UUID,
        query: str,
        top_k: int = 20,
        similarity_threshold: float | None = None,
        source_ids: list[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]:
        # Execute dense and lexical retrieval concurrently, both scoped to source_ids
        dense_task = self.semantic_retriever.retrieve(
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            source_ids=source_ids,
        )
        lexical_task = self.lexical_retriever.retrieve(
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            source_ids=source_ids,
        )

        dense_res, lexical_res = await asyncio.gather(
            dense_task, lexical_task, return_exceptions=True
        )

        dense_candidates: list[RetrievedChunk] = []
        if isinstance(dense_res, Exception):
            logger.warning(f"Dense retrieval error during hybrid search: {dense_res}")
        else:
            dense_candidates = dense_res

        lexical_candidates: list[RetrievedChunk] = []
        if isinstance(lexical_res, Exception):
            logger.warning(f"Lexical retrieval error during hybrid search: {lexical_res}")
        else:
            lexical_candidates = lexical_res

        # If both fail or empty
        if not dense_candidates and not lexical_candidates:
            return []

        # Reciprocal Rank Fusion
        rrf_scores: dict[uuid.UUID, float] = {}
        chunk_map: dict[uuid.UUID, RetrievedChunk] = {}

        for rank, chunk in enumerate(dense_candidates, start=1):
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (self.rrf_k + rank))
            chunk_map[chunk.id] = chunk

        for rank, chunk in enumerate(lexical_candidates, start=1):
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (self.rrf_k + rank))
            if chunk.id not in chunk_map:
                chunk_map[chunk.id] = chunk

        # Sort candidate items by RRF score descending
        sorted_chunk_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True,
        )

        merged: list[RetrievedChunk] = []
        for cid in sorted_chunk_ids[:top_k]:
            candidate = chunk_map[cid]
            # Create a copy with the merged RRF score
            updated_candidate = candidate.model_copy(update={"score": round(rrf_scores[cid], 6)})
            merged.append(updated_candidate)

        return merged
