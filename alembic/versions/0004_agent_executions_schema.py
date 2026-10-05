"""agent executions and traces schema for agent orchestration layer

Revision ID: 0004_agent_executions_schema
Revises: 0003_conversations_and_rag_schema
Create Date: 2026-10-04 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_agent_executions_schema"
down_revision: str | None = "0003_conversations_rag_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("final_response", sa.Text(), nullable=True),
        sa.Column("steps_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "trace",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_agent_executions_workspace_id", "agent_executions", ["workspace_id"], unique=False
    )
    op.create_index("ix_agent_executions_user_id", "agent_executions", ["user_id"], unique=False)
    op.create_index(
        "ix_agent_executions_conversation_id", "agent_executions", ["conversation_id"], unique=False
    )
    op.create_index("ix_agent_executions_status", "agent_executions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_executions_status", table_name="agent_executions")
    op.drop_index("ix_agent_executions_conversation_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_user_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_workspace_id", table_name="agent_executions")
    op.drop_table("agent_executions")
