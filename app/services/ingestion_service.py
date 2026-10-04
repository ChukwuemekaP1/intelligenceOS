"""Knowledge Ingestion Service.

Orchestrates the complete knowledge ingestion pipeline:
Source -> Parse -> Normalize -> Chunk -> Embed -> Qdrant

Enforces workspace isolation, idempotency on retries, clean failure reporting,
and separates storage references from PostgreSQL relational metadata.
"""

import re
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.ingestion.chunking.base import BaseChunker
from app.ingestion.chunking.deterministic import DeterministicChunker
from app.ingestion.parsers.base import ParserError
from app.ingestion.parsers.factory import get_parser
from app.ingestion.parsers.website import validate_safe_url
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import ProcessingStatus, Source, SourceType
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.factory import get_embedding_provider
from app.queue.job_queue import JobQueue, get_job_queue
from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend
from app.vectorstore.base import VectorStore
from app.vectorstore.factory import get_vector_store
from app.vectorstore.models import VectorPoint

logger = get_logger("app.services.ingestion")

# Allowed MIME types for file uploads
ALLOWED_MIME_TYPES = {
    "application/pdf": SourceType.PDF,
    "text/csv": SourceType.CSV,
    "application/vnd.ms-excel": SourceType.CSV,
    "text/plain": SourceType.CSV,  # Plain text csv uploads
    "image/png": SourceType.IMAGE,
    "image/jpeg": SourceType.IMAGE,
    "image/jpg": SourceType.IMAGE,
    "image/webp": SourceType.IMAGE,
    "image/tiff": SourceType.IMAGE,
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".pdf": SourceType.PDF,
    ".csv": SourceType.CSV,
    ".png": SourceType.IMAGE,
    ".jpg": SourceType.IMAGE,
    ".jpeg": SourceType.IMAGE,
    ".webp": SourceType.IMAGE,
    ".tiff": SourceType.IMAGE,
}


def sanitize_filename(filename: str) -> str:
    """Removes path traversal sequences, control characters, and unsafe symbols from filenames."""
    # Strip directory components
    clean = re.sub(r"[/\\]+", "", filename)
    # Remove control characters and limit charset
    clean = re.sub(r"[^\w\s\.-]", "_", clean).strip()
    return clean or "unnamed_file"


class IngestionService:
    """Coordinates knowledge source registration, background queuing, and pipeline execution."""

    @staticmethod
    def detect_source_type(filename: str, content_type: str | None = None) -> SourceType:
        """Determines the source type from file extension and MIME type.

        Raises:
            BadRequestError: If the file type is not supported.
        """
        # First check explicit MIME type if standard
        if content_type and content_type.lower() in ALLOWED_MIME_TYPES:
            return ALLOWED_MIME_TYPES[content_type.lower()]

        # Fallback to extension check
        lower_name = filename.lower()
        for ext, stype in ALLOWED_EXTENSIONS.items():
            if lower_name.endswith(ext):
                return stype

        raise BadRequestError(
            f"Unsupported format '{filename}'. Allowed formats: PDF, CSV, PNG, JPEG, WEBP, TIFF."
        )

    @staticmethod
    async def create_file_source(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        storage: StorageBackend | None = None,
        queue: JobQueue | None = None,
        settings: Settings | None = None,
    ) -> Source:
        """Registers an uploaded file, stores binary in storage, and enqueues processing.

        Flow:
          1. Validate file size and type.
          2. Sanitize filename and create storage reference key.
          3. Upload binary to S3/MinIO.
          4. Create Source, Document, and DocumentVersion records with PENDING status.
          5. Enqueue background ingestion job.
        """
        cfg = settings or get_settings()
        if len(content) > cfg.MAX_UPLOAD_SIZE_BYTES:
            max_mb = cfg.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise BadRequestError(
                f"Uploaded file exceeds the maximum permitted limit of {max_mb}MB."
            )

        if not content:
            raise BadRequestError("Uploaded file is empty.")

        source_type = IngestionService.detect_source_type(filename, content_type)
        safe_name = sanitize_filename(filename)
        source_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()

        # Object storage path: workspaces/{workspace_id}/sources/{source_id}/{safe_name}
        storage_key = f"workspaces/{workspace_id}/sources/{source_id}/{safe_name}"

        # 1. Persist raw binary to object storage
        storage_backend = storage or get_storage_backend(cfg)
        effective_mime = content_type or "application/octet-stream"
        await storage_backend.upload_file(
            key=storage_key,
            data=content,
            content_type=effective_mime,
        )

        # 2. Create PostgreSQL relational entities
        source = Source(
            id=source_id,
            workspace_id=workspace_id,
            source_type=source_type.value,
            name=safe_name,
            status=ProcessingStatus.PENDING.value,
            metadata_={
                "original_filename": filename,
                "file_size": len(content),
                "content_type": effective_mime,
            },
        )
        session.add(source)

        document = Document(
            id=doc_id,
            source_id=source_id,
            workspace_id=workspace_id,
            metadata_={
                "title": safe_name,
                "file_size": len(content),
            },
        )
        session.add(document)

        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            storage_key=storage_key,
            status=ProcessingStatus.PENDING.value,
        )
        session.add(version)

        await session.commit()
        await session.refresh(source)

        # 3. Enqueue background ingestion task
        job_queue = queue or get_job_queue(cfg)
        await job_queue.enqueue(
            job_type="ingestion",
            payload={
                "source_id": str(source_id),
                "workspace_id": str(workspace_id),
            },
        )

        logger.info(f"Registered file source '{source.id}' for workspace '{workspace_id}'")
        return source

    @staticmethod
    async def create_url_source(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        url: str,
        name: str | None = None,
        queue: JobQueue | None = None,
        settings: Settings | None = None,
    ) -> Source:
        """Registers a website URL source after SSRF validation, then enqueues processing."""
        cfg = settings or get_settings()

        # Enforce strict SSRF safety checks before storing
        try:
            validate_safe_url(url)
        except ParserError as exc:
            raise BadRequestError(f"URL validation failed: {exc}") from exc

        source_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()
        source_name = name.strip() if name and name.strip() else url

        source = Source(
            id=source_id,
            workspace_id=workspace_id,
            source_type=SourceType.WEBSITE.value,
            name=source_name,
            status=ProcessingStatus.PENDING.value,
            metadata_={"url": url},
        )
        session.add(source)

        document = Document(
            id=doc_id,
            source_id=source_id,
            workspace_id=workspace_id,
            metadata_={"url": url, "title": source_name},
        )
        session.add(document)

        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            storage_key=None,
            status=ProcessingStatus.PENDING.value,
        )
        session.add(version)

        await session.commit()
        await session.refresh(source)

        # Enqueue background ingestion task
        job_queue = queue or get_job_queue(cfg)
        await job_queue.enqueue(
            job_type="ingestion",
            payload={
                "source_id": str(source_id),
                "workspace_id": str(workspace_id),
            },
        )

        logger.info(f"Registered website source '{source.id}' for URL '{url}'")
        return source

    @staticmethod
    async def process_source_ingestion(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
        storage: StorageBackend | None = None,
        vector_store: VectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        chunker: BaseChunker | None = None,
    ) -> None:
        """Executes the asynchronous ingestion pipeline for a single source.

        Pipeline Stages:
          1. Transition state: PENDING -> PROCESSING
          2. Retrieve raw content from Object Storage or URL
          3. Parse raw data into canonical NormalizedDocument
          4. Chunk document into traceable segments
          5. Generate vector embeddings via EmbeddingProvider
          6. Idempotently write vectors to Qdrant (deleting previous version vectors)
          7. Persist Chunk relational entities to PostgreSQL
          8. Transition state: PROCESSING -> COMPLETED (or FAILED on error)
        """
        # Resolve dependencies
        cfg = get_settings()
        storage_backend = storage or get_storage_backend(cfg)
        vstore = vector_store or get_vector_store(cfg)
        embedder = embedding_provider or get_embedding_provider(cfg)
        doc_chunker = chunker or DeterministicChunker()

        # 1. Fetch Source and linked entities
        stmt = (
            select(Source)
            .where(Source.id == source_id, Source.workspace_id == workspace_id)
            .options(selectinload(Source.documents).selectinload(Document.versions))
        )
        result = await session.execute(stmt)
        source = result.scalar_one_or_none()

        if not source:
            logger.error(f"Source '{source_id}' not found in workspace '{workspace_id}'.")
            return

        # Locate latest document and version
        if not source.documents or not source.documents[0].versions:
            logger.error(f"No document version found for source '{source_id}'.")
            source.status = ProcessingStatus.FAILED.value
            source.metadata_ = dict(source.metadata_, error="No document version found")
            await session.commit()
            return

        doc = source.documents[0]
        version = doc.versions[-1]

        # Update status to PROCESSING
        source.status = ProcessingStatus.PROCESSING.value
        version.status = ProcessingStatus.PROCESSING.value
        await session.commit()

        try:
            # 2. Retrieve content
            content_bytes = b""
            parse_metadata: dict[str, Any] = {
                "source_id": str(source.id),
                "workspace_id": str(workspace_id),
                "filename": source.name,
                "url": source.metadata_.get("url"),
                **source.metadata_,
            }

            if version.storage_key:
                logger.info(f"Downloading object '{version.storage_key}' from storage...")
                content_bytes = await storage_backend.download_file(version.storage_key)

            # 3. Parse content into canonical NormalizedDocument
            parser = get_parser(source.source_type)
            norm_doc = await parser.parse(content_bytes, metadata=parse_metadata)
            logger.info(
                f"Parsed source '{source.id}' into {len(norm_doc.elements)} normalized elements."
            )

            # 4. Chunk document
            chunks_data = doc_chunker.chunk(
                document=norm_doc,
                workspace_id=workspace_id,
                source_id=source.id,
                document_id=doc.id,
                document_version_id=version.id,
            )

            if not chunks_data:
                raise ParserError("Ingestion produced zero text chunks.")

            logger.info(f"Generated {len(chunks_data)} chunks for source '{source.id}'.")

            # 5. Generate embeddings
            chunk_texts = [c.content for c in chunks_data]
            vectors = await embedder.embed_texts(chunk_texts)

            if len(vectors) != len(chunks_data):
                raise ValueError(
                    f"Vector count mismatch: generated {len(vectors)} embeddings "
                    f"for {len(chunks_data)} chunks."
                )

            # 6. Idempotently update Qdrant (remove previous vectors for this version if re-running)
            await vstore.ensure_collection()
            await vstore.delete_by_document_version(workspace_id, version.id)

            vector_points: list[VectorPoint] = []
            for c_data, vec in zip(chunks_data, vectors, strict=True):
                # Ensure all mandatory metadata payload fields exist
                payload = {
                    "workspace_id": str(workspace_id),
                    "source_id": str(source.id),
                    "document_id": str(doc.id),
                    "document_version_id": str(version.id),
                    "chunk_id": str(c_data.id),
                    "source_type": source.source_type,
                    "page_number": c_data.page_number,
                    "chunk_index": c_data.chunk_index,
                    "text": c_data.content,
                    **c_data.metadata,
                }
                vector_points.append(
                    VectorPoint(
                        id=c_data.id,
                        vector=vec,
                        payload=payload,
                    )
                )

            await vstore.upsert_points(workspace_id, vector_points)
            logger.info(f"Successfully upserted {len(vector_points)} points to vector store.")

            # 7. Persist Chunk entities in PostgreSQL
            # Remove any prior DB chunks for this version (guarantees idempotency on retry)
            await session.execute(delete(Chunk).where(Chunk.document_version_id == version.id))

            for c_data in chunks_data:
                db_chunk = Chunk(
                    id=c_data.id,
                    document_version_id=version.id,
                    workspace_id=workspace_id,
                    chunk_index=c_data.chunk_index,
                    content=c_data.content,
                    metadata_=c_data.metadata,
                )
                session.add(db_chunk)

            # 8. Mark as COMPLETED
            source.status = ProcessingStatus.COMPLETED.value
            version.status = ProcessingStatus.COMPLETED.value
            version.error_message = None
            source.metadata_ = dict(
                source.metadata_,
                total_chunks=len(chunks_data),
                title=norm_doc.title,
            )
            await session.commit()
            logger.info(f"Ingestion COMPLETED for source '{source.id}'.")

        except Exception as exc:
            await session.rollback()
            # Sanitize error message to avoid leaking internals
            error_msg = str(exc)[:500]
            logger.error(f"Ingestion FAILED for source '{source_id}': {error_msg}")

            # Re-fetch entities in a fresh transaction to record failure
            fail_stmt = (
                select(Source)
                .where(Source.id == source_id)
                .options(selectinload(Source.documents).selectinload(Document.versions))
            )
            fail_res = await session.execute(fail_stmt)
            fail_source = fail_res.scalar_one_or_none()

            if fail_source:
                fail_source.status = ProcessingStatus.FAILED.value
                fail_source.metadata_ = dict(fail_source.metadata_, error=error_msg)
                if fail_source.documents and fail_source.documents[0].versions:
                    fail_ver = fail_source.documents[0].versions[-1]
                    fail_ver.status = ProcessingStatus.FAILED.value
                    fail_ver.error_message = error_msg
                await session.commit()

    @staticmethod
    async def retry_ingestion(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
        queue: JobQueue | None = None,
    ) -> Source:
        """Re-enqueues a failed or pending source for ingestion."""
        source = await IngestionService.get_source(session, source_id, workspace_id)
        if not source:
            raise NotFoundError("Source not found in workspace.")

        source.status = ProcessingStatus.PENDING.value
        await session.commit()

        job_queue = queue or get_job_queue()
        await job_queue.enqueue(
            job_type="ingestion",
            payload={
                "source_id": str(source_id),
                "workspace_id": str(workspace_id),
            },
        )
        return source

    @staticmethod
    async def get_source(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Source | None:
        """Retrieves a source by ID enforcing workspace isolation."""
        stmt = select(Source).where(
            Source.id == source_id,
            Source.workspace_id == workspace_id,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_sources(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Source]:
        """Lists sources belonging to a specific workspace with pagination."""
        stmt = (
            select(Source)
            .where(Source.workspace_id == workspace_id)
            .order_by(Source.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_source_documents(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> list[Document]:
        """Returns documents and versions associated with a source."""
        stmt = (
            select(Document)
            .where(
                Document.source_id == source_id,
                Document.workspace_id == workspace_id,
            )
            .options(selectinload(Document.versions))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_source_chunks(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Chunk]:
        """Returns chunks generated for a source, enforcing workspace isolation."""
        stmt = (
            select(Chunk)
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.source_id == source_id,
                Chunk.workspace_id == workspace_id,
            )
            .order_by(Chunk.chunk_index.asc())
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
