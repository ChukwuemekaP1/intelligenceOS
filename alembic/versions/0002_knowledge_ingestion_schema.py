"""knowledge ingestion schema (sources, documents, document_versions, chunks)

Revision ID: 0002_knowledge_ingestion_schema
Revises: 0001_initial_identity_schema
Create Date: 2026-10-04 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_knowledge_ingestion_schema"
down_revision: str | None = "0001_initial_identity_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Sources Table
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
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
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_sources_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_sources_id"), "sources", ["id"], unique=False)
    op.create_index(op.f("ix_sources_workspace_id"), "sources", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_sources_source_type"), "sources", ["source_type"], unique=False)
    op.create_index(op.f("ix_sources_name"), "sources", ["name"], unique=False)
    op.create_index(op.f("ix_sources_status"), "sources", ["status"], unique=False)

    # 2. Documents Table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
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
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_documents_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_documents_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(op.f("ix_documents_source_id"), "documents", ["source_id"], unique=False)
    op.create_index(op.f("ix_documents_workspace_id"), "documents", ["workspace_id"], unique=False)

    # 3. Document Versions Table
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id_documents",
            ondelete="CASCADE",
        ),
    )
    op.create_index(op.f("ix_document_versions_id"), "document_versions", ["id"], unique=False)
    op.create_index(
        op.f("ix_document_versions_document_id"), "document_versions", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_versions_storage_key"), "document_versions", ["storage_key"], unique=False
    )
    op.create_index(
        op.f("ix_document_versions_status"), "document_versions", ["status"], unique=False
    )

    # 4. Chunks Table
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
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
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_chunks_document_version_id_document_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_chunks_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_chunks_version_index",
        ),
    )
    op.create_index(op.f("ix_chunks_id"), "chunks", ["id"], unique=False)
    op.create_index(
        op.f("ix_chunks_document_version_id"), "chunks", ["document_version_id"], unique=False
    )
    op.create_index(op.f("ix_chunks_workspace_id"), "chunks", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_chunks_chunk_index"), "chunks", ["chunk_index"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chunks_chunk_index"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_workspace_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_version_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_id"), table_name="chunks")
    op.drop_table("chunks")

    op.drop_index(op.f("ix_document_versions_status"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_storage_key"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_id"), table_name="document_versions")
    op.drop_table("document_versions")

    op.drop_index(op.f("ix_documents_workspace_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_source_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")

    op.drop_index(op.f("ix_sources_status"), table_name="sources")
    op.drop_index(op.f("ix_sources_name"), table_name="sources")
    op.drop_index(op.f("ix_sources_source_type"), table_name="sources")
    op.drop_index(op.f("ix_sources_workspace_id"), table_name="sources")
    op.drop_index(op.f("ix_sources_id"), table_name="sources")
    op.drop_table("sources")
