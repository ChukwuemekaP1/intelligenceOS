"""Pydantic schemas for Phase 3 Grounded RAG, Retrieval, and Conversations."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """Full traceability citation pointing back to supporting chunks and documents."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID = Field(description="Unique identifier of the cited chunk")
    chunk_index: int = Field(description="Sequence index of the chunk in its document version")
    source_id: uuid.UUID = Field(description="Identifier of the origin source")
    source_name: str = Field(description="Original filename or URL of the source")
    source_type: str = Field(description="Source type (pdf, website, csv, image)")
    document_id: uuid.UUID = Field(description="Parent document UUID")
    document_version_id: uuid.UUID = Field(description="Document version snapshot UUID")
    version_number: int | None = Field(default=None, description="Incremental version number")
    page_number: int | None = Field(default=None, description="1-indexed page number if available")
    snippet: str = Field(description="Verbatim excerpt from the chunk supporting the answer")
    score: float | None = Field(default=None, description="Retrieval or relevance ranking score")


class RetrievedChunk(BaseModel):
    """Internal candidate representation passed through retrieval, reranking, and context."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    workspace_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_type: str
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version_number: int | None = None
    page_number: int | None = None
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalConfig(BaseModel):
    """Runtime configurable parameters for retrieval and candidate ranking."""

    initial_top_k: int | None = Field(
        default=None, ge=1, le=100, description="Initial candidates to retrieve"
    )
    final_top_k: int | None = Field(
        default=None, ge=1, le=50, description="Top candidates after reranking to feed to context"
    )
    similarity_threshold: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Minimum similarity score filter"
    )
    enable_reranking: bool | None = Field(
        default=None, description="Whether to apply secondary reranker"
    )
    retrieval_mode: Literal["semantic", "hybrid"] | None = Field(
        default=None,
        description="Retrieval strategy: dense semantic only or hybrid (dense + lexical)",
    )


class RAGMetrics(BaseModel):
    """Operational and performance metrics for the completed RAG execution."""

    retrieval_count: int = Field(description="Number of initial candidates retrieved")
    final_context_count: int = Field(description="Number of candidates included in LLM context")
    total_latency_ms: float = Field(description="Total end-to-end pipeline latency in milliseconds")
    retrieval_latency_ms: float = Field(description="Candidate retrieval latency in milliseconds")
    rerank_latency_ms: float = Field(description="Reranking latency in milliseconds")
    generation_latency_ms: float = Field(description="LLM generation latency in milliseconds")


class ConversationCreate(BaseModel):
    """Request payload to initiate a new conversation session."""

    title: str | None = Field(
        default=None, max_length=255, description="Optional conversation title"
    )


class MessageResponse(BaseModel):
    """Response representation of a persisted conversation message."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    workspace_id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime


class ConversationResponse(BaseModel):
    """Summary of a conversation session."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    """Detailed conversation view with message history."""

    messages: list[MessageResponse] = Field(default_factory=list)


class QuestionRequest(BaseModel):
    """Request payload to ask a grounded question in a workspace conversation."""

    question: str = Field(min_length=1, max_length=4000, description="User question to answer")
    retrieval_config: RetrievalConfig | None = Field(
        default=None, description="Optional per-request retrieval parameter overrides"
    )
    source_ids: list[uuid.UUID] | None = Field(
        default=None,
        description=(
            "Optional list of source UUIDs to restrict retrieval scope. "
            "When provided, only vectors belonging to these sources are searched. "
            "When null/omitted, all indexed sources in the workspace are searched."
        ),
    )


class QuestionResponse(BaseModel):
    """Comprehensive response containing grounded answer, citations, and execution telemetry."""

    conversation_id: uuid.UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    answer: str
    citations: list[Citation]
    metrics: RAGMetrics
