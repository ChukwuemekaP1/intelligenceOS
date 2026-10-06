"""Service managing conversation sessions, message persistence, and grounded RAG execution."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.user import User
from app.rag.pipeline import RAGPipeline
from app.schemas.rag import (
    ConversationCreate,
    MessageResponse,
    QuestionRequest,
    QuestionResponse,
)

logger = get_logger("app.services.conversation_service")


class ConversationService:
    """Handles conversation persistence, multi-turn message history, and RAG execution."""

    @staticmethod
    async def create_conversation(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        user: User | None = None,
        data: ConversationCreate | None = None,
    ) -> Conversation:
        """Creates a new conversation session strictly belonging to workspace_id."""
        title = (data.title if data and data.title else None) or "New Conversation"

        conversation = Conversation(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user.id if user else None,
            title=title,
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        logger.info(f"Created conversation '{conversation.id}' for workspace '{workspace_id}'.")
        return conversation

    @staticmethod
    async def list_conversations(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """Lists conversations belonging strictly to workspace_id."""
        stmt = (
            select(Conversation)
            .where(Conversation.workspace_id == workspace_id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_conversation(
        session: AsyncSession,
        conversation_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Conversation | None:
        """Retrieves a conversation by ID with messages loaded, enforcing workspace boundary."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
            .options(selectinload(Conversation.messages))
        )
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv is not None:
            await session.refresh(conv, ["messages"])
        return conv

    @staticmethod
    async def delete_conversation(
        session: AsyncSession,
        conversation_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> bool:
        """Deletes a conversation and cascaded messages, enforcing workspace boundary."""
        conversation = await ConversationService.get_conversation(
            session, conversation_id, workspace_id
        )
        if not conversation:
            return False

        await session.delete(conversation)
        await session.commit()
        logger.info(f"Deleted conversation '{conversation_id}' in workspace '{workspace_id}'.")
        return True

    @staticmethod
    async def ask_question(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        request: QuestionRequest,
        user: User | None = None,
        pipeline: RAGPipeline | None = None,
    ) -> QuestionResponse:
        """Executes full Grounded RAG pipeline and persists messages atomically."""
        # 1. Verify conversation exists and belongs to workspace
        conversation = await ConversationService.get_conversation(
            session, conversation_id, workspace_id
        )
        if not conversation:
            raise NotFoundError("Conversation not found in workspace.")

        # 2. Execute RAG pipeline
        rag_pipeline = pipeline or RAGPipeline(session=session)
        rag_result = await rag_pipeline.execute(
            workspace_id=workspace_id,
            query=request.question,
            retrieval_config=request.retrieval_config,
            source_ids=request.source_ids or None,
        )

        # 3. Persist User Message
        user_message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            conversation=conversation,
            workspace_id=workspace_id,
            role=MessageRole.USER.value,
            content=request.question.strip(),
            citations=[],
            metadata_={},
        )
        session.add(user_message)

        # 4. Persist Assistant Message with Citations and Evaluation Telemetry
        metrics_dict = rag_result.metrics.model_dump()
        assistant_message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            conversation=conversation,
            workspace_id=workspace_id,
            role=MessageRole.ASSISTANT.value,
            content=rag_result.answer,
            citations=[c.model_dump(mode="json") for c in rag_result.citations],
            metadata_={
                # Flat fields for easy frontend consumption
                "retrieval_latency_ms": metrics_dict.get("retrieval_latency_ms"),
                "chunks_retrieved": metrics_dict.get("retrieval_count"),
                "final_context_count": metrics_dict.get("final_context_count"),
                "total_latency_ms": metrics_dict.get("total_latency_ms"),
                "generation_latency_ms": metrics_dict.get("generation_latency_ms"),
                # Full nested metrics for evaluation tooling
                "metrics": metrics_dict,
                "rag_evaluation": rag_result.evaluation_payload.model_dump(mode="json"),
                # Scope info
                "source_ids_filter": [str(s) for s in request.source_ids] if request.source_ids else None,
            },
        )
        session.add(assistant_message)

        # 5. Update Conversation metadata (auto-title if default)
        if conversation.title == "New Conversation":
            first_q = request.question.strip()
            conversation.title = (first_q[:57] + "...") if len(first_q) > 60 else first_q

        conversation.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(user_message)
        await session.refresh(assistant_message)

        return QuestionResponse(
            conversation_id=conversation.id,
            user_message=MessageResponse.model_validate(user_message),
            assistant_message=MessageResponse.model_validate(assistant_message),
            answer=rag_result.answer,
            citations=rag_result.citations,
            metrics=rag_result.metrics,
        )
