import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.models.membership import Membership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.services.auth_service import AuthService


class WorkspaceService:
    """Service handling workspace creation, membership management, and RBAC rules."""

    @staticmethod
    async def create_workspace(session: AsyncSession, name: str, owner: User) -> Workspace:
        workspace = Workspace(name=name.strip())
        session.add(workspace)
        await session.flush()

        # Workspace creator automatically becomes OWNER
        owner_membership = Membership(
            user_id=owner.id,
            workspace_id=workspace.id,
            role=WorkspaceRole.OWNER,
        )
        session.add(owner_membership)
        await session.flush()
        await session.refresh(workspace)
        return workspace

    @staticmethod
    async def list_user_workspaces(
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[tuple[Workspace, WorkspaceRole]]:
        stmt = (
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        )
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def get_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_membership(
        session: AsyncSession,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Membership | None:
        stmt = (
            select(Membership)
            .where(Membership.user_id == user_id, Membership.workspace_id == workspace_id)
            .options(selectinload(Membership.user), selectinload(Membership.workspace))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_workspace_members(
        session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> list[Membership]:
        stmt = (
            select(Membership)
            .where(Membership.workspace_id == workspace_id)
            .options(selectinload(Membership.user))
            .order_by(Membership.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_owners(session: AsyncSession, workspace_id: uuid.UUID) -> int:
        stmt = select(func.count(Membership.user_id)).where(
            Membership.workspace_id == workspace_id, Membership.role == WorkspaceRole.OWNER
        )
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def add_member(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        email: str,
        role: WorkspaceRole,
        acting_membership: Membership,
    ) -> Membership:
        # Authorization check: only OWNER or ADMIN can invite/add
        if acting_membership.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
            raise ForbiddenError("Only workspace owners and administrators can add members.")

        # ADMIN cannot grant OWNER role
        if acting_membership.role == WorkspaceRole.ADMIN and role == WorkspaceRole.OWNER:
            raise ForbiddenError("Administrators cannot grant owner privileges.")

        target_user = await AuthService.get_user_by_email(session, email)
        if target_user is None:
            raise NotFoundError(f"User with email '{email}' was not found.")

        existing = await WorkspaceService.get_membership(session, target_user.id, workspace_id)
        if existing is not None:
            raise ConflictError("User is already a member of this workspace.")

        membership = Membership(
            user_id=target_user.id,
            workspace_id=workspace_id,
            role=role,
        )
        session.add(membership)
        await session.flush()
        await session.refresh(membership)
        membership.user = target_user
        return membership

    @staticmethod
    async def update_member_role(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        target_user_id: uuid.UUID,
        new_role: WorkspaceRole,
        acting_membership: Membership,
    ) -> Membership:
        if acting_membership.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
            raise ForbiddenError(
                "Only workspace owners and administrators can update member roles."
            )

        if acting_membership.user_id == target_user_id:
            raise BadRequestError("You cannot modify your own workspace role.")

        target_membership = await WorkspaceService.get_membership(
            session, target_user_id, workspace_id
        )
        if target_membership is None:
            raise NotFoundError("Membership not found in this workspace.")

        # ADMIN restrictions
        if acting_membership.role == WorkspaceRole.ADMIN:
            if target_membership.role == WorkspaceRole.OWNER:
                raise ForbiddenError("Administrators cannot modify the role of an owner.")
            if new_role == WorkspaceRole.OWNER:
                raise ForbiddenError("Administrators cannot promote members to owner.")

        # If demoting an OWNER, ensure at least one other OWNER remains
        if target_membership.role == WorkspaceRole.OWNER and new_role != WorkspaceRole.OWNER:
            owner_count = await WorkspaceService.count_owners(session, workspace_id)
            if owner_count <= 1:
                raise BadRequestError("Cannot demote the only owner of the workspace.")

        user = target_membership.user
        target_membership.role = new_role
        await session.flush()
        target_membership.user = user
        return target_membership

    @staticmethod
    async def remove_member(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        target_user_id: uuid.UUID,
        acting_membership: Membership,
    ) -> None:
        target_membership = await WorkspaceService.get_membership(
            session, target_user_id, workspace_id
        )
        if target_membership is None:
            raise NotFoundError("Membership not found in this workspace.")

        is_self_leave = acting_membership.user_id == target_user_id

        # RBAC validation
        if not is_self_leave:
            if acting_membership.role == WorkspaceRole.MEMBER:
                raise ForbiddenError("Workspace members cannot remove other users.")
            if acting_membership.role == WorkspaceRole.ADMIN:
                if target_membership.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
                    raise ForbiddenError(
                        "Administrators cannot remove owners or other administrators."
                    )

        # Safety check: Cannot remove the last OWNER
        if target_membership.role == WorkspaceRole.OWNER:
            owner_count = await WorkspaceService.count_owners(session, workspace_id)
            if owner_count <= 1:
                raise BadRequestError("Cannot remove the only owner of the workspace.")

        await session.delete(target_membership)
        await session.flush()
