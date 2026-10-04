import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.membership import Membership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.services.auth_service import AuthService
from app.services.workspace_service import WorkspaceService

bearer_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that authenticates the caller via Bearer JWT and returns the User model."""
    if credentials is None:
        raise UnauthorizedError("Authentication token is missing.")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise UnauthorizedError("Invalid or expired authentication token.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError("Invalid token subject.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedError("Malformed user identifier in token.") from None

    user = await AuthService.get_user_by_id(session, user_id)
    if user is None:
        raise UnauthorizedError("User associated with this token no longer exists.")

    return user


async def get_active_workspace(
    workspace_id: uuid.UUID = Path(..., description="Target workspace ID"),
    session: AsyncSession = Depends(get_db),
) -> Workspace:
    """Dependency that resolves the active workspace from the path parameter."""
    workspace = await WorkspaceService.get_workspace(session, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found.")
    return workspace


async def get_workspace_membership(
    workspace: Workspace = Depends(get_active_workspace),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Membership:
    """Dependency that verifies the current user has membership in the active workspace."""
    membership = await WorkspaceService.get_membership(session, current_user.id, workspace.id)
    if membership is None:
        raise ForbiddenError("You are not a member of this workspace.")
    return membership


def require_workspace_role(
    *allowed_roles: WorkspaceRole,
) -> Callable[[Membership], Coroutine[Any, Any, Membership]]:
    """Dependency factory that enforces that the user's membership role is in allowed_roles."""

    async def role_checker(
        membership: Membership = Depends(get_workspace_membership),
    ) -> Membership:
        if membership.role not in allowed_roles:
            allowed_names = ", ".join(r.value for r in allowed_roles)
            raise ForbiddenError(f"Insufficient permissions. Required role: {allowed_names}.")
        return membership

    return role_checker
