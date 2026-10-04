"""Pydantic request and response schemas for the agent layer and execution traces."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentStepResponse(BaseModel):
    """Schema representing an individual reasoning or tool execution step in the trace."""

    model_config = ConfigDict(from_attributes=True)

    step_index: int
    thought: str = ""
    action: str = "call_tool"
    tool_name: str | None = None
    tool_input: Any | None = None
    tool_result: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0


class AgentExecuteRequest(BaseModel):
    """Payload for invoking an agent request within a workspace."""

    query: str = Field(..., min_length=1, max_length=2000, description="The user query or prompt.")
    conversation_id: uuid.UUID | None = Field(
        None, description="Optional conversation session ID to persist context."
    )
    allowed_tools: list[str] | None = Field(
        None,
        description="Optional explicit subset of authorized tools to grant for this execution.",
    )
    max_steps: int = Field(
        default=6,
        ge=1,
        le=15,
        description="Maximum execution steps allowed for this query.",
    )


class AgentExecutionResponse(BaseModel):
    """Full execution response including answer, status, and complete trace."""

    model_config = ConfigDict(from_attributes=True)

    execution_id: uuid.UUID
    workspace_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    query: str
    status: str
    final_response: str | None = None
    steps_count: int
    total_latency_ms: float
    trace: list[AgentStepResponse] = []
    error: str | None = None
    created_at: datetime


class AgentExecutionSummary(BaseModel):
    """Summary of an execution record for history listings."""

    model_config = ConfigDict(from_attributes=True)

    execution_id: uuid.UUID
    workspace_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    query: str
    status: str
    steps_count: int
    total_latency_ms: float
    created_at: datetime
