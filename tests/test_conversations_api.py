"""API integration tests for conversations and grounded RAG question answering."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import ProcessingStatus, Source, SourceType
from app.models.user import User
from app.models.workspace import Workspace
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.mock import MockLLMProvider
from app.services.auth_service import AuthService
from app.services.workspace_service import WorkspaceService
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.models import VectorPoint

_test_mock_vstore = MockVectorStore()


@pytest_asyncio.fixture(autouse=True)
async def setup_api_vectorstore(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None, None]:
    """Ensures MockVectorStore is used across conversation API tests."""
    global _test_mock_vstore
    _test_mock_vstore = MockVectorStore()
    from app.vectorstore import factory

    monkeypatch.setattr(factory, "_vector_store_instance", _test_mock_vstore)
    yield


@pytest.fixture
async def user_and_workspace(
    db_session: AsyncSession,
    auth_headers: Any,
) -> tuple[Workspace, User, dict[str, str]]:
    headers = await auth_headers("conv_user@example.com", "securepassword123")
    user = await AuthService.get_user_by_email(db_session, "conv_user@example.com")
    assert user is not None
    workspace = await WorkspaceService.create_workspace(db_session, "Conversations Space", user)
    return workspace, user, headers


@pytest.fixture
async def other_user_and_workspace(
    db_session: AsyncSession,
    auth_headers: Any,
) -> tuple[Workspace, User, dict[str, str]]:
    headers = await auth_headers("other_conv_user@example.com", "securepassword123")
    user = await AuthService.get_user_by_email(db_session, "other_conv_user@example.com")
    assert user is not None
    workspace = await WorkspaceService.create_workspace(db_session, "Other Space", user)
    return workspace, user, headers


@pytest.mark.asyncio
async def test_create_and_list_conversations(
    client: AsyncClient,
    user_and_workspace: tuple[Workspace, User, dict[str, str]],
) -> None:
    workspace, _, headers = user_and_workspace

    # 1. Create Conversation
    resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/conversations",
        json={"title": "Q3 Analysis Session"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    conv_data = resp.json()
    assert conv_data["title"] == "Q3 Analysis Session"
    assert conv_data["workspace_id"] == str(workspace.id)

    # 2. List Conversations
    list_resp = await client.get(
        f"/api/v1/workspaces/{workspace.id}/conversations",
        headers=headers,
    )
    assert list_resp.status_code == 200
    conversations = list_resp.json()
    assert len(conversations) == 1
    assert conversations[0]["id"] == conv_data["id"]


@pytest.mark.asyncio
async def test_conversation_authorization_cross_workspace(
    client: AsyncClient,
    user_and_workspace: tuple[Workspace, User, dict[str, str]],
    other_user_and_workspace: tuple[Workspace, User, dict[str, str]],
) -> None:
    """Verifies that users cannot access conversations in workspaces they do not belong to."""
    ws1, _, headers1 = user_and_workspace
    ws2, _, headers2 = other_user_and_workspace

    # User 1 creates conversation in WS 1
    resp = await client.post(
        f"/api/v1/workspaces/{ws1.id}/conversations",
        json={"title": "WS1 Confidential Chat"},
        headers=headers1,
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]

    # User 2 attempts to read WS 1 conversation using WS 1 path -> 403 Forbidden
    unauthorized_resp = await client.get(
        f"/api/v1/workspaces/{ws1.id}/conversations/{conv_id}",
        headers=headers2,
    )
    assert unauthorized_resp.status_code == 403

    # User 2 attempts to access WS 1 conversation through WS 2 path -> 404 Not Found
    spoofed_resp = await client.get(
        f"/api/v1/workspaces/{ws2.id}/conversations/{conv_id}",
        headers=headers2,
    )
    assert spoofed_resp.status_code == 404


@pytest.mark.asyncio
async def test_ask_question_api_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    user_and_workspace: tuple[Workspace, User, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies end-to-end API question answering flow with citations and message persistence."""
    workspace, _, headers = user_and_workspace

    # 1. Seed knowledge
    source = Source(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        source_type=SourceType.PDF.value,
        name="company_policy.pdf",
        status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(source)

    doc = Document(
        id=uuid.uuid4(),
        source_id=source.id,
        workspace_id=workspace.id,
        metadata_={"title": "company_policy.pdf"},
    )
    db_session.add(doc)

    doc_version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_number=1,
        status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(doc_version)

    chunk = Chunk(
        id=uuid.uuid4(),
        document_version_id=doc_version.id,
        workspace_id=workspace.id,
        chunk_index=0,
        content="Employees are granted 25 days of annual paid time off starting on day one.",
        metadata_={"page_number": 8, "source_name": "company_policy.pdf"},
    )
    db_session.add(chunk)
    await db_session.commit()

    # Index into vector store
    embedder = MockEmbeddingProvider(dimension=768)
    vec = await embedder.embed_query(chunk.content)

    await _test_mock_vstore.upsert_points(
        workspace_id=workspace.id,
        points=[
            VectorPoint(
                id=chunk.id,
                vector=vec,
                payload={
                    "workspace_id": str(workspace.id),
                    "source_id": str(source.id),
                    "document_id": str(doc.id),
                    "document_version_id": str(doc_version.id),
                    "chunk_id": str(chunk.id),
                    "source_type": source.source_type,
                    "source_name": source.name,
                    "page_number": 8,
                    "chunk_index": 0,
                    "text": chunk.content,
                },
            )
        ],
    )

    # Mock LLM and Embedder in RAGPipeline
    mock_llm = MockLLMProvider(
        default_response="According to [Doc 1], employees receive 25 days of annual paid time off."
    )
    monkeypatch.setattr("app.rag.pipeline.get_llm_provider", lambda *a, **kw: mock_llm)
    monkeypatch.setattr("app.rag.pipeline.get_embedding_provider", lambda *a, **kw: embedder)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_embedding_provider", lambda *a, **kw: embedder
    )
    monkeypatch.setattr("app.rag.pipeline.get_vector_store", lambda *a, **kw: _test_mock_vstore)
    monkeypatch.setattr(
        "app.rag.retrieval.service.get_vector_store", lambda *a, **kw: _test_mock_vstore
    )

    # 2. Create conversation
    create_resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/conversations",
        json={"title": "HR Questions"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # 3. Post Question
    question_resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/conversations/{conv_id}/messages",
        json={"question": "How many days of paid time off do employees get?"},
        headers=headers,
    )
    assert question_resp.status_code == 200, question_resp.text
    q_data = question_resp.json()

    assert "25 days of annual paid time off" in q_data["answer"]
    assert len(q_data["citations"]) == 1
    assert q_data["citations"][0]["source_name"] == "company_policy.pdf"
    assert q_data["citations"][0]["page_number"] == 8
    assert q_data["metrics"]["retrieval_count"] >= 1
    assert q_data["metrics"]["final_context_count"] >= 1

    # 4. Verify messages are persisted in conversation history
    detail_resp = await client.get(
        f"/api/v1/workspaces/{workspace.id}/conversations/{conv_id}",
        headers=headers,
    )
    assert detail_resp.status_code == 200
    history = detail_resp.json()
    assert len(history["messages"]) == 2
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][1]["role"] == "assistant"
    assert len(history["messages"][1]["citations"]) == 1


@pytest.mark.asyncio
async def test_delete_conversation(
    client: AsyncClient,
    user_and_workspace: tuple[Workspace, User, dict[str, str]],
) -> None:
    workspace, _, headers = user_and_workspace

    # Create conversation
    resp = await client.post(
        f"/api/v1/workspaces/{workspace.id}/conversations",
        json={"title": "To Delete"},
        headers=headers,
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]

    # Delete conversation
    del_resp = await client.delete(
        f"/api/v1/workspaces/{workspace.id}/conversations/{conv_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # Verify 404 when reading again
    get_resp = await client.get(
        f"/api/v1/workspaces/{workspace.id}/conversations/{conv_id}",
        headers=headers,
    )
    assert get_resp.status_code == 404
