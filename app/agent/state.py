"""Explicit state definitions for LangGraph agent orchestration."""

from typing import Any, TypedDict


class AgentStepRecord(TypedDict):
    """Detailed record of a single agent reasoning and tool execution step."""

    step_index: int
    thought: str
    action: str  # "call_tool" | "final_answer"
    tool_name: str | None
    tool_input: Any | None
    tool_result: Any | None
    error: str | None
    duration_ms: float


class AgentState(TypedDict):
    """Explicit state representation managed by the LangGraph runtime."""

    # Tenancy and session context
    workspace_id: str
    user_id: str | None
    conversation_id: str | None
    query: str
    allowed_tools: list[str]

    # Bounded loop controls
    step_count: int
    max_steps: int

    # Multi-turn conversation messages
    history: list[dict[str, str]]

    # Step-by-step execution trace
    steps: list[AgentStepRecord]

    # Intermediate decision state
    current_thought: str
    current_action: str  # "call_tool" | "final_answer"
    current_tool_name: str | None
    current_tool_input: Any | None
    current_tool_result: str | None

    # Output and lifecycle status
    final_response: str | None
    status: str  # "running" | "completed" | "budget_exceeded" | "failed"
    error: str | None
