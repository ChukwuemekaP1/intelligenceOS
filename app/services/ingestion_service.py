"""Knowledge Ingestion Service.

Orchestrates the complete knowledge ingestion pipeline:
  Source -> Parse -> Normalize -> Chunk -> Embed -> Qdrant

Key improvements over the original:
- Enqueue failure: if Redis enqueue fails after DB commit, source is immediately
  marked FAILED (not left stuck as PENDING forever).
- Retry with exponential backoff for transient Redis errors (3 attempts).
- Structured pipeline logs with [stage] prefixes for traceability.
- Clear distinction between transient infrastructure errors and permanent document errors.
- Error metadata stored in source.metadata_["error"] for frontend visibility.
- No execution path leaves a source in PROCESSING permanently — every path resolves
  to COMPLETED or FAILED.
"""

import asyncio
import re
import uuid
from datetime import UTC, datetime
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
    "text/plain": SourceType.TEXT,
    "text/markdown": SourceType.TEXT,
    "text/x-markdown": SourceType.TEXT,
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
    ".txt": SourceType.TEXT,
    ".md": SourceType.TEXT,
    ".markdown": SourceType.TEXT,
    ".png": SourceType.IMAGE,
    ".jpg": SourceType.IMAGE,
    ".jpeg": SourceType.IMAGE,
    ".webp": SourceType.IMAGE,
    ".tiff": SourceType.IMAGE,
}

# Maximum retry attempts for transient infrastructure errors during enqueue
_ENQUEUE_MAX_RETRIES = 3
_ENQUEUE_BACKOFF_BASE = 1.0  # seconds


def sanitize_filename(filename: str) -> str:
    """Removes path traversal sequences, control chars, and unsafe symbols from filenames."""
    clean = re.sub(r"[/\\]+", "", filename)
    clean = re.sub(r"[^\w\s\.-]", "_", clean).strip()
    return clean or "unnamed_file"


def _safe_error(exc: Exception) -> str:
    """Returns a truncated, safe error message without leaking credentials."""
    msg = str(exc)
    # Strip anything that looks like a password in a connection URL
    if "@" in msg:
        msg = msg.split("@")[-1]
    return msg[:500]


async def _enqueue_with_retry(
    job_queue: JobQueue,
    source_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Attempts to enqueue an ingestion job with exponential backoff retries.

    Raises:
        Exception: The last exception if all retry attempts are exhausted.
    """
    last_exc: Exception | None = None
    backoff = _ENQUEUE_BACKOFF_BASE

    for attempt in range(1, _ENQUEUE_MAX_RETRIES + 1):
        try:
            await job_queue.enqueue(
                job_type="ingestion",
                payload={
                    "source_id": str(source_id),
                    "workspace_id": str(workspace_id),
                },
            )
            if attempt > 1:
                logger.info(
                    f"[ENQUEUE] Succeeded on attempt {attempt} for source_id={source_id}"
                )
            return
        except Exception as exc:
            last_exc = exc
            safe_msg = _safe_error(exc)
            logger.warning(
                f"[ENQUEUE] Attempt {attempt}/{_ENQUEUE_MAX_RETRIES} failed "
                f"for source_id={source_id}: {safe_msg}"
            )
            if attempt < _ENQUEUE_MAX_RETRIES:
                await asyncio.sleep(backoff)
                backoff *= 2.0

    raise last_exc  # type: ignore[misc]


async def _mark_source_enqueue_failed(
    session: AsyncSession,
    source_id: uuid.UUID,
    error_msg: str,
) -> None:
    """Marks a source and its latest document version as FAILED after enqueue failure.

    This prevents sources from being stuck forever as PENDING when Redis is unavailable.
    """
    try:
        stmt = (
            select(Source)
            .where(Source.id == source_id)
            .options(selectinload(Source.documents).selectinload(Document.versions))
        )
        res = await session.execute(stmt)
        source = res.scalar_one_or_none()
        if source:
            source.status = ProcessingStatus.FAILED.value
            source.metadata_ = dict(
                source.metadata_,
                error=error_msg,
                error_code="enqueue_failed",
                failed_at=datetime.now(UTC).isoformat(),
            )
            if source.documents and source.documents[0].versions:
                ver = source.documents[0].versions[-1]
                ver.status = ProcessingStatus.FAILED.value
                ver.error_message = error_msg
            await session.commit()
            logger.error(
                f"[ENQUEUE FAILED] source_id={source_id} marked FAILED. "
                f"Reason: {error_msg}"
            )
    except Exception as db_exc:
        logger.error(
            f"[ENQUEUE FAILED] Could not update source {source_id} to FAILED "
            f"after enqueue failure: {db_exc}"
        )


class IngestionService:
    """Coordinates knowledge source registration, background queuing, and pipeline execution."""

    @staticmethod
    def detect_source_type(filename: str, content_type: str | None = None) -> SourceType:
        """Determines the source type from file extension and MIME type.

        Raises:
            BadRequestError: If the file type is not supported.
        """
        if content_type and content_type.lower() in ALLOWED_MIME_TYPES:
            return ALLOWED_MIME_TYPES[content_type.lower()]

        lower_name = filename.lower()
        for ext, stype in ALLOWED_EXTENSIONS.items():
            if lower_name.endswith(ext):
                return stype

        raise BadRequestError(
            f"Unsupported format '{filename}'. Allowed: PDF, CSV, TXT, MD, PNG, JPEG, WEBP, TIFF."
        )

    @staticmethod
    async def create_file_source(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        title: str | None = None,
        storage: StorageBackend | None = None,
        queue: JobQueue | None = None,
        settings: Settings | None = None,
    ) -> Source:
        """Registers an uploaded file, stores binary in storage, and enqueues processing.

        If Redis enqueue fails after DB commit, the source is immediately marked FAILED
        (never left stuck as PENDING).

        Flow:
          1. Validate file size and type.
          2. Sanitize filename and create storage key.
          3. Upload binary to Supabase Storage.
          4. Create Source, Document, DocumentVersion records (PENDING status).
          5. Enqueue background ingestion job with retries.
          6. On enqueue failure → mark source FAILED with error_code=enqueue_failed.
        """
        cfg = settings or get_settings()
        if len(content) > cfg.MAX_UPLOAD_SIZE_BYTES:
            max_mb = cfg.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise BadRequestError(
                f"Uploaded file exceeds the maximum permitted limit of {max_mb} MB."
            )

        if not content:
            raise BadRequestError("Uploaded file is empty.")

        source_type = IngestionService.detect_source_type(filename, content_type)
        safe_name = sanitize_filename(filename)
        display_name = title.strip() if title and title.strip() else safe_name
        source_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()

        storage_key = f"workspaces/{workspace_id}/sources/{source_id}/{safe_name}"

        # 1. Persist raw binary to object storage
        storage_backend = storage or get_storage_backend(cfg)
        effective_mime = content_type or "application/octet-stream"
        await storage_backend.upload_file(
            key=storage_key,
            data=content,
            content_type=effective_mime,
        )

        # 2. Create PostgreSQL relational entities (status=PENDING)
        source = Source(
            id=source_id,
            workspace_id=workspace_id,
            source_type=source_type.value,
            name=display_name,
            status=ProcessingStatus.PENDING.value,
            metadata_={
                "original_filename": filename,
                "file_size": len(content),
                "content_type": effective_mime,
                "title": display_name,
            },
        )
        session.add(source)

        document = Document(
            id=doc_id,
            source_id=source_id,
            workspace_id=workspace_id,
            metadata_={"title": display_name, "file_size": len(content)},
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

        logger.info(
            f"[SOURCE CREATED] source_id={source.id} workspace_id={workspace_id} "
            f"type={source_type.value} size={len(content)} name='{display_name}'"
        )

        # 3. Enqueue background ingestion task (with retries)
        job_queue = queue or get_job_queue(cfg)
        try:
            await _enqueue_with_retry(job_queue, source_id, workspace_id)
            logger.info(
                f"[SOURCE QUEUED] source_id={source.id} "
                f"queue={cfg.INGESTION_QUEUE_NAME}"
            )
        except Exception as exc:
            # Enqueue failed after all retries — mark the source immediately so
            # the frontend never sees a permanently stuck PENDING source.
            safe_msg = _safe_error(exc)
            enqueue_error = (
                f"Failed to queue ingestion job after {_ENQUEUE_MAX_RETRIES} attempts. "
                f"Check Redis connectivity. Detail: {safe_msg}"
            )
            await _mark_source_enqueue_failed(session, source_id, enqueue_error)
            await session.refresh(source)
            # Return the source in FAILED state — the API will return 202 with failed status
            # so the frontend can immediately display "Processing failed — please retry"
            logger.error(
                f"[ENQUEUE FAILED] source_id={source.id} "
                f"workspace_id={workspace_id}: {enqueue_error}"
            )

        return source

    @staticmethod
    async def create_url_source(
        session: AsyncSession,
        workspace_id: uuid.UUID,
        url: str,
        name: str | None = None,
        title: str | None = None,
        queue: JobQueue | None = None,
        settings: Settings | None = None,
    ) -> Source:
        """Registers a website URL source after SSRF validation, then enqueues processing.

        If Redis enqueue fails after DB commit, the source is immediately marked FAILED.
        """
        cfg = settings or get_settings()

        try:
            validate_safe_url(url)
        except ParserError as exc:
            raise BadRequestError(f"URL validation failed: {exc}") from exc

        source_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()
        raw_name = title if (title and title.strip()) else name
        source_name = raw_name.strip() if raw_name and raw_name.strip() else url

        source = Source(
            id=source_id,
            workspace_id=workspace_id,
            source_type=SourceType.WEBSITE.value,
            name=source_name,
            status=ProcessingStatus.PENDING.value,
            metadata_={"url": url, "title": source_name},
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

        logger.info(
            f"[SOURCE CREATED] source_id={source.id} workspace_id={workspace_id} "
            f"type=website url='{url}'"
        )

        # Enqueue background ingestion task (with retries)
        job_queue = queue or get_job_queue(cfg)
        try:
            await _enqueue_with_retry(job_queue, source_id, workspace_id)
            logger.info(
                f"[SOURCE QUEUED] source_id={source.id} "
                f"queue={cfg.INGESTION_QUEUE_NAME}"
            )
        except Exception as exc:
            safe_msg = _safe_error(exc)
            enqueue_error = (
                f"Failed to queue ingestion job after {_ENQUEUE_MAX_RETRIES} attempts. "
                f"Check Redis connectivity. Detail: {safe_msg}"
            )
            await _mark_source_enqueue_failed(session, source_id, enqueue_error)
            await session.refresh(source)
            logger.error(
                f"[ENQUEUE FAILED] source_id={source.id} "
                f"workspace_id={workspace_id}: {enqueue_error}"
            )

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
        """Executes the full asynchronous ingestion pipeline for a single source.

        Every execution path resolves to COMPLETED or FAILED — no path leaves
        the source permanently in PROCESSING.

        Pipeline Stages:
          1. PENDING → PROCESSING
          2. Retrieve raw content (Storage or URL)
          3. Parse → NormalizedDocument
          4. Chunk → ChunkData list
          5. Embed → float vectors
          6. Qdrant upsert (idempotent)
          7. Persist Chunk DB records
          8. PROCESSING → COMPLETED  (or FAILED on any error)
        """
        cfg = get_settings()
        storage_backend = storage or get_storage_backend(cfg)
        vstore = vector_store or get_vector_store(cfg)
        embedder = embedding_provider or get_embedding_provider(cfg)
        doc_chunker = chunker or DeterministicChunker()

        # --- Stage 1: Load Source ---
        stmt = (
            select(Source)
            .where(Source.id == source_id, Source.workspace_id == workspace_id)
            .options(selectinload(Source.documents).selectinload(Document.versions))
        )
        result = await session.execute(stmt)
        source = result.scalar_one_or_none()

        if not source:
            logger.error(
                f"[PIPELINE] Source '{source_id}' not found in workspace '{workspace_id}'. "
                f"Aborting."
            )
            return

        if source.status == ProcessingStatus.CANCELLED.value:
            logger.info(
                f"[PIPELINE] source_id={source_id} is CANCELLED — skipping ingestion."
            )
            return

        if not source.documents or not source.documents[0].versions:
            logger.error(
                f"[PIPELINE] No document/version for source_id={source_id} — marking FAILED."
            )
            source.status = ProcessingStatus.FAILED.value
            source.metadata_ = dict(
                source.metadata_,
                error="No document version found",
                error_code="missing_document_version",
                failed_at=datetime.now(UTC).isoformat(),
            )
            await session.commit()
            return

        doc = source.documents[0]
        version = doc.versions[-1]

        # --- Stage 2: Transition to PROCESSING ---
        source.status = ProcessingStatus.PROCESSING.value
        version.status = ProcessingStatus.PROCESSING.value
        await session.commit()

        logger.info(
            f"[PIPELINE START] source_id={source_id} type={source.source_type} "
            f"workspace_id={workspace_id} name='{source.name}'"
        )

        try:
            # --- Stage 3: Retrieve content ---
            content_bytes = b""
            parse_metadata: dict[str, Any] = {
                "source_id": str(source.id),
                "workspace_id": str(workspace_id),
                "filename": source.name,
                "url": source.metadata_.get("url"),
                **source.metadata_,
            }

            if version.storage_key:
                logger.info(
                    f"[RETRIEVE] Downloading from storage: key='{version.storage_key}'"
                )
                content_bytes = await storage_backend.download_file(version.storage_key)
                logger.info(
                    f"[RETRIEVE] Retrieved: key='{version.storage_key}' "
                    f"bytes={len(content_bytes)}"
                )
            else:
                logger.info(
                    f"[RETRIEVE] URL source — parser will fetch: "
                    f"url='{source.metadata_.get('url')}'"
                )

            # --- Stage 4: Parse ---
            parser = get_parser(source.source_type)
            norm_doc = await parser.parse(content_bytes, metadata=parse_metadata)
            char_count = norm_doc.total_characters
            logger.info(
                f"[EXTRACT] source_id={source_id} "
                f"type={source.source_type} "
                f"title='{norm_doc.title}' "
                f"elements={len(norm_doc.elements)} "
                f"chars={char_count}"
            )

            # Guard: empty extraction is a permanent failure (not a transient error)
            if not norm_doc.elements or char_count == 0:
                raise ParserError(
                    f"No text could be extracted from this {source.source_type} source. "
                    f"For PDFs, scanned images require OCR. "
                    f"For URLs, the page may be empty or JavaScript-rendered."
                )

            # --- Stage 5: Chunk ---
            chunks_data = doc_chunker.chunk(
                document=norm_doc,
                workspace_id=workspace_id,
                source_id=source.id,
                document_id=doc.id,
                document_version_id=version.id,
            )

            if not chunks_data:
                raise ParserError("Ingestion produced zero text chunks.")

            logger.info(
                f"[CHUNK] source_id={source_id} "
                f"chunk_count={len(chunks_data)}"
            )

            # --- Stage 6: Embed ---
            chunk_texts = [c.content for c in chunks_data]
            vectors = await embedder.embed_texts(chunk_texts)

            if len(vectors) != len(chunks_data):
                raise ValueError(
                    f"Vector count mismatch: {len(vectors)} embeddings for "
                    f"{len(chunks_data)} chunks."
                )

            # Validate that we actually got non-empty vectors
            if not vectors or not vectors[0]:
                raise ValueError("Embedding provider returned empty vectors.")

            logger.info(
                f"[EMBED] source_id={source_id} "
                f"embedding_count={len(vectors)} "
                f"dimension={len(vectors[0])}"
            )

            # Dimension sanity check vs Qdrant collection config
            expected_dim = cfg.EMBEDDING_DIMENSION
            actual_dim = len(vectors[0])
            if actual_dim != expected_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: got {actual_dim}, "
                    f"expected {expected_dim} (EMBEDDING_DIMENSION in config). "
                    f"Update EMBEDDING_DIMENSION or recreate the Qdrant collection."
                )

            # --- Stage 7: Qdrant upsert (idempotent) ---
            await vstore.ensure_collection()
            await vstore.delete_by_document_version(workspace_id, version.id)

            vector_points: list[VectorPoint] = []
            for c_data, vec in zip(chunks_data, vectors, strict=True):
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
                    VectorPoint(id=c_data.id, vector=vec, payload=payload)
                )

            await vstore.upsert_points(workspace_id, vector_points)
            logger.info(
                f"[QDRANT] source_id={source_id} "
                f"workspace_id={workspace_id} "
                f"vectors_upserted={len(vector_points)}"
            )

            # --- Stage 8: Persist Chunk records ---
            await session.execute(
                delete(Chunk).where(Chunk.document_version_id == version.id)
            )
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

            # --- Stage 9: Mark COMPLETED ---
            source.status = ProcessingStatus.COMPLETED.value
            version.status = ProcessingStatus.COMPLETED.value
            version.error_message = None
            source.metadata_ = dict(
                source.metadata_,
                total_chunks=len(chunks_data),
                total_characters=char_count,
                document_count=1,
                title=norm_doc.title,
                completed_at=datetime.now(UTC).isoformat(),
                # Clear any stale error info from prior failed attempts
                error=None,
                error_code=None,
            )
            await session.commit()
            logger.info(
                f"[PIPELINE COMPLETE] source_id={source_id} "
                f"type={source.source_type} "
                f"chunks={len(chunks_data)} "
                f"chars={char_count} "
                f"vectors={len(vector_points)}"
            )

        except Exception as exc:
            await session.rollback()
            error_msg = _safe_error(exc)
            error_code = _classify_error(exc)

            logger.error(
                f"[PIPELINE FAILED] source_id={source_id} "
                f"error_code={error_code} "
                f"error={error_msg}",
                exc_info=True,
            )

            # Re-fetch in a fresh transaction to record failure
            try:
                fail_stmt = (
                    select(Source)
                    .where(Source.id == source_id)
                    .options(
                        selectinload(Source.documents).selectinload(Document.versions)
                    )
                )
                fail_res = await session.execute(fail_stmt)
                fail_source = fail_res.scalar_one_or_none()

                if fail_source:
                    fail_source.status = ProcessingStatus.FAILED.value
                    fail_source.metadata_ = dict(
                        fail_source.metadata_,
                        error=error_msg,
                        error_code=error_code,
                        failed_at=datetime.now(UTC).isoformat(),
                    )
                    if fail_source.documents and fail_source.documents[0].versions:
                        fail_ver = fail_source.documents[0].versions[-1]
                        fail_ver.status = ProcessingStatus.FAILED.value
                        fail_ver.error_message = error_msg
                    await session.commit()

                    # Observability metric
                    try:
                        from app.observability.metrics import record_ingestion_failure
                        record_ingestion_failure(fail_source.source_type, type(exc).__name__)
                    except Exception:
                        pass

            except Exception as db_exc:
                logger.error(
                    f"[PIPELINE FAILED] Could not persist failure status for "
                    f"source_id={source_id}: {db_exc}"
                )

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

        # Allow retry from FAILED or PENDING (but not PROCESSING or COMPLETED)
        if source.status == ProcessingStatus.PROCESSING.value:
            raise BadRequestError(
                "Source is currently being processed. Cancel it first to retry."
            )

        cfg = get_settings()
        job_queue = queue or get_job_queue(cfg)

        source.status = ProcessingStatus.PENDING.value
        # Clear prior error state
        source.metadata_ = dict(
            source.metadata_,
            error=None,
            error_code=None,
            failed_at=None,
        )
        await session.commit()

        try:
            await _enqueue_with_retry(job_queue, source_id, workspace_id)
            logger.info(
                f"[RETRY QUEUED] source_id={source_id} workspace_id={workspace_id}"
            )
        except Exception as exc:
            safe_msg = _safe_error(exc)
            enqueue_error = (
                f"Retry enqueue failed after {_ENQUEUE_MAX_RETRIES} attempts: {safe_msg}"
            )
            await _mark_source_enqueue_failed(session, source_id, enqueue_error)
            await session.refresh(source)
            logger.error(
                f"[RETRY ENQUEUE FAILED] source_id={source_id}: {enqueue_error}"
            )

        return source

    @staticmethod
    async def cancel_source(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> Source:
        """Cancels an active or pending source ingestion."""
        source = await IngestionService.get_source(session, source_id, workspace_id)
        if not source:
            raise NotFoundError("Source not found in workspace.")

        if source.status in (ProcessingStatus.PENDING.value, ProcessingStatus.PROCESSING.value):
            source.status = ProcessingStatus.CANCELLED.value
            source.metadata_ = dict(
                source.metadata_,
                cancelled=True,
                cancelled_at=datetime.now(UTC).isoformat(),
            )
            await session.commit()
            await session.refresh(source)
            logger.info(f"[CANCEL] Cancelled ingestion for source_id={source_id}")
        return source

    @staticmethod
    async def delete_source(
        session: AsyncSession,
        source_id: uuid.UUID,
        workspace_id: uuid.UUID,
        storage: StorageBackend | None = None,
        vector_store: VectorStore | None = None,
        settings: Settings | None = None,
    ) -> bool:
        """Deletes a source, purging object storage files, Qdrant vectors, and DB records."""
        cfg = settings or get_settings()
        storage_backend = storage or get_storage_backend(cfg)
        vstore = vector_store or get_vector_store(cfg)

        stmt = (
            select(Source)
            .where(Source.id == source_id, Source.workspace_id == workspace_id)
            .options(selectinload(Source.documents).selectinload(Document.versions))
        )
        res = await session.execute(stmt)
        source = res.scalar_one_or_none()
        if not source:
            return False

        # 1. Purge Qdrant vectors
        try:
            await vstore.ensure_collection()
            await vstore.delete_by_source(workspace_id, source_id)
        except Exception as e:
            logger.warning(f"[DELETE] Could not purge vectors for source_id={source_id}: {e}")

        # 2. Purge object storage
        for doc in source.documents:
            for ver in doc.versions:
                if ver.storage_key:
                    try:
                        await storage_backend.delete_file(ver.storage_key)
                    except Exception as e:
                        logger.warning(
                            f"[DELETE] Could not delete storage key "
                            f"'{ver.storage_key}': {e}"
                        )

        # 3. Delete DB record (cascades to documents, versions, chunks)
        await session.delete(source)
        await session.commit()
        logger.info(
            f"[DELETE] Permanently deleted source_id={source_id} "
            f"workspace_id={workspace_id}"
        )
        return True

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
        """Lists sources for a workspace with pagination."""
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
        """Returns chunks for a source, enforcing workspace isolation."""
        from app.models.document_version import DocumentVersion

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


def _classify_error(exc: Exception) -> str:
    """Maps an exception to a stable, user-facing error code.

    Distinguishes permanent document errors (won't recover with a retry) from
    transient infrastructure errors (may recover).
    """
    exc_name = type(exc).__name__
    msg_lower = str(exc).lower()

    # Permanent / document-level errors
    if isinstance(exc, ParserError):
        if "password" in msg_lower or "encrypted" in msg_lower:
            return "pdf_encrypted"
        if "no extractable text" in msg_lower or "extraction" in msg_lower:
            return "extraction_failed"
        if "empty" in msg_lower:
            return "empty_document"
        if "http" in msg_lower or "status code" in msg_lower:
            return "url_fetch_failed"
        if "dns" in msg_lower or "resolve" in msg_lower:
            return "url_dns_failed"
        if "timeout" in msg_lower and "http" in msg_lower:
            return "url_timeout"
        if "zero chunk" in msg_lower or "no extractable" in msg_lower:
            return "no_chunks"
        return "parse_failed"

    if "dimension mismatch" in msg_lower:
        return "embedding_dimension_mismatch"

    if "mismatch" in msg_lower and "vector" in msg_lower:
        return "embedding_count_mismatch"

    # Transient infrastructure errors
    if "qdrant" in msg_lower or "vectorstore" in exc_name.lower():
        return "qdrant_error"

    if "embedding" in exc_name.lower() or "embedding" in msg_lower:
        if "auth" in msg_lower or "key" in msg_lower:
            return "embedding_auth_failed"
        if "rate" in msg_lower or "quota" in msg_lower:
            return "embedding_rate_limit"
        return "embedding_error"

    if "storage" in msg_lower or "supabase" in msg_lower:
        return "storage_error"

    if "redis" in msg_lower or "connection" in msg_lower:
        return "redis_error"

    return "pipeline_error"
