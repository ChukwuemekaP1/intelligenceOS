"""Agent runner managing LangGraph execution, timeouts, and result compilation."""

import asyncio
import logging
import time
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import create_agent_graph
from app.agent.state import AgentState, AgentStepRecord
from app.core.config import get_settings
from app.models.agent_execution import ExecutionStatus
from app.models.user import User
from app.providers.llm.base import LLMProvider
from app.tools.base import ToolExecutionContext
from app.tools.builtins import create_default_registry
from app.tools.registry import ToolRegistry
from app.vectorstore.base import VectorStore

logger = logging.getLogger("app.agent.runner")


class AgentRunResult(BaseModel):
    """Result of an agent graph execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    final_response: str
    status: str
    steps: list[AgentStepRecord]
    steps_count: int
    total_latency_ms: float
    error: str | None = None


class AgentRunner:
    """Executes the LangGraph agent state graph within bounded resource limits."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry or create_default_registry(vector_store=vector_store)

    async def run(
        self,
        query: str,
        workspace_id: uuid.UUID,
        user: User | None = None,
        conversation_id: uuid.UUID | None = None,
        allowed_tools: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
        session: AsyncSession | None = None,
        max_steps: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AgentRunResult:
        settings = get_settings()
        effective_max_steps = max_steps or settings.AGENT_MAX_STEPS
        effective_timeout = timeout_seconds or settings.AGENT_TIMEOUT_SECONDS

        # Default to all registered tools if none specified
        if allowed_tools is None:
            effective_allowed_tools = [t.name for t in self.tool_registry.list_tools()]
        else:
            effective_allowed_tools = allowed_tools

        context = ToolExecutionContext(
            workspace_id=workspace_id,
            user_id=user.id if user else None,
            user=user,
            session=session,
            extra={},
        )

        app_graph = create_agent_graph(
            llm_provider=self.llm_provider,
            tool_registry=self.tool_registry,
            context=context,
        )

        initial_state: AgentState = {
            "workspace_id": str(workspace_id),
            "user_id": str(user.id) if user else None,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "query": query,
            "allowed_tools": effective_allowed_tools,
            "step_count": 0,
            "max_steps": effective_max_steps,
            "history": history or [],
            "steps": [],
            "current_thought": "",
            "current_action": "call_tool",
            "current_tool_name": None,
            "current_tool_input": None,
            "current_tool_result": None,
            "final_response": None,
            "status": ExecutionStatus.RUNNING.value,
            "error": None,
        }

        start_time = time.perf_counter()

        try:
            final_state: dict[str, Any] = await asyncio.wait_for(
                app_graph.ainvoke(initial_state),
                timeout=effective_timeout,
            )
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            final_text = (
                final_state.get("final_response")
                or "The agent finished execution without returning an answer."
            )
            status = final_state.get("status", ExecutionStatus.COMPLETED.value)
            steps = final_state.get("steps", [])

            return AgentRunResult(
                final_response=final_text,
                status=status,
                steps=steps,
                steps_count=len(steps),
                total_latency_ms=round(total_latency_ms, 2),
                error=final_state.get("error"),
            )

        except TimeoutError:
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"Agent execution timed out after {effective_timeout}s.")
            return AgentRunResult(
                final_response=(
                    "Agent execution timed out before a complete response could be formed."
                ),
                status=ExecutionStatus.FAILED.value,
                steps=[],
                steps_count=0,
                total_latency_ms=round(total_latency_ms, 2),
                error=f"Execution timed out after {effective_timeout}s.",
            )
        except Exception as exc:
            total_latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.exception(f"Unhandled error during agent execution: {exc}")
            return AgentRunResult(
                final_response="An unexpected error occurred during agent execution.",
                status=ExecutionStatus.FAILED.value,
                steps=[],
                steps_count=0,
                total_latency_ms=round(total_latency_ms, 2),
                error=str(exc),
            )
