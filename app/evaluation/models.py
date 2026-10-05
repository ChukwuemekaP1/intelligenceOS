"""Dataset and configuration schemas for reproducible RAG evaluations."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvaluationExample(BaseModel):
    """An individual test case in an evaluation dataset."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    expected_answer: str | None = None
    relevance_scores: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationDataset(BaseModel):
    """A versioned evaluation dataset for a specific workspace or benchmark."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    version: str = "1.0.0"
    workspace_id: str = ""
    description: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    examples: list[EvaluationExample] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationConfig(BaseModel):
    """Explicit parameters governing a reproducible evaluation experiment."""

    retrieval_mode: Literal["semantic", "hybrid"] = "semantic"
    enable_reranking: bool = False
    reranker_type: Literal["local", "none", "external"] = "local"
    initial_top_k: int = 10
    final_top_k: int = 5
    similarity_threshold: float = 0.0
    embedding_model: str = "text-embedding-004"
    llm_model: str = "gemini-3.8-flash"
    evaluator_mode: Literal["deterministic", "llm_assisted"] = "deterministic"


class ExampleResult(BaseModel):
    """Evaluation result for an individual example."""

    example_id: str
    query: str
    retrieved_chunk_ids: list[str]
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_metrics: dict[str, float]
    generated_answer: str | None = None
    answer_relevance: float | None = None
    groundedness: float | None = None
    citation_correctness: float | None = None
    latency_ms: float = 0.0
    error: str | None = None


class EvaluationRun(BaseModel):
    """A completed evaluation run with full experiment metadata and aggregates."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dataset_id: str
    dataset_name: str
    dataset_version: str
    workspace_id: str
    config: EvaluationConfig
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "completed"  # "completed" | "failed"
    total_examples: int = 0
    failures_count: int = 0
    mean_recall_at_k: float = 0.0
    mean_mrr: float = 0.0
    mean_ndcg_at_k: float = 0.0
    mean_citation_f1: float = 0.0
    mean_answer_relevance: float | None = None
    mean_groundedness: float | None = None
    mean_latency_ms: float = 0.0
    example_results: list[ExampleResult] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class ExperimentComparison(BaseModel):
    """Comparison view between two evaluation runs (A vs B)."""

    run_a_id: str
    run_b_id: str
    dataset_id: str
    config_diff: dict[str, Any]
    metrics_diff: dict[str, float]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
