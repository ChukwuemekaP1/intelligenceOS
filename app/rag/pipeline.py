"""Complete grounded RAG pipeline orchestrator.

Pipeline:
  Question
  -> query preprocessing
  -> retrieval (semantic or hybrid)
  -> reranking (local, external, or passthrough)
  -> context construction (injection-resistant, bounded)
  -> LLM generation (grounded prompts)
  -> citation extraction
  -> evaluation telemetry
"""

import time
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.factory import get_embedding_provider
from app.providers.llm.base import LLMProvider
from app.providers.llm.factory import get_llm_provider
from app.rag.citations.generator import CitationGenerator
from app.rag.context.builder import ContextBuilder
from app.rag.evaluation_hooks import RAGEvaluationPayload
from app.rag.prompts import RAG_SYSTEM_INSTRUCTION, build_rag_user_prompt
from app.rag.reranking.base import BaseReranker
from app.rag.reranking.factory import get_reranker
from app.rag.retrieval.service import RetrievalService
from app.schemas.llm import CompletionRequest
from app.schemas.rag import Citation, RAGMetrics, RetrievalConfig, RetrievedChunk
from app.vectorstore.base import VectorStore
from app.vectorstore.factory import get_vector_store

logger = get_logger("app.rag.pipeline")


class RAGExecutionResult(BaseModel):
    """Encapsulates the complete result of a RAG pipeline execution."""

    answer: str
    citations: list[Citation]
    metrics: RAGMetrics
    evaluation_payload: RAGEvaluationPayload
    included_chunks: list[RetrievedChunk] = Field(default_factory=list)


class RAGPipeline:
    """Orchestrates retrieval, reranking, context construction, and grounded generation."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        llm_provider: LLMProvider | None = None,
        vector_store: VectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        reranker: BaseReranker | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.llm_provider = llm_provider or get_llm_provider(self.settings)
        self.vector_store = vector_store or get_vector_store(self.settings)
        self.embedding_provider = embedding_provider or get_embedding_provider(self.settings)
        self.reranker = reranker
        self.context_builder = context_builder or ContextBuilder(
            max_context_chars=self.settings.RAG_MAX_CONTEXT_CHARS
        )
        self.retrieval_service = RetrievalService(
            session=self.session,
            vector_store=self.vector_store,
            embedding_provider=self.embedding_provider,
            settings=self.settings,
        )

    async def execute(
        self,
        workspace_id: uuid.UUID,
        query: str,
        retrieval_config: RetrievalConfig | None = None,
    ) -> RAGExecutionResult:
        """Executes the full RAG pipeline with strict workspace tenant boundaries."""
        t_total_start = time.perf_counter()

        # 1. Parameter resolution
        clean_query = query.strip()
        initial_top_k = (
            retrieval_config.initial_top_k
            if retrieval_config and retrieval_config.initial_top_k is not None
            else self.settings.RAG_INITIAL_TOP_K
        )
        final_top_k = (
            retrieval_config.final_top_k
            if retrieval_config and retrieval_config.final_top_k is not None
            else self.settings.RAG_FINAL_TOP_K
        )
        threshold = (
            retrieval_config.similarity_threshold
            if retrieval_config and retrieval_config.similarity_threshold is not None
            else self.settings.RAG_SIMILARITY_THRESHOLD
        )
        enable_rerank = (
            retrieval_config.enable_reranking
            if retrieval_config and retrieval_config.enable_reranking is not None
            else self.settings.RAG_ENABLE_RERANKING
        )
        mode = (
            retrieval_config.retrieval_mode
            if retrieval_config and retrieval_config.retrieval_mode is not None
            else self.settings.RAG_RETRIEVAL_MODE
        )

        # 2. Retrieval stage
        t_ret_start = time.perf_counter()
        initial_candidates = await self.retrieval_service.retrieve(
            workspace_id=workspace_id,
            query=clean_query,
            top_k=initial_top_k,
            similarity_threshold=threshold,
            mode=mode,
        )
        retrieval_latency_ms = (time.perf_counter() - t_ret_start) * 1000

        # 3. Reranking stage
        t_rerank_start = time.perf_counter()
        active_reranker = self.reranker or get_reranker(
            settings=self.settings, enabled=enable_rerank
        )
        reranked_candidates = await active_reranker.rerank(
            query=clean_query,
            candidates=initial_candidates,
            top_k=final_top_k,
        )
        rerank_latency_ms = (time.perf_counter() - t_rerank_start) * 1000

        # 4. Context construction stage
        built_context = self.context_builder.build_context(
            candidates=reranked_candidates,
            max_context_chars=self.settings.RAG_MAX_CONTEXT_CHARS,
        )

        # 5. LLM Generation stage
        t_gen_start = time.perf_counter()
        user_prompt = build_rag_user_prompt(
            question=clean_query,
            formatted_context=built_context.formatted_context,
        )

        completion_req = CompletionRequest(
            prompt=user_prompt,
            system_instruction=RAG_SYSTEM_INSTRUCTION,
            temperature=0.2,
            max_tokens=1024,
        )

        completion_resp = await self.llm_provider.generate_text(completion_req)
        answer = completion_resp.text.strip()
        generation_latency_ms = (time.perf_counter() - t_gen_start) * 1000

        # 6. Citation extraction stage
        citations = CitationGenerator.generate_citations(
            answer=answer,
            included_chunks=built_context.included_chunks,
        )

        total_latency_ms = (time.perf_counter() - t_total_start) * 1000

        metrics = RAGMetrics(
            retrieval_count=len(initial_candidates),
            final_context_count=len(built_context.included_chunks),
            total_latency_ms=round(total_latency_ms, 2),
            retrieval_latency_ms=round(retrieval_latency_ms, 2),
            rerank_latency_ms=round(rerank_latency_ms, 2),
            generation_latency_ms=round(generation_latency_ms, 2),
        )

        # 7. Evaluation Hook Payload
        evaluation_payload = RAGEvaluationPayload.record_execution(
            query=clean_query,
            workspace_id=workspace_id,
            initial_candidates=initial_candidates,
            reranked_candidates=reranked_candidates,
            final_context_chunks=built_context.included_chunks,
            answer=answer,
            citations=citations,
            latency_breakdown={
                "total": metrics.total_latency_ms,
                "retrieval": metrics.retrieval_latency_ms,
                "rerank": metrics.rerank_latency_ms,
                "generation": metrics.generation_latency_ms,
            },
            extra_metadata={
                "retrieval_mode": mode,
                "enable_reranking": enable_rerank,
                "model": completion_resp.model,
                "tokens_estimate": built_context.token_count_estimate,
            },
        )

        return RAGExecutionResult(
            answer=answer,
            citations=citations,
            metrics=metrics,
            evaluation_payload=evaluation_payload,
            included_chunks=built_context.included_chunks,
        )
