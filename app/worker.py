"""Background Worker for processing knowledge ingestion jobs.

Listens to the Redis ingestion queue, orchestrates parsing, normalisation, chunking,
embedding, vector storage, and state persistence.

Run as a standalone process:
    python -m app.worker

Structured log traces every significant event with job_id, source_id, and workspace_id
so that the complete lifecycle of any job can be reconstructed from logs.

Stale-job detection:  if a source has been in PROCESSING status for longer than
STALE_JOB_THRESHOLD_SECONDS it is eligible for automatic retry or failure marking.
"""

import asyncio
import signal
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database.redis import check_redis_health, close_redis
from app.database.session import async_session_factory, engine
from app.models.document import Document
from app.models.source import ProcessingStatus, Source
from app.queue.job_queue import get_job_queue
from app.services.ingestion_service import IngestionService

settings = get_settings()
setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
logger = get_logger("app.worker")

# A source stuck in PROCESSING for longer than this is considered stale
STALE_JOB_THRESHOLD_SECONDS: int = settings.WORKER_STALE_THRESHOLD_SECONDS
# How often the worker scans for stale jobs (seconds)
STALE_SCAN_INTERVAL_SECONDS: int = settings.WORKER_STALE_SCAN_INTERVAL_SECONDS

_last_stale_scan: datetime = datetime.min.replace(tzinfo=UTC)


async def _verify_redis_connection() -> bool:
    """Checks Redis connectivity at startup and logs a clear diagnostic message."""
    logger.info("Verifying Redis connection...")
    ok = await check_redis_health()
    if ok:
        logger.info("Redis connection verified successfully.")
    else:
        logger.error(
            "Redis connection FAILED. "
            "Check REDIS_URL in .env and ensure the Redis host is reachable."
        )
    return ok


async def process_next_job() -> bool:
    """Dequeues and executes a single background job.

    Returns:
        True if a job was found and executed, False if the queue was empty.
    """
    queue = get_job_queue(settings)

    try:
        job = await queue.dequeue(timeout=2)
    except Exception as exc:
        err = str(exc)
        if "@" in err:
            err = err.split("@")[-1]
        logger.error(f"[WORKER] Failed to dequeue from Redis: {err}")
        return False

    if job is None:
        return False

    logger.info(
        f"[JOB RECEIVED] job_id={job.id} type={job.job_type} "
        f"created_at={job.created_at}"
    )

    if job.job_type == "ingestion":
        source_id_str = job.payload.get("source_id")
        workspace_id_str = job.payload.get("workspace_id")

        if not source_id_str or not workspace_id_str:
            logger.error(
                f"[JOB MALFORMED] job_id={job.id}: "
                f"missing source_id or workspace_id in payload={job.payload}"
            )
            return True

        try:
            source_id = uuid.UUID(source_id_str)
            workspace_id = uuid.UUID(workspace_id_str)
        except ValueError:
            logger.error(
                f"[JOB MALFORMED] job_id={job.id}: "
                f"invalid UUID — source_id='{source_id_str}' workspace_id='{workspace_id_str}'"
            )
            return True

        logger.info(
            f"[PROCESSING START] job_id={job.id} "
            f"source_id={source_id} workspace_id={workspace_id}"
        )

        async with async_session_factory() as session:
            try:
                await IngestionService.process_source_ingestion(
                    session=session,
                    source_id=source_id,
                    workspace_id=workspace_id,
                )
                logger.info(
                    f"[JOB COMPLETED] job_id={job.id} "
                    f"source_id={source_id} workspace_id={workspace_id}"
                )
            except Exception as exc:
                # process_source_ingestion handles its own failure status update.
                # Log here for worker-level visibility.
                logger.error(
                    f"[JOB FAILED] job_id={job.id} "
                    f"source_id={source_id} workspace_id={workspace_id} "
                    f"error={type(exc).__name__}: {str(exc)[:300]}",
                    exc_info=True,
                )

    else:
        logger.warning(
            f"[JOB UNKNOWN TYPE] job_id={job.id} type={job.job_type} — skipping."
        )

    return True


async def _mark_stale_sources_failed() -> None:
    """Finds sources stuck in PROCESSING longer than the stale threshold and marks them FAILED.

    This is a safety net for cases where the worker died mid-job without updating status.
    We only mark sources as FAILED — we do NOT automatically retry, because retrying
    without understanding why the job died could cause infinite loops.
    """
    global _last_stale_scan

    now = datetime.now(UTC)
    if (now - _last_stale_scan).total_seconds() < STALE_SCAN_INTERVAL_SECONDS:
        return

    _last_stale_scan = now
    stale_cutoff = now - timedelta(seconds=STALE_JOB_THRESHOLD_SECONDS)

    logger.info(
        f"[STALE SCAN] Scanning for sources stuck in PROCESSING "
        f"since before {stale_cutoff.isoformat()}"
    )

    try:
        async with async_session_factory() as session:
            stmt = (
                select(Source)
                .where(Source.status == ProcessingStatus.PROCESSING.value)
                .options(selectinload(Source.documents).selectinload(Document.versions))
            )
            result = await session.execute(stmt)
            stale_candidates = result.scalars().all()

            stale_count = 0
            for source in stale_candidates:
                # Use updated_at as the staleness reference.
                # If the ORM timestamp is timezone-naive, normalise it.
                updated = source.updated_at
                if updated is None:
                    continue
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)

                if updated < stale_cutoff:
                    stale_count += 1
                    error_msg = (
                        f"Job exceeded maximum processing time "
                        f"({STALE_JOB_THRESHOLD_SECONDS}s). "
                        f"Marked failed by stale-job monitor."
                    )
                    source.status = ProcessingStatus.FAILED.value
                    source.metadata_ = dict(
                        source.metadata_,
                        error=error_msg,
                        stale_detected_at=now.isoformat(),
                    )
                    if source.documents:
                        for doc in source.documents:
                            for ver in doc.versions:
                                if ver.status == ProcessingStatus.PROCESSING.value:
                                    ver.status = ProcessingStatus.FAILED.value
                                    ver.error_message = error_msg

                    logger.warning(
                        f"[STALE SOURCE] source_id={source.id} "
                        f"workspace_id={source.workspace_id} "
                        f"last_updated={updated.isoformat()} "
                        f"→ marked FAILED"
                    )

            if stale_count:
                await session.commit()
                logger.info(f"[STALE SCAN] Marked {stale_count} stale source(s) as FAILED.")
            else:
                logger.info("[STALE SCAN] No stale sources found.")

    except Exception as exc:
        logger.error(f"[STALE SCAN] Error during stale job scan: {exc}", exc_info=True)


async def run_worker(stop_event: asyncio.Event | None = None) -> None:
    """Main worker loop that processes queued jobs until signalled to terminate."""
    logger.info("=" * 60)
    logger.info("[WORKER STARTED] IntelligenceOS background ingestion worker starting...")
    logger.info(f"[WORKER CONFIG] queue={settings.INGESTION_QUEUE_NAME}")
    logger.info(f"[WORKER CONFIG] stale_threshold={STALE_JOB_THRESHOLD_SECONDS}s")
    logger.info(f"[WORKER CONFIG] stale_scan_interval={STALE_SCAN_INTERVAL_SECONDS}s")
    logger.info("=" * 60)

    is_stopping = stop_event or asyncio.Event()

    # Register OS signals if in the main thread (POSIX only)
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, is_stopping.set)
    except (NotImplementedError, RuntimeError):
        # Windows or non-main thread — signal handling not supported
        pass

    # Verify Redis connectivity before entering the main loop
    redis_ok = await _verify_redis_connection()
    if not redis_ok:
        logger.error(
            "[WORKER ABORTED] Cannot connect to Redis. "
            "Fix REDIS_URL in .env and restart the worker."
        )
        return

    logger.info("[WORKER READY] Waiting for ingestion jobs...")

    idle_iters = 0
    try:
        while not is_stopping.is_set():
            try:
                # Check for stale jobs periodically
                await _mark_stale_sources_failed()

                processed = await process_next_job()
                if processed:
                    idle_iters = 0
                else:
                    idle_iters += 1
                    # Sleep longer when queue has been empty for a while to reduce Redis load
                    sleep_secs = min(0.5 * (1 + idle_iters // 20), 5.0)
                    await asyncio.sleep(sleep_secs)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    f"[WORKER LOOP ERROR] Unhandled exception in worker loop: {exc}",
                    exc_info=True,
                )
                await asyncio.sleep(2.0)

    finally:
        logger.info("[WORKER SHUTDOWN] Closing Redis and database connections...")
        await close_redis()
        await engine.dispose()
        logger.info("[WORKER SHUTDOWN] Worker gracefully terminated.")


if __name__ == "__main__":
    asyncio.run(run_worker())
