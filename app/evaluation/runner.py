"""Evaluation runner executing datasets across reproducible retrieval configurations."""

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.evaluation.evaluators import DeterministicAnswerEvaluator, LLMAssistedAnswerEvaluator
from app.evaluation.models import (
    EvaluationConfig,
    EvaluationDataset,
    EvaluationRun,
    ExampleResult,
)
from app.evaluation.repository import get_evaluation_repository
from app.evaluation.retrieval_metrics import (
    compute_mrr,
    compute_ndcg_at_k,
    compute_recall_at_k,
    evaluate_citations,
)
from app.observability.metrics import record_evaluation_run
from app.observability.tracer import start_span, start_trace
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.factory import get_embedding_provider
from app.providers.llm.base import LLMProvider
from app.providers.llm.factory import get_llm_provider
from app.rag.citations.generator import CitationGenerator
from app.rag.context.builder import ContextBuilder
from app.rag.prompts import RAG_SYSTEM_INSTRUCTION, build_rag_user_prompt
from app.rag.reranking.base import BaseReranker
from app.rag.reranking.factory import get_reranker
from app.rag.retrieval.service import RetrievalService
from app.schemas.llm import CompletionRequest
from app.vectorstore.base import VectorStore
from app.vectorstore.factory import get_vector_store


class EvaluationRunner:
    """Executes a benchmark evaluation dataset against an explicit retrieval/model configuration."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        vector_store: VectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        llm_provider: LLMProvider | None = None,
        reranker: BaseReranker | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.vector_store = vector_store or get_vector_store(self.settings)
        self.embedding_provider = embedding_provider or get_embedding_provider(self.settings)
        self.llm_provider = llm_provider or get_llm_provider(self.settings)
        self.reranker = reranker
        self.retrieval_service = RetrievalService(
            session=self.session,
            vector_store=self.vector_store,
            embedding_provider=self.embedding_provider,
            settings=self.settings,
        )
        self.context_builder = ContextBuilder(max_context_chars=self.settings.RAG_MAX_CONTEXT_CHARS)

    async def run(
        self,
        dataset: EvaluationDataset,
        config: EvaluationConfig,
    ) -> EvaluationRun:
        """Runs the entire dataset under the specified configuration and records metrics."""
        run_id = str(uuid.uuid4())
        workspace_uuid = uuid.UUID(dataset.workspace_id)
        example_results: list[ExampleResult] = []
        failures: list[str] = []

        active_reranker = self.reranker or get_reranker(
            settings=self.settings,
            enabled=config.enable_reranking,
        )

        evaluator = (
            LLMAssistedAnswerEvaluator(self.llm_provider)
            if config.evaluator_mode == "llm_assisted"
            else DeterministicAnswerEvaluator()
        )

        total_latencies = []

        async with start_trace(
            operation_name="evaluation_run",
            workspace_id=dataset.workspace_id,
            trace_id=run_id,
        ):
            for example in dataset.examples:
                t0 = time.perf_counter()
                try:
                    # 1. Retrieval
                    async with start_span(
                        "retrieval", {"query": example.query, "mode": config.retrieval_mode}
                    ):
                        initial_candidates = await self.retrieval_service.retrieve(
                            workspace_id=workspace_uuid,
                            query=example.query,
                            top_k=config.initial_top_k,
                            similarity_threshold=config.similarity_threshold,
                            mode=config.retrieval_mode,
                        )

                    # 2. Reranking
                    if config.enable_reranking:
                        async with start_span("reranking", {"count": len(initial_candidates)}):
                            reranked_candidates = await active_reranker.rerank(
                                query=example.query,
                                candidates=initial_candidates,
                                top_k=config.final_top_k,
                            )
                    else:
                        reranked_candidates = initial_candidates[: config.final_top_k]

                    # 3. Context Construction
                    built_context = self.context_builder.build_context(
                        candidates=reranked_candidates,
                        max_context_chars=self.settings.RAG_MAX_CONTEXT_CHARS,
                    )

                    # 4. LLM Generation
                    user_prompt = build_rag_user_prompt(
                        question=example.query,
                        formatted_context=built_context.formatted_context,
                    )
                    completion_req = CompletionRequest(
                        prompt=user_prompt,
                        system_instruction=RAG_SYSTEM_INSTRUCTION,
                        temperature=0.0,
                        max_tokens=1000,
                    )
                    async with start_span("generation", {"model": config.llm_model}):
                        completion_resp = await self.llm_provider.generate_text(completion_req)
                        answer = completion_resp.text.strip()

                    # 5. Citation Extraction
                    citations = CitationGenerator.generate_citations(
                        answer=answer,
                        included_chunks=built_context.included_chunks,
                    )
                    gen_citation_ids = [str(c.chunk_id) for c in citations]

                    # 6. Metric Computation
                    retrieved_ids = [str(c.id) for c in reranked_candidates]
                    rec_k = compute_recall_at_k(
                        retrieved_ids, example.expected_chunk_ids, k=config.final_top_k
                    )
                    mrr = compute_mrr(retrieved_ids, example.expected_chunk_ids)
                    ndcg = compute_ndcg_at_k(
                        retrieved_ids,
                        example.relevance_scores or example.expected_chunk_ids,
                        k=config.final_top_k,
                    )
                    cit_metrics = evaluate_citations(gen_citation_ids, example.expected_citations)

                    # 7. Answer Quality Evaluation
                    context_texts = [c.content for c in built_context.included_chunks]
                    ans_eval = await evaluator.evaluate_answer(
                        query=example.query,
                        answer=answer,
                        context_texts=context_texts,
                        expected_answer=example.expected_answer,
                        citations=gen_citation_ids,
                    )

                    lat_ms = (time.perf_counter() - t0) * 1000.0
                    total_latencies.append(lat_ms)

                    example_results.append(
                        ExampleResult(
                            example_id=example.id,
                            query=example.query,
                            retrieved_chunk_ids=retrieved_ids,
                            recall_at_k=rec_k,
                            mrr=mrr,
                            ndcg_at_k=ndcg,
                            citation_metrics=cit_metrics,
                            generated_answer=answer,
                            answer_relevance=ans_eval.answer_relevance,
                            groundedness=ans_eval.groundedness,
                            citation_correctness=ans_eval.citation_correctness,
                            latency_ms=round(lat_ms, 2),
                        )
                    )

                except Exception as exc:
                    lat_ms = (time.perf_counter() - t0) * 1000.0
                    failures.append(f"Example {example.id}: {str(exc)}")
                    example_results.append(
                        ExampleResult(
                            example_id=example.id,
                            query=example.query,
                            retrieved_chunk_ids=[],
                            recall_at_k=0.0,
                            mrr=0.0,
                            ndcg_at_k=0.0,
                            citation_metrics={"precision": 0.0, "recall": 0.0, "f1": 0.0},
                            latency_ms=round(lat_ms, 2),
                            error=str(exc),
                        )
                    )

        # Compute Aggregates
        n = len(example_results)
        mean_rec = sum(r.recall_at_k for r in example_results) / n if n else 0.0
        mean_mrr = sum(r.mrr for r in example_results) / n if n else 0.0
        mean_ndcg = sum(r.ndcg_at_k for r in example_results) / n if n else 0.0
        mean_cit_f1 = (
            sum(r.citation_metrics.get("f1", 0.0) for r in example_results) / n if n else 0.0
        )
        ans_rels = [r.answer_relevance for r in example_results if r.answer_relevance is not None]
        mean_rel = sum(ans_rels) / len(ans_rels) if ans_rels else None
        groundeds = [r.groundedness for r in example_results if r.groundedness is not None]
        mean_grounded = sum(groundeds) / len(groundeds) if groundeds else None
        mean_lat = sum(total_latencies) / len(total_latencies) if total_latencies else 0.0

        eval_run = EvaluationRun(
            run_id=run_id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            workspace_id=dataset.workspace_id,
            config=config,
            status="completed" if not failures else "completed_with_errors",
            total_examples=len(dataset.examples),
            failures_count=len(failures),
            mean_recall_at_k=round(mean_rec, 4),
            mean_mrr=round(mean_mrr, 4),
            mean_ndcg_at_k=round(mean_ndcg, 4),
            mean_citation_f1=round(mean_cit_f1, 4),
            mean_answer_relevance=round(mean_rel, 4) if mean_rel is not None else None,
            mean_groundedness=round(mean_grounded, 4) if mean_grounded is not None else None,
            mean_latency_ms=round(mean_lat, 2),
            example_results=example_results,
            failures=failures,
        )

        # Persist Run
        repo = get_evaluation_repository()
        repo.save_run(eval_run)
        record_evaluation_run(dataset_id=dataset.id, retrieval_mode=config.retrieval_mode)

        return eval_run
