from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.membership import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Workspace name")


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    role: WorkspaceRole | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberAddRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.MEMBER


class MemberUpdateRequest(BaseModel):
    role: WorkspaceRole


class MemberResponse(BaseModel):
    user_id: UUID
    email: str
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
