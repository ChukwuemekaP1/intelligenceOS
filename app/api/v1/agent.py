"""API endpoints for LangGraph Agent execution, tool inspection, and trace retrieval."""

import uuid
from typing import Annotated, Any

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
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecutionResponse,
    AgentExecutionSummary,
)
from app.services.agent_service import AgentService
from app.tools.builtins import create_default_registry

router = APIRouter(
    prefix="/workspaces/{workspace_id}/agent",
    tags=["Agent & Tools Orchestration"],
)


@router.post(
    "/execute",
    response_model=AgentExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an agent task using LangGraph with approved tools",
)
async def execute_agent(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    request: AgentExecuteRequest,
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AgentExecutionResponse:
    """Executes the agent workflow within the authenticated workspace and persists trace."""
    return await AgentService.execute_agent(
        session=session,
        workspace_id=workspace_id,
        request=request,
        user=current_user,
    )


@router.get(
    "/executions",
    response_model=list[AgentExecutionSummary],
    status_code=status.HTTP_200_OK,
    summary="List recent agent executions for the workspace",
)
async def list_executions(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AgentExecutionSummary]:
    """Retrieves execution history records for observability and evaluation."""
    return await AgentService.list_executions(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=AgentExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect complete execution trace and tool invocation history",
)
async def get_execution_trace(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    execution_id: Annotated[uuid.UUID, Path(..., description="Target agent execution ID")],
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AgentExecutionResponse:
    """Retrieves full execution trace, including all intermediate steps and tool results."""
    execution = await AgentService.get_execution(
        session=session,
        workspace_id=workspace_id,
        execution_id=execution_id,
        user=current_user,
    )
    if not execution:
        raise NotFoundError("Agent execution record not found in this workspace.")
    return execution


@router.get(
    "/tools",
    response_model=list[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List available approved tools and their input schemas",
)
async def list_available_tools(
    workspace_id: Annotated[uuid.UUID, Path(..., description="Target workspace ID")],
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Returns tool descriptors and schemas available for this workspace."""
    registry = create_default_registry()
    return registry.get_descriptors()
