"""Trace and Span models for distributed request tracing and observability."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import redact_sensitive_data


class Span(BaseModel):
    """An individual operation segment in an execution trace."""

    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None
    operation_name: str
    start_time: float = Field(default_factory=time.perf_counter)
    end_time: float | None = None
    duration_ms: float | None = None
    status: str = "ok"  # "ok" or "error"
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def finish(self, status: str = "ok", error_message: str | None = None) -> None:
        """Complete the span and record its duration."""
        self.end_time = time.perf_counter()
        self.duration_ms = round((self.end_time - self.start_time) * 1000.0, 2)
        self.status = status
        if error_message:
            self.error_message = redact_sensitive_data(error_message)

    def set_tag(self, key: str, value: Any) -> None:
        """Set a tag or metadata item with automatic redaction if string."""
        if isinstance(value, str):
            self.metadata[key] = redact_sensitive_data(value)
        else:
            self.metadata[key] = value


class Trace(BaseModel):
    """Encapsulates a full sequence of nested spans for an operation."""

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str | None = None
    operation_name: str
    start_time_iso: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "ok"
    duration_ms: float = 0.0
    spans: list[Span] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_span(self, span: Span) -> None:
        self.spans.append(span)

    def finish(self, status: str = "ok") -> None:
        self.status = status
        if self.spans:
            # Total duration from first span start to last span end
            start = self.spans[0].start_time
            end = max((s.end_time or s.start_time) for s in self.spans)
            self.duration_ms = round((end - start) * 1000.0, 2)


# Context variables for trace propagation across async workflows
current_trace_ctx: ContextVar[Trace | None] = ContextVar("current_trace_ctx", default=None)
current_span_ctx: ContextVar[Span | None] = ContextVar("current_span_ctx", default=None)


def get_current_trace() -> Trace | None:
    return current_trace_ctx.get()


def get_current_span() -> Span | None:
    return current_span_ctx.get()


@asynccontextmanager
async def start_trace(
    operation_name: str,
    workspace_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
) -> AsyncGenerator[Trace, None]:
    """Context manager to start and scope an execution trace."""
    ws_str = str(workspace_id) if workspace_id else None
    t_id = trace_id or str(uuid.uuid4())
    trace = Trace(
        trace_id=t_id,
        workspace_id=ws_str,
        operation_name=operation_name,
    )
    token = current_trace_ctx.set(trace)
    try:
        yield trace
        trace.finish(status="ok" if trace.status != "error" else "error")
    except Exception:
        trace.finish(status="error")
        raise
    finally:
        current_trace_ctx.reset(token)


@asynccontextmanager
async def start_span(
    operation_name: str,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[Span, None]:
    """Context manager to start a child span within the current active trace."""
    trace = current_trace_ctx.get()
    parent_span = current_span_ctx.get()

    clean_meta = {}
    if metadata:
        for k, v in metadata.items():
            if isinstance(v, str):
                clean_meta[k] = redact_sensitive_data(v)
            else:
                clean_meta[k] = v

    span = Span(
        parent_span_id=parent_span.span_id if parent_span else None,
        operation_name=operation_name,
        metadata=clean_meta,
    )

    if trace:
        trace.add_span(span)

    token = current_span_ctx.set(span)
    try:
        yield span
        if span.duration_ms is None:
            span.finish(status="ok")
    except Exception as exc:
        span.finish(status="error", error_message=str(exc))
        if trace:
            trace.status = "error"
        raise
    finally:
        current_span_ctx.reset(token)
