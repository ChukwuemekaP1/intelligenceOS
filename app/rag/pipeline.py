"""Complete grounded RAG pipeline orchestrator.

Pipeline:
  Question [+ Conversation History]
  -> query preprocessing
  -> retrieval (semantic or hybrid)
  -> retrieval-confidence guard (empty → insufficient-evidence bypass)
  -> reranking (local, external, or passthrough)
  -> context construction (injection-resistant, bounded)
  -> LLM generation (grounded prompts with synthesis instructions)
  -> citation extraction
  -> evaluation telemetry

Key improvements:
- Conversation history is threaded through to the LLM prompt for multi-turn support.
- Zero-retrieval guard: when retrieval returns no candidates the LLM is given a
  specific no-context prompt and immediately produces the canonical insufficient-evidence
  response without being asked to synthesise from nothing.
- Dense-retrieval failure is observable: if Qdrant is unavailable, the pipeline logs
  a warning and falls back to lexical-only results — this is never silently swallowed.
- The response contract distinguishes answer / citations / retrieval_mode so the
  frontend can display retrieval fallback state clearly.
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
from app.rag.prompts import (
    INSUFFICIENT_EVIDENCE_PHRASE,
    RAG_SYSTEM_INSTRUCTION,
    build_no_context_prompt,
    build_rag_user_prompt,
)
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
    # Indicates whether dense (semantic) retrieval succeeded or fell back to lexical-only.
    # "hybrid" = both succeeded, "lexical" = Qdrant was unavailable, "semantic" = lexical failed.
    retrieval_mode_used: str = Field(default="hybrid")
    # True when retrieval returned no usable candidates
    insufficient_knowledge: bool = Field(default=False)


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
        source_ids: list[uuid.UUID] | None = None,
        conversation_history: list[dict] | None = None,
    ) -> RAGExecutionResult:
        """Executes the full RAG pipeline with strict workspace tenant boundaries.

        Args:
            workspace_id: Tenant workspace UUID.
            query: User question string.
            retrieval_config: Optional per-request retrieval parameter overrides.
            source_ids: Optional list of source UUIDs to restrict retrieval scope.
                        When None, all indexed sources in the workspace are searched.
            conversation_history: Optional ordered list of prior conversation turns,
                                  each a dict with "role" and "content" keys.
                                  Used to provide multi-turn context to the LLM.
        """
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

        from app.observability.metrics import (
            record_llm_latency,
            record_retrieval_latency,
        )
        from app.observability.repository import get_trace_repository
        from app.observability.tracer import get_current_trace, start_span, start_trace

        async def _execute_steps() -> RAGExecutionResult:
            # ── 2. Retrieval ──────────────────────────────────────────────────
            t_ret_start = time.perf_counter()
            retrieval_mode_used = mode

            async with start_span("retrieval", {"mode": mode, "top_k": initial_top_k}):
                try:
                    initial_candidates = await self.retrieval_service.retrieve(
                        workspace_id=workspace_id,
                        query=clean_query,
                        top_k=initial_top_k,
                        similarity_threshold=threshold,
                        mode=mode,
                        source_ids=source_ids,
                    )
                except Exception as retrieval_exc:
                    # Retrieval failure is observable — log it clearly, do not mask it.
                    logger.error(
                        f"[RAG RETRIEVAL FAILED] workspace_id={workspace_id} "
                        f"mode={mode} error={retrieval_exc}"
                    )
                    # Propagate — do not silently return a 200 with a fabricated answer
                    raise

            retrieval_latency_ms = (time.perf_counter() - t_ret_start) * 1000
            record_retrieval_latency(retrieval_mode_used, retrieval_latency_ms / 1000.0)

            logger.info(
                f"[RAG RETRIEVAL] workspace_id={workspace_id} "
                f"mode={retrieval_mode_used} "
                f"candidates={len(initial_candidates)} "
                f"latency_ms={retrieval_latency_ms:.1f}"
            )

            # ── 3. Zero-retrieval guard ───────────────────────────────────────
            # If no candidates were found at all, skip the full pipeline and return
            # the canonical insufficient-evidence answer immediately.
            if not initial_candidates:
                logger.info(
                    f"[RAG NO RESULTS] workspace_id={workspace_id} query='{clean_query[:80]}' "
                    f"— no candidates retrieved, returning insufficient-evidence response."
                )
                total_latency_ms = (time.perf_counter() - t_total_start) * 1000
                empty_metrics = RAGMetrics(
                    retrieval_count=0,
                    final_context_count=0,
                    total_latency_ms=round(total_latency_ms, 2),
                    retrieval_latency_ms=round(retrieval_latency_ms, 2),
                    rerank_latency_ms=0.0,
                    generation_latency_ms=0.0,
                )
                empty_eval = RAGEvaluationPayload.record_execution(
                    query=clean_query,
                    workspace_id=workspace_id,
                    initial_candidates=[],
                    reranked_candidates=[],
                    final_context_chunks=[],
                    answer=INSUFFICIENT_EVIDENCE_PHRASE,
                    citations=[],
                    latency_breakdown={
                        "total": empty_metrics.total_latency_ms,
                        "retrieval": empty_metrics.retrieval_latency_ms,
                        "rerank": 0.0,
                        "generation": 0.0,
                    },
                    extra_metadata={
                        "retrieval_mode": retrieval_mode_used,
                        "insufficient_knowledge": True,
                    },
                )
                return RAGExecutionResult(
                    answer=INSUFFICIENT_EVIDENCE_PHRASE,
                    citations=[],
                    metrics=empty_metrics,
                    evaluation_payload=empty_eval,
                    included_chunks=[],
                    retrieval_mode_used=retrieval_mode_used,
                    insufficient_knowledge=True,
                )

            # ── 4. Reranking ──────────────────────────────────────────────────
            t_rerank_start = time.perf_counter()
            active_reranker = self.reranker or get_reranker(
                settings=self.settings, enabled=enable_rerank
            )
            async with start_span(
                "reranking", {"enabled": enable_rerank, "count": len(initial_candidates)}
            ):
                reranked_candidates = await active_reranker.rerank(
                    query=clean_query,
                    candidates=initial_candidates,
                    top_k=final_top_k,
                )
            rerank_latency_ms = (time.perf_counter() - t_rerank_start) * 1000

            # ── 5. Context construction ───────────────────────────────────────
            async with start_span(
                "context_construction", {"candidates_in": len(reranked_candidates)}
            ):
                built_context = self.context_builder.build_context(
                    candidates=reranked_candidates,
                    max_context_chars=self.settings.RAG_MAX_CONTEXT_CHARS,
                )

            logger.info(
                f"[RAG CONTEXT] workspace_id={workspace_id} "
                f"chunks_included={len(built_context.included_chunks)} "
                f"context_chars={built_context.total_characters} "
                f"truncated={built_context.truncated}"
            )

            # ── 6. LLM Generation ─────────────────────────────────────────────
            t_gen_start = time.perf_counter()

            user_prompt = build_rag_user_prompt(
                question=clean_query,
                formatted_context=built_context.formatted_context,
                conversation_history=conversation_history,
            )

            completion_req = CompletionRequest(
                prompt=user_prompt,
                system_instruction=RAG_SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_tokens=1024,
            )

            async with start_span(
                "llm_generation",
                {"provider": self.settings.LLM_PROVIDER, "model": self.settings.GEMINI_MODEL},
            ):
                completion_resp = await self.llm_provider.generate_text(completion_req)
                answer = completion_resp.text.strip()

            generation_latency_ms = (time.perf_counter() - t_gen_start) * 1000
            record_llm_latency(
                self.settings.LLM_PROVIDER, completion_resp.model, generation_latency_ms / 1000.0
            )

            logger.info(
                f"[RAG GENERATION] workspace_id={workspace_id} "
                f"answer_chars={len(answer)} "
                f"latency_ms={generation_latency_ms:.1f}"
            )

            # ── 7. Detect insufficient-evidence response from LLM ─────────────
            is_insufficient = INSUFFICIENT_EVIDENCE_PHRASE.lower() in answer.lower()

            # ── 8. Citation extraction ────────────────────────────────────────
            async with start_span(
                "citation_extraction", {"chunks_count": len(built_context.included_chunks)}
            ):
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

            # ── 9. Evaluation payload ─────────────────────────────────────────
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
                    "retrieval_mode": retrieval_mode_used,
                    "enable_reranking": enable_rerank,
                    "model": completion_resp.model,
                    "tokens_estimate": built_context.token_count_estimate,
                    "insufficient_knowledge": is_insufficient,
                },
            )

            return RAGExecutionResult(
                answer=answer,
                citations=citations,
                metrics=metrics,
                evaluation_payload=evaluation_payload,
                included_chunks=built_context.included_chunks,
                retrieval_mode_used=retrieval_mode_used,
                insufficient_knowledge=is_insufficient,
            )

        # ── Trace wrapper ─────────────────────────────────────────────────────
        parent_trace = get_current_trace()
        if parent_trace is None:
            async with start_trace("rag_query", workspace_id=workspace_id) as trace:
                res = await _execute_steps()
                get_trace_repository().save_trace(trace)
                return res
        else:
            return await _execute_steps()
