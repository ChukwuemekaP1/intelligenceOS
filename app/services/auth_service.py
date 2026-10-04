import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

settings = get_settings()


class AuthService:
    """Service handling user registration, authentication, and token issuance."""

    @staticmethod
    async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower().strip())
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def register_user(session: AsyncSession, request: RegisterRequest) -> User:
        clean_email = request.email.lower().strip()
        existing = await AuthService.get_user_by_email(session, clean_email)
        if existing is not None:
            raise ConflictError("A user with this email address already exists.")

        user = User(
            email=clean_email,
            password_hash=get_password_hash(request.password),
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user

    @staticmethod
    async def authenticate_user(session: AsyncSession, request: LoginRequest) -> TokenResponse:
        clean_email = request.email.lower().strip()
        user = await AuthService.get_user_by_email(session, clean_email)
        if user is None or not verify_password(request.password, user.password_hash):
            raise UnauthorizedError("Invalid email or password.")

        access_token = create_access_token(subject=user.id)
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
