"""Tests for Vector Store and Workspace Isolation."""

import uuid

import pytest

from app.vectorstore.base import VectorStoreError
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.models import VectorPoint


@pytest.mark.asyncio
async def test_mock_vector_store_workspace_isolation() -> None:
    """Verifies that vector store strictly segregates points by workspace."""
    vstore = MockVectorStore()

    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()

    point_a = VectorPoint(
        id=uuid.uuid4(),
        vector=[0.1] * 768,
        payload={"workspace_id": str(ws_a), "source_type": "pdf", "text": "Doc A"},
    )
    point_b = VectorPoint(
        id=uuid.uuid4(),
        vector=[0.2] * 768,
        payload={"workspace_id": str(ws_b), "source_type": "website", "text": "Doc B"},
    )

    # Upsert to respective workspaces
    await vstore.upsert_points(ws_a, [point_a])
    await vstore.upsert_points(ws_b, [point_b])

    assert await vstore.count_points(ws_a) == 1
    assert await vstore.count_points(ws_b) == 1

    # Attempt to upsert point_a into ws_b (should trigger workspace isolation violation)
    cross_point = VectorPoint(
        id=uuid.uuid4(),
        vector=[0.3] * 768,
        payload={"workspace_id": str(ws_a), "text": "Cross tenant breach"},
    )
    with pytest.raises(VectorStoreError, match="Workspace isolation violation"):
        await vstore.upsert_points(ws_b, [cross_point])


@pytest.mark.asyncio
async def test_mock_vector_store_deletion_by_version_and_source() -> None:
    """Verifies that vector deletions scoped to a workspace do not affect other workspaces."""
    vstore = MockVectorStore()

    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    src_a = uuid.uuid4()
    ver_a1 = uuid.uuid4()
    ver_a2 = uuid.uuid4()

    pt_a1 = VectorPoint(
        id=uuid.uuid4(),
        vector=[0.1] * 768,
        payload={
            "workspace_id": str(ws_a),
            "source_id": str(src_a),
            "document_version_id": str(ver_a1),
        },
    )
    pt_a2 = VectorPoint(
        id=uuid.uuid4(),
        vector=[0.2] * 768,
        payload={
            "workspace_id": str(ws_a),
            "source_id": str(src_a),
            "document_version_id": str(ver_a2),
        },
    )
    pt_b = VectorPoint(
        id=uuid.uuid4(),
        vector=[0.3] * 768,
        payload={
            "workspace_id": str(ws_b),
            "source_id": str(uuid.uuid4()),
            "document_version_id": str(uuid.uuid4()),
        },
    )

    await vstore.upsert_points(ws_a, [pt_a1, pt_a2])
    await vstore.upsert_points(ws_b, [pt_b])

    assert await vstore.count_points(ws_a) == 2
    assert await vstore.count_points(ws_b) == 1

    # Delete ver_a1 in ws_a
    await vstore.delete_by_document_version(ws_a, ver_a1)
    assert await vstore.count_points(ws_a) == 1
    # Verify ws_b was not touched
    assert await vstore.count_points(ws_b) == 1

    # Delete all from src_a in ws_a
    await vstore.delete_by_source(ws_a, src_a)
    assert await vstore.count_points(ws_a) == 0
    assert await vstore.count_points(ws_b) == 1
