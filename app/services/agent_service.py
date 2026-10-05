"""Agent service coordinating execution, persistence, traces, and workspace security."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import AgentRunner
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.models.agent_execution import AgentExecution
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.user import User
from app.providers.llm.factory import get_llm_provider
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecutionResponse,
    AgentExecutionSummary,
    AgentStepResponse,
)
from app.services.conversation_service import ConversationService
from app.services.workspace_service import WorkspaceService
from app.vectorstore.base import VectorStore

logger = get_logger("app.services.agent_service")


class AgentService:
    """Manages LangGraph agent execution runs, trace recording, and workspace scoping."""

    @staticmethod
    async def execute_agent(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        request: AgentExecuteRequest,
        user: User,
        runner: AgentRunner | None = None,
        vector_store: VectorStore | None = None,
    ) -> AgentExecutionResponse:
        """Executes an agent workflow with bounded tools and persists the execution trace."""
        # 1. Tenancy validation: ensure user belongs to workspace
        membership = await WorkspaceService.get_membership(
            session, user_id=user.id, workspace_id=workspace_id
        )
        if membership is None:
            raise ForbiddenError("You are not a member of this workspace.")

        # 2. Conversation validation & history retrieval if specified
        history: list[dict[str, str]] = []
        conversation: Conversation | None = None
        if request.conversation_id:
            conversation = await ConversationService.get_conversation(
                session, request.conversation_id, workspace_id
            )
            if not conversation:
                raise NotFoundError("Specified conversation does not exist in this workspace.")

            for msg in conversation.messages:
                history.append({"role": msg.role, "content": msg.content})

        # 3. Instantiate or reuse AgentRunner
        effective_runner = runner or AgentRunner(
            llm_provider=get_llm_provider(),
            vector_store=vector_store,
        )

        # 4. Execute LangGraph workflow
        run_result = await effective_runner.run(
            query=request.query,
            workspace_id=workspace_id,
            user=user,
            conversation_id=request.conversation_id,
            allowed_tools=request.allowed_tools,
            history=history,
            session=session,
            max_steps=request.max_steps,
        )

        # 5. Persist AgentExecution record
        execution_id = uuid.uuid4()
        execution_record = AgentExecution(
            id=execution_id,
            workspace_id=workspace_id,
            user_id=user.id,
            conversation_id=request.conversation_id,
            query=request.query,
            status=run_result.status,
            final_response=run_result.final_response,
            steps_count=run_result.steps_count,
            total_latency_ms=run_result.total_latency_ms,
            trace=run_result.steps,
            error=run_result.error,
        )
        session.add(execution_record)

        # 6. If conversation is linked, persist user and assistant messages
        if conversation:
            user_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                conversation=conversation,
                workspace_id=workspace_id,
                role=MessageRole.USER.value,
                content=request.query.strip(),
                citations=[],
                metadata_={},
            )
            session.add(user_msg)

            assistant_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                conversation=conversation,
                workspace_id=workspace_id,
                role=MessageRole.ASSISTANT.value,
                content=run_result.final_response,
                citations=[],
                metadata_={
                    "agent_execution_id": str(execution_id),
                    "steps_count": run_result.steps_count,
                    "status": run_result.status,
                },
            )
            session.add(assistant_msg)

            if conversation.title == "New Conversation":
                first_q = request.query.strip()
                conversation.title = (first_q[:57] + "...") if len(first_q) > 60 else first_q
            conversation.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(execution_record)

        # 7. Build structured response
        trace_responses = [
            AgentStepResponse(
                step_index=s["step_index"],
                thought=s.get("thought", ""),
                action=s.get("action", "call_tool"),
                tool_name=s.get("tool_name"),
                tool_input=s.get("tool_input"),
                tool_result=s.get("tool_result"),
                error=s.get("error"),
                duration_ms=s.get("duration_ms", 0.0),
            )
            for s in run_result.steps
        ]

        return AgentExecutionResponse(
            execution_id=execution_record.id,
            workspace_id=execution_record.workspace_id,
            conversation_id=execution_record.conversation_id,
            query=execution_record.query,
            status=execution_record.status,
            final_response=execution_record.final_response,
            steps_count=execution_record.steps_count,
            total_latency_ms=execution_record.total_latency_ms,
            trace=trace_responses,
            error=execution_record.error,
            created_at=execution_record.created_at,
        )

    @staticmethod
    async def list_executions(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentExecutionSummary]:
        """Lists recent agent executions within a workspace for authorized members."""
        membership = await WorkspaceService.get_membership(
            session, user_id=user.id, workspace_id=workspace_id
        )
        if membership is None:
            raise ForbiddenError("You are not a member of this workspace.")

        stmt = (
            select(AgentExecution)
            .where(AgentExecution.workspace_id == workspace_id)
            .order_by(AgentExecution.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        executions = result.scalars().all()

        return [
            AgentExecutionSummary(
                execution_id=e.id,
                workspace_id=e.workspace_id,
                conversation_id=e.conversation_id,
                query=e.query,
                status=e.status,
                steps_count=e.steps_count,
                total_latency_ms=e.total_latency_ms,
                created_at=e.created_at,
            )
            for e in executions
        ]

    @staticmethod
    async def get_execution(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        execution_id: uuid.UUID,
        user: User,
    ) -> AgentExecutionResponse | None:
        """Retrieves a full execution record including trace, enforcing workspace boundary."""
        membership = await WorkspaceService.get_membership(
            session, user_id=user.id, workspace_id=workspace_id
        )
        if membership is None:
            raise ForbiddenError("You are not a member of this workspace.")

        stmt = select(AgentExecution).where(
            AgentExecution.id == execution_id,
            AgentExecution.workspace_id == workspace_id,
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return None

        trace_responses = [
            AgentStepResponse(
                step_index=s.get("step_index", idx),
                thought=s.get("thought", ""),
                action=s.get("action", "call_tool"),
                tool_name=s.get("tool_name"),
                tool_input=s.get("tool_input"),
                tool_result=s.get("tool_result"),
                error=s.get("error"),
                duration_ms=s.get("duration_ms", 0.0),
            )
            for idx, s in enumerate(record.trace, start=1)
        ]

        return AgentExecutionResponse(
            execution_id=record.id,
            workspace_id=record.workspace_id,
            conversation_id=record.conversation_id,
            query=record.query,
            status=record.status,
            final_response=record.final_response,
            steps_count=record.steps_count,
            total_latency_ms=record.total_latency_ms,
            trace=trace_responses,
            error=record.error,
            created_at=record.created_at,
        )

    @staticmethod
    async def delete_execution(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        execution_id: uuid.UUID,
        user: User,
    ) -> bool:
        """Deletes an agent execution record, enforcing workspace isolation."""
        membership = await WorkspaceService.get_membership(
            session, user_id=user.id, workspace_id=workspace_id
        )
        if membership is None:
            raise ForbiddenError("You are not a member of this workspace.")

        stmt = select(AgentExecution).where(
            AgentExecution.id == execution_id,
            AgentExecution.workspace_id == workspace_id,
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        await session.delete(record)
        await session.commit()
        return True
