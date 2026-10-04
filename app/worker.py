"""Background Worker for processing knowledge ingestion jobs.

Listens to the Redis ingestion queue, orchestrates parsing, normalization, chunking,
embedding, vector storage, and state persistence.
Can be run as a standalone process via: python -m app.worker
"""

import asyncio
import signal
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database.redis import close_redis
from app.database.session import async_session_factory, engine
from app.queue.job_queue import get_job_queue
from app.services.ingestion_service import IngestionService

settings = get_settings()
setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
logger = get_logger("app.worker")


async def process_next_job() -> bool:
    """Dequeues and executes a single background job.

    Returns:
        True if a job was found and executed, False if the queue was empty.
    """
    queue = get_job_queue(settings)
    job = await queue.dequeue(timeout=2)
    if job is None:
        return False

    logger.info(f"Worker picked up job {job.id} of type '{job.job_type}'")

    if job.job_type == "ingestion":
        source_id_str = job.payload.get("source_id")
        workspace_id_str = job.payload.get("workspace_id")

        if not source_id_str or not workspace_id_str:
            logger.error(f"Malformed job payload in {job.id}: missing source_id or workspace_id")
            return True

        source_id = uuid.UUID(source_id_str)
        workspace_id = uuid.UUID(workspace_id_str)

        async with async_session_factory() as session:
            try:
                await IngestionService.process_source_ingestion(
                    session=session,
                    source_id=source_id,
                    workspace_id=workspace_id,
                )
            except Exception as exc:
                logger.error(f"Error processing ingestion job {job.id}: {exc}", exc_info=True)

    return True


async def run_worker(stop_event: asyncio.Event | None = None) -> None:
    """Main worker loop that processes queued jobs until signaled to terminate."""
    logger.info("Starting IntelligenceOS background ingestion worker...")
    is_stopping = stop_event or asyncio.Event()

    # Register OS signals if in main thread
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, is_stopping.set)
    except (NotImplementedError, RuntimeError):
        # Windows or non-main thread might not support add_signal_handler
        pass

    try:
        while not is_stopping.is_set():
            try:
                processed = await process_next_job()
                if not processed:
                    # Give control back to event loop on idle queue
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Worker loop exception: {exc}")
                await asyncio.sleep(1.0)
    finally:
        logger.info("Shutting down worker connections...")
        await close_redis()
        await engine.dispose()
        logger.info("Worker gracefully terminated.")


if __name__ == "__main__":
    asyncio.run(run_worker())
