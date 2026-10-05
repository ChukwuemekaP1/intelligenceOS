"""Unit and integration tests for Phase 5 Evaluation and Observability."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.evaluators import DeterministicAnswerEvaluator
from app.evaluation.models import (
    EvaluationConfig,
    EvaluationDataset,
    EvaluationExample,
)
from app.evaluation.repository import get_evaluation_repository
from app.evaluation.retrieval_metrics import (
    compute_mrr,
    compute_ndcg_at_k,
    compute_recall_at_k,
    evaluate_citations,
)
from app.evaluation.runner import EvaluationRunner
from app.models.chunk import Chunk
from app.observability.repository import get_trace_repository
from app.observability.tracer import start_span, start_trace
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.mock import MockLLMProvider
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.models import VectorPoint


def test_deterministic_retrieval_metrics():
    # 1. Recall@K
    retrieved = ["chunk-1", "chunk-2", "chunk-3"]
    expected = ["chunk-2", "chunk-4"]
    assert compute_recall_at_k(retrieved, expected, k=2) == 0.5
    assert compute_recall_at_k(retrieved, expected, k=1) == 0.0
    assert compute_recall_at_k(retrieved, ["chunk-1", "chunk-2"], k=2) == 1.0

    # 2. MRR
    assert compute_mrr(["chunk-1", "chunk-2", "chunk-3"], ["chunk-2"]) == 0.5
    assert compute_mrr(["chunk-2", "chunk-1"], ["chunk-2"]) == 1.0
    assert compute_mrr(["chunk-1"], ["chunk-9"]) == 0.0

    # 3. nDCG@K
    assert compute_ndcg_at_k(["chunk-1", "chunk-2"], {"chunk-1": 1.0, "chunk-2": 0.5}, k=2) == 1.0
    assert compute_ndcg_at_k(["chunk-2", "chunk-1"], {"chunk-1": 1.0, "chunk-2": 0.5}, k=2) < 1.0


def test_citation_evaluation():
    generated = ["c1", "c2"]
    expected = ["c2", "c3"]
    metrics = evaluate_citations(generated, expected)
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5


@pytest.mark.asyncio
async def test_tracing_and_sensitive_data_redaction():
    repo = get_trace_repository()
    repo.clear()

    async with start_trace("test_operation", workspace_id="ws-123") as trace:
        async with start_span("sub_step", {"api_key": "Bearer sensitive_secret_key_12345"}):
            pass

    repo.save_trace(trace)
    saved = repo.get_trace(trace.trace_id)
    assert saved is not None
    assert len(saved.spans) == 1
    assert "Bearer sensitive_secret_key_12345" not in str(saved.spans[0].metadata)
    assert "[REDACTED]" in str(saved.spans[0].metadata)


@pytest.mark.asyncio
async def test_deterministic_answer_evaluator():
    evaluator = DeterministicAnswerEvaluator()
    res = await evaluator.evaluate_answer(
        query="What is Apollo?",
        answer="Apollo was a NASA moon mission.",
        context_texts=[
            "The Apollo program was a NASA human spaceflight effort landing on the moon."
        ],
        expected_answer="Apollo was a moon landing mission.",
        citations=["chunk-1"],
    )
    assert res.groundedness > 0.0
    assert res.answer_relevance > 0.0
    assert res.is_model_based is False


@pytest.mark.asyncio
async def test_evaluation_runner_comparison_and_workspace_isolation(
    db_session: AsyncSession,
    client: AsyncClient,
    auth_headers: any,
):
    # Setup two workspaces
    headers = await auth_headers("eval_tester@example.com", "securepassword123")
    res_w1 = await client.post(
        "/api/v1/workspaces", json={"name": "Eval Workspace 1"}, headers=headers
    )
    ws1_id = res_w1.json()["id"]

    res_w2 = await client.post(
        "/api/v1/workspaces", json={"name": "Eval Workspace 2"}, headers=headers
    )
    ws2_id = res_w2.json()["id"]

    # Seed data in Workspace 1
    vstore = MockVectorStore()
    embedder = MockEmbeddingProvider()

    c1_id = uuid.uuid4()
    doc_ver_id = uuid.uuid4()
    chunk1 = Chunk(
        id=c1_id,
        document_version_id=doc_ver_id,
        workspace_id=uuid.UUID(ws1_id),
        chunk_index=0,
        content="IntelligenceOS is an enterprise AI operating system.",
        metadata_={"source_name": "overview.pdf"},
    )
    db_session.add(chunk1)
    await db_session.commit()

    vec = await embedder.embed_query(chunk1.content)
    await vstore.upsert_points(
        uuid.UUID(ws1_id),
        [
            VectorPoint(
                id=c1_id,
                vector=vec,
                payload={
                    "workspace_id": ws1_id,
                    "text": chunk1.content,
                    "source_name": "overview.pdf",
                    "chunk_index": 0,
                },
            )
        ],
    )

    dataset = EvaluationDataset(
        name="Benchmark Q1",
        workspace_id=ws1_id,
        examples=[
            EvaluationExample(
                query="What is IntelligenceOS?",
                expected_chunk_ids=[str(c1_id)],
                expected_citations=[str(c1_id)],
                expected_answer="IntelligenceOS is an enterprise AI operating system.",
            )
        ],
    )

    runner = EvaluationRunner(
        session=db_session,
        vector_store=vstore,
        embedding_provider=embedder,
        llm_provider=MockLLMProvider(
            default_response=(
                "Based on [Doc 1], IntelligenceOS is an enterprise AI operating system."
            )
        ),
    )

    # 1. Baseline Run (Semantic)
    run_a = await runner.run(
        dataset, EvaluationConfig(retrieval_mode="semantic", enable_reranking=False)
    )
    assert run_a.mean_recall_at_k == 1.0
    assert run_a.mean_mrr == 1.0

    # 2. Comparison Run (Reranked)
    run_b = await runner.run(
        dataset, EvaluationConfig(retrieval_mode="semantic", enable_reranking=True)
    )
    assert run_b.mean_recall_at_k == 1.0

    repo = get_evaluation_repository()
    comp = repo.compare_runs(run_a.run_id, run_b.run_id)
    assert comp is not None
    assert "enable_reranking" in comp.config_diff

    # 3. Workspace isolation check via API: User from WS2 cannot see WS1 datasets
    res_ds_list = await client.get(
        f"/api/v1/workspaces/{ws2_id}/evaluations/datasets", headers=headers
    )
    assert res_ds_list.status_code == 200
    assert len(res_ds_list.json()) == 0

    # 4. Check Prometheus metrics endpoint
    res_metrics = await client.get("/metrics")
    assert res_metrics.status_code == 200
    assert b"intelligenceos_http_requests_total" in res_metrics.content
