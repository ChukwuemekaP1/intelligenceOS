"""Service managing conversation sessions, message persistence, and grounded RAG execution.

Key improvements:
- Conversation history is now passed to the RAG pipeline for proper multi-turn context.
  The last N turns (bounded) are serialised and injected into the LLM prompt.
- retrieval_mode_used and insufficient_knowledge are stored in assistant message metadata
  so the frontend can display accurate retrieval state.
- History is bounded to the last 12 messages (6 turns) to avoid token overflow.
"""

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

# Maximum number of prior messages to include in the LLM history context.
# 12 messages = 6 full user/assistant turns.
_MAX_HISTORY_MESSAGES = 12


def _build_history(messages: list[Message]) -> list[dict]:
    """Converts the most recent N messages into the format expected by the RAG prompt builder.

    Returns a list of {"role": "user"|"assistant", "content": "..."} dicts,
    ordered oldest-first, bounded to _MAX_HISTORY_MESSAGES.
    """
    if not messages:
        return []

    # Sort by created_at ascending (oldest first) and take the last N
    sorted_msgs = sorted(messages, key=lambda m: m.created_at)
    recent = sorted_msgs[-_MAX_HISTORY_MESSAGES:]

    history = []
    for msg in recent:
        role = msg.role  # "user" or "assistant"
        content = (msg.content or "").strip()
        if content:
            history.append({"role": role, "content": content})

    return history


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

        logger.info(
            f"[CONVERSATION] Created conversation_id={conversation.id} "
            f"workspace_id={workspace_id}"
        )
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
        logger.info(
            f"[CONVERSATION] Deleted conversation_id={conversation_id} "
            f"workspace_id={workspace_id}"
        )
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
        """Executes full Grounded RAG pipeline and persists messages atomically.

        The conversation history (excluding the current question) is passed to the
        RAG pipeline so the LLM can resolve follow-up references and maintain context
        across multiple turns.
        """
        # 1. Verify conversation exists and belongs to workspace
        conversation = await ConversationService.get_conversation(
            session, conversation_id, workspace_id
        )
        if not conversation:
            raise NotFoundError("Conversation not found in workspace.")

        # 2. Build conversation history from prior messages
        #    We exclude the current question (not yet persisted) — it is already in the query.
        prior_messages = list(conversation.messages) if conversation.messages else []
        conversation_history = _build_history(prior_messages)

        logger.info(
            f"[RAG REQUEST] conversation_id={conversation_id} "
            f"workspace_id={workspace_id} "
            f"history_turns={len(conversation_history)} "
            f"question_chars={len(request.question)}"
        )

        # 3. Execute RAG pipeline with conversation history
        rag_pipeline = pipeline or RAGPipeline(session=session)
        rag_result = await rag_pipeline.execute(
            workspace_id=workspace_id,
            query=request.question,
            retrieval_config=request.retrieval_config,
            source_ids=request.source_ids or None,
            conversation_history=conversation_history if conversation_history else None,
        )

        logger.info(
            f"[RAG RESULT] conversation_id={conversation_id} "
            f"retrieval_count={rag_result.metrics.retrieval_count} "
            f"context_count={rag_result.metrics.final_context_count} "
            f"insufficient_knowledge={rag_result.insufficient_knowledge} "
            f"retrieval_mode={rag_result.retrieval_mode_used} "
            f"total_ms={rag_result.metrics.total_latency_ms}"
        )

        # 4. Persist User Message
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

        # 5. Persist Assistant Message with Citations and Evaluation Telemetry
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
                # Retrieval state — visible to frontend
                "retrieval_mode_used": rag_result.retrieval_mode_used,
                "insufficient_knowledge": rag_result.insufficient_knowledge,
                # Source filter scope
                "source_ids_filter": (
                    [str(s) for s in request.source_ids] if request.source_ids else None
                ),
                # Full nested metrics for evaluation tooling
                "metrics": metrics_dict,
                "rag_evaluation": rag_result.evaluation_payload.model_dump(mode="json"),
            },
        )
        session.add(assistant_message)

        # 6. Update Conversation metadata (auto-title if still default)
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
            retrieval_mode_used=rag_result.retrieval_mode_used,
            insufficient_knowledge=rag_result.insufficient_knowledge,
        )
