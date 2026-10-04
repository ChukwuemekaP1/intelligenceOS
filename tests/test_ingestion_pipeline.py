"""End-to-end tests for the Knowledge Ingestion Pipeline.

Tests:
  - Ingestion flow: Source -> Parse -> Normalize -> Chunk -> Embed -> Qdrant
  - State transitions: PENDING -> PROCESSING -> COMPLETED
  - Storage persistence of original files
  - Chunks written to PostgreSQL
  - Vectors written to VectorStore with workspace metadata
  - Failure handling: FAILED status and sanitized error persistence
  - Idempotency: Retries do not produce duplicate vectors or database records
"""

import io

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunking.deterministic import DeterministicChunker
from app.models.source import ProcessingStatus, SourceType
from app.models.user import User
from app.models.workspace import Workspace
from app.providers.embedding.mock import MockEmbeddingProvider
from app.queue.job_queue import MockJobQueue
from app.schemas.auth import RegisterRequest
from app.services.auth_service import AuthService
from app.services.ingestion_service import IngestionService
from app.services.workspace_service import WorkspaceService
from app.storage.mock import MockStorageBackend
from app.vectorstore.mock import MockVectorStore


@pytest.fixture
def mock_storage() -> MockStorageBackend:
    return MockStorageBackend()


@pytest.fixture
def mock_vstore() -> MockVectorStore:
    return MockVectorStore()


@pytest.fixture
def mock_embedder() -> MockEmbeddingProvider:
    return MockEmbeddingProvider(dimension=768)


@pytest.fixture
def mock_queue() -> MockJobQueue:
    return MockJobQueue()


@pytest.fixture
async def sample_workspace(db_session: AsyncSession) -> tuple[Workspace, User]:
    user = await AuthService.register_user(
        db_session,
        RegisterRequest(email="ingest_user@example.com", password="securepassword123"),
    )
    workspace = await WorkspaceService.create_workspace(db_session, "Ingestion Workspace", user)
    return workspace, user


@pytest.mark.asyncio
async def test_csv_ingestion_pipeline_end_to_end(
    db_session: AsyncSession,
    sample_workspace: tuple[Workspace, User],
    mock_storage: MockStorageBackend,
    mock_vstore: MockVectorStore,
    mock_embedder: MockEmbeddingProvider,
    mock_queue: MockJobQueue,
) -> None:
    """Verifies complete successful ingestion path for CSV data."""
    workspace, _ = sample_workspace
    csv_bytes = b"id,name,role\n1,Alice,Engineer\n2,Bob,Product\n"

    # 1. Create file source
    source = await IngestionService.create_file_source(
        session=db_session,
        workspace_id=workspace.id,
        filename="team.csv",
        content=csv_bytes,
        content_type="text/csv",
        storage=mock_storage,
        queue=mock_queue,
    )
    assert source.status == ProcessingStatus.PENDING.value
    assert source.source_type == SourceType.CSV.value

    # Verify background job was queued
    assert await mock_queue.length() == 1
    job = await mock_queue.dequeue()
    assert job is not None
    assert job.payload["source_id"] == str(source.id)

    # Verify original file was stored in object storage
    docs = await IngestionService.get_source_documents(db_session, source.id, workspace.id)
    assert len(docs) == 1
    assert len(docs[0].versions) == 1
    storage_key = docs[0].versions[0].storage_key
    assert storage_key is not None
    stored_bytes = await mock_storage.download_file(storage_key)
    assert stored_bytes == csv_bytes

    # 2. Worker executes pipeline
    await IngestionService.process_source_ingestion(
        session=db_session,
        source_id=source.id,
        workspace_id=workspace.id,
        storage=mock_storage,
        vector_store=mock_vstore,
        embedding_provider=mock_embedder,
        chunker=DeterministicChunker(chunk_size=500),
    )

    # 3. Verify status transitioned to COMPLETED
    updated_source = await IngestionService.get_source(db_session, source.id, workspace.id)
    assert updated_source is not None
    assert updated_source.status == ProcessingStatus.COMPLETED.value
    assert updated_source.metadata_["total_chunks"] == 2

    # 4. Verify Chunks in PostgreSQL
    db_chunks = await IngestionService.get_source_chunks(db_session, source.id, workspace.id)
    assert len(db_chunks) == 2
    assert db_chunks[0].chunk_index == 0
    assert db_chunks[1].chunk_index == 1
    assert "Alice" in db_chunks[0].content

    # 5. Verify Vectors in Vector Store
    point_count = await mock_vstore.count_points(workspace.id)
    assert point_count == 2
    points = mock_vstore.get_points(workspace.id)
    assert len(points) == 2
    assert points[0].payload["workspace_id"] == str(workspace.id)
    assert points[0].payload["source_id"] == str(source.id)
    assert points[0].payload["source_type"] == "csv"


@pytest.mark.asyncio
async def test_image_ingestion_pipeline_with_mock_ocr(
    db_session: AsyncSession,
    sample_workspace: tuple[Workspace, User],
    mock_storage: MockStorageBackend,
    mock_vstore: MockVectorStore,
    mock_embedder: MockEmbeddingProvider,
    mock_queue: MockJobQueue,
) -> None:
    """Verifies that an image source undergoes storage, OCR, chunking, and embedding."""
    workspace, _ = sample_workspace

    # Create dummy PNG
    img = Image.new("RGB", (100, 100), color="blue")
    stream = io.BytesIO()
    img.save(stream, format="PNG")
    img_bytes = stream.getvalue()

    source = await IngestionService.create_file_source(
        session=db_session,
        workspace_id=workspace.id,
        filename="diagram.png",
        content=img_bytes,
        content_type="image/png",
        storage=mock_storage,
        queue=mock_queue,
    )
    # Add mock OCR text into source metadata for test OCR simulation
    source.metadata_ = dict(source.metadata_, mock_ocr_text="Architecture diagram nodes and edges.")
    await db_session.commit()

    # Process ingestion
    await IngestionService.process_source_ingestion(
        session=db_session,
        source_id=source.id,
        workspace_id=workspace.id,
        storage=mock_storage,
        vector_store=mock_vstore,
        embedding_provider=mock_embedder,
        chunker=DeterministicChunker(),
    )

    updated_source = await IngestionService.get_source(db_session, source.id, workspace.id)
    assert updated_source is not None
    assert updated_source.status == ProcessingStatus.COMPLETED.value

    chunks = await IngestionService.get_source_chunks(db_session, source.id, workspace.id)
    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert "Architecture diagram" in chunks[0].content


@pytest.mark.asyncio
async def test_ingestion_failure_handling(
    db_session: AsyncSession,
    sample_workspace: tuple[Workspace, User],
    mock_storage: MockStorageBackend,
    mock_vstore: MockVectorStore,
    mock_embedder: MockEmbeddingProvider,
    mock_queue: MockJobQueue,
) -> None:
    """Verifies that corrupted files transition to FAILED status with diagnostic info."""
    workspace, _ = sample_workspace

    # Corrupt PDF bytes
    corrupt_bytes = b"%PDF-corrupted-bytes-xyz"

    source = await IngestionService.create_file_source(
        session=db_session,
        workspace_id=workspace.id,
        filename="corrupt.pdf",
        content=corrupt_bytes,
        content_type="application/pdf",
        storage=mock_storage,
        queue=mock_queue,
    )

    await IngestionService.process_source_ingestion(
        session=db_session,
        source_id=source.id,
        workspace_id=workspace.id,
        storage=mock_storage,
        vector_store=mock_vstore,
        embedding_provider=mock_embedder,
    )

    failed_source = await IngestionService.get_source(db_session, source.id, workspace.id)
    assert failed_source is not None
    assert failed_source.status == ProcessingStatus.FAILED.value
    assert "error" in failed_source.metadata_

    docs = await IngestionService.get_source_documents(db_session, source.id, workspace.id)
    assert docs[0].versions[0].status == ProcessingStatus.FAILED.value
    assert docs[0].versions[0].error_message is not None


@pytest.mark.asyncio
async def test_ingestion_idempotency_on_retry(
    db_session: AsyncSession,
    sample_workspace: tuple[Workspace, User],
    mock_storage: MockStorageBackend,
    mock_vstore: MockVectorStore,
    mock_embedder: MockEmbeddingProvider,
    mock_queue: MockJobQueue,
) -> None:
    """Verifies that executing ingestion multiple times does not duplicate vectors or chunks."""
    workspace, _ = sample_workspace
    csv_bytes = b"id,name\n1,Alpha\n2,Beta\n"

    source = await IngestionService.create_file_source(
        session=db_session,
        workspace_id=workspace.id,
        filename="data.csv",
        content=csv_bytes,
        content_type="text/csv",
        storage=mock_storage,
        queue=mock_queue,
    )

    # Run ingestion first time
    await IngestionService.process_source_ingestion(
        session=db_session,
        source_id=source.id,
        workspace_id=workspace.id,
        storage=mock_storage,
        vector_store=mock_vstore,
        embedding_provider=mock_embedder,
    )

    chunks_first_run = await IngestionService.get_source_chunks(db_session, source.id, workspace.id)
    assert len(chunks_first_run) == 2
    assert await mock_vstore.count_points(workspace.id) == 2

    # Run ingestion second time (simulating a retry)
    await IngestionService.process_source_ingestion(
        session=db_session,
        source_id=source.id,
        workspace_id=workspace.id,
        storage=mock_storage,
        vector_store=mock_vstore,
        embedding_provider=mock_embedder,
    )

    chunks_second_run = await IngestionService.get_source_chunks(
        db_session, source.id, workspace.id
    )
    # Total chunks in PostgreSQL MUST still be exactly 2 (not 4!)
    assert len(chunks_second_run) == 2
    # Total points in vector store MUST still be exactly 2 (not 4!)
    assert await mock_vstore.count_points(workspace.id) == 2
