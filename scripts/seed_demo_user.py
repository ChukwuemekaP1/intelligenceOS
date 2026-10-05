"""Seed script to ensure default demo login credentials and initial workspace exist."""

import asyncio

from sqlalchemy import select

from app.core.security import get_password_hash, verify_password
from app.database.session import async_session_factory
from app.models.membership import Membership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace

DEMO_EMAIL = "admin@intelligence.os"
DEMO_PASSWORD = "IntelligenceOS2026!"
DEFAULT_WORKSPACE_NAME = "IntelligenceOS Primary Workspace"


async def seed_demo_user():
    async with async_session_factory() as session:
        # Check if user already exists
        stmt = select(User).where(User.email == DEMO_EMAIL)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=DEMO_EMAIL,
                password_hash=get_password_hash(DEMO_PASSWORD),
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)
            print(f"Created demo user: {DEMO_EMAIL}")
        else:
            # Update password hash if needed
            if not verify_password(DEMO_PASSWORD, user.password_hash):
                user.password_hash = get_password_hash(DEMO_PASSWORD)
                await session.flush()
                print(f"Updated password hash for: {DEMO_EMAIL}")
            else:
                print(f"Demo user already exists with matching password: {DEMO_EMAIL}")

        # Check if user has a workspace
        ws_stmt = (
            select(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user.id)
        )
        ws_result = await session.execute(ws_stmt)
        workspace = ws_result.scalars().first()

        if workspace is None:
            workspace = Workspace(name=DEFAULT_WORKSPACE_NAME)
            session.add(workspace)
            await session.flush()

            membership = Membership(
                user_id=user.id,
                workspace_id=workspace.id,
                role=WorkspaceRole.OWNER,
            )
            session.add(membership)
            await session.flush()
            await session.commit()
            print(f"Created default workspace: '{DEFAULT_WORKSPACE_NAME}' (ID: {workspace.id})")
        else:
            await session.commit()
            print(f"Existing workspace found: '{workspace.name}' (ID: {workspace.id})")

    print("\n--- DEMO LOGIN CREDENTIALS READY ---")
    print(f"Email:    {DEMO_EMAIL}")
    print(f"Password: {DEMO_PASSWORD}")
    print("------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(seed_demo_user())
