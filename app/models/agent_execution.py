"""Agent execution entity representing an orchestrated multi-tool workflow run."""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User
    from app.models.workspace import Workspace


class ExecutionStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


class AgentExecution(Base, TimestampMixin):
    """Represents a bounded LangGraph agent execution trace."""

    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default=ExecutionStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    final_response: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    steps_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_latency_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Detailed structured execution trace:
    # [{"step_index": 1, "thought": "...", "tool_name": "...", "duration_ms": 15.2}]
    trace: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace")
    user: Mapped["User | None"] = relationship("User")
    conversation: Mapped["Conversation | None"] = relationship("Conversation")
