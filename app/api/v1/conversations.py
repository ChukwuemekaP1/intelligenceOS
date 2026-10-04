"""API endpoints for Workspace Conversations and Grounded RAG Question Answering.

Enforces workspace tenant isolation, membership authorization, and persistent conversation history.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_workspace_membership,
)
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.models.membership import Membership
from app.models.user import User
from app.schemas.rag import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    QuestionRequest,
    QuestionResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/conversations",
    tags=["Conversations & RAG"],
)


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation in the workspace",
)
async def create_conversation(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    data: ConversationCreate | None = None,
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Initializes a new conversation session partitioned strictly by workspace_id."""
    conversation = await ConversationService.create_conversation(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        data=data,
    )
    return ConversationResponse.model_validate(conversation)


@router.get(
    "",
    response_model=list[ConversationResponse],
    summary="List all conversations in the workspace",
)
async def list_conversations(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    limit: Annotated[int, Query(ge=1, le=100, description="Page limit")] = 50,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    """Retrieves conversation sessions belonging to the specified workspace."""
    conversations = await ConversationService.list_conversations(
        session=session,
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
    )
    return [ConversationResponse.model_validate(c) for c in conversations]


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation history by ID",
)
async def get_conversation(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    conversation_id: Annotated[uuid.UUID, Path(..., description="Conversation ID")],
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Returns conversation details along with full message history and citations."""
    conversation = await ConversationService.get_conversation(
        session=session,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )
    if not conversation:
        raise NotFoundError("Conversation not found in workspace.")

    return ConversationDetailResponse(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in conversation.messages],
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=QuestionResponse,
    summary="Send a question and execute grounded RAG pipeline",
)
@router.post(
    "/{conversation_id}/question",
    response_model=QuestionResponse,
    include_in_schema=False,
)
async def ask_question(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    conversation_id: Annotated[uuid.UUID, Path(..., description="Conversation ID")],
    request: QuestionRequest,
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Executes the complete RAG question-answering pipeline:

    Question -> Retrieval -> Reranking -> Context -> LLM Generation -> Citations -> Persistence.
    """
    return await ConversationService.ask_question(
        session=session,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        request=request,
        user=current_user,
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and its messages",
)
async def delete_conversation(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    conversation_id: Annotated[uuid.UUID, Path(..., description="Conversation ID")],
    current_user: User = Depends(get_current_user),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Permanently deletes a conversation and its cascaded message records."""
    success = await ConversationService.delete_conversation(
        session=session,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )
    if not success:
        raise NotFoundError("Conversation not found in workspace.")
