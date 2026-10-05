"""Metrics collectors and Prometheus exporter for IntelligenceOS."""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

# Standard metrics
REQUEST_COUNT = Counter(
    "intelligenceos_http_requests_total",
    "Total HTTP requests handled by the platform",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "intelligenceos_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

INGESTION_FAILURES = Counter(
    "intelligenceos_ingestion_failures_total",
    "Total failed ingestion processing jobs",
    ["source_type", "error_category"],
)

RETRIEVAL_LATENCY = Histogram(
    "intelligenceos_retrieval_duration_seconds",
    "Document retrieval latency in seconds",
    ["retrieval_mode"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

LLM_LATENCY = Histogram(
    "intelligenceos_llm_request_duration_seconds",
    "LLM completion request duration in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

AGENT_TOOL_FAILURES = Counter(
    "intelligenceos_agent_tool_failures_total",
    "Total failures recorded during agent tool invocation",
    ["tool_name", "error_category"],
)

EVALUATION_RUNS = Counter(
    "intelligenceos_evaluation_runs_total",
    "Total evaluation experiments conducted",
    ["dataset_id", "retrieval_mode"],
)


def record_http_request(
    method: str, endpoint: str, status_code: int, duration_seconds: float
) -> None:
    """Record an HTTP request metric."""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration_seconds)


def record_ingestion_failure(source_type: str, error_category: str) -> None:
    """Record an ingestion failure."""
    INGESTION_FAILURES.labels(source_type=source_type, error_category=error_category).inc()


def record_retrieval_latency(retrieval_mode: str, duration_seconds: float) -> None:
    """Record retrieval latency."""
    RETRIEVAL_LATENCY.labels(retrieval_mode=retrieval_mode).observe(duration_seconds)


def record_llm_latency(provider: str, model: str, duration_seconds: float) -> None:
    """Record LLM call latency."""
    LLM_LATENCY.labels(provider=provider, model=model).observe(duration_seconds)


def record_agent_tool_failure(tool_name: str, error_category: str) -> None:
    """Record a failure during agent tool execution."""
    AGENT_TOOL_FAILURES.labels(tool_name=tool_name, error_category=error_category).inc()


def record_evaluation_run(dataset_id: str, retrieval_mode: str) -> None:
    """Record an evaluation run execution."""
    EVALUATION_RUNS.labels(dataset_id=dataset_id, retrieval_mode=retrieval_mode).inc()


def export_metrics() -> tuple[bytes, str]:
    """Exports all registered Prometheus metrics formatted for scraping."""
    return generate_latest(), CONTENT_TYPE_LATEST
