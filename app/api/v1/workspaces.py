import uuid

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_workspace_membership,
    require_workspace_role,
)
from app.database.session import get_db
from app.models.membership import Membership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import (
    MemberAddRequest,
    MemberResponse,
    MemberUpdateRequest,
    WorkspaceCreate,
    WorkspaceResponse,
)
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
)
async def create_workspace(
    request: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Creates a workspace and assigns the creating user as OWNER."""
    workspace = await WorkspaceService.create_workspace(session, request.name, current_user)
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        role=WorkspaceRole.OWNER,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.get(
    "",
    response_model=list[WorkspaceResponse],
    status_code=status.HTTP_200_OK,
    summary="List workspaces for current user",
)
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[WorkspaceResponse]:
    """Returns all workspaces where the current user holds membership."""
    items = await WorkspaceService.list_user_workspaces(session, current_user.id)
    return [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            role=role,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        )
        for ws, role in items
    ]


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get workspace details",
)
async def get_workspace(
    membership: Membership = Depends(get_workspace_membership),
) -> WorkspaceResponse:
    """Returns details of a specific workspace (requires membership)."""
    ws: Workspace = membership.workspace
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        role=membership.role,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


@router.get(
    "/{workspace_id}/members",
    response_model=list[MemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List members of a workspace",
)
async def list_workspace_members(
    workspace_id: uuid.UUID = Path(...),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> list[MemberResponse]:
    """Lists all members of the workspace (accessible to OWNER, ADMIN, and MEMBER)."""
    members = await WorkspaceService.list_workspace_members(session, workspace_id)
    return [
        MemberResponse(
            user_id=m.user_id,
            email=m.user.email,
            role=m.role,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in members
    ]


@router.post(
    "/{workspace_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member to the workspace",
)
async def add_workspace_member(
    request: MemberAddRequest,
    workspace_id: uuid.UUID = Path(...),
    membership: Membership = Depends(
        require_workspace_role(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    session: AsyncSession = Depends(get_db),
) -> MemberResponse:
    """Adds a new member to the workspace (restricted to OWNER and ADMIN)."""
    new_member = await WorkspaceService.add_member(
        session=session,
        workspace_id=workspace_id,
        email=request.email,
        role=request.role,
        acting_membership=membership,
    )
    return MemberResponse(
        user_id=new_member.user_id,
        email=new_member.user.email,
        role=new_member.role,
        created_at=new_member.created_at,
        updated_at=new_member.updated_at,
    )


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a member's role",
)
async def update_member_role(
    request: MemberUpdateRequest,
    workspace_id: uuid.UUID = Path(...),
    user_id: uuid.UUID = Path(...),
    membership: Membership = Depends(
        require_workspace_role(WorkspaceRole.OWNER, WorkspaceRole.ADMIN)
    ),
    session: AsyncSession = Depends(get_db),
) -> MemberResponse:
    """Updates a member's role in the workspace (restricted to OWNER and ADMIN)."""
    updated_member = await WorkspaceService.update_member_role(
        session=session,
        workspace_id=workspace_id,
        target_user_id=user_id,
        new_role=request.role,
        acting_membership=membership,
    )
    return MemberResponse(
        user_id=updated_member.user_id,
        email=updated_member.user.email,
        role=updated_member.role,
        created_at=updated_member.created_at,
        updated_at=updated_member.updated_at,
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the workspace",
)
async def remove_workspace_member(
    workspace_id: uuid.UUID = Path(...),
    user_id: uuid.UUID = Path(...),
    membership: Membership = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Removes a member from the workspace (OWNER/ADMIN or self-removal)."""
    await WorkspaceService.remove_member(
        session=session,
        workspace_id=workspace_id,
        target_user_id=user_id,
        acting_membership=membership,
    )
