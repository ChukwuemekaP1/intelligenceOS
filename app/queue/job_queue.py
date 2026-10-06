"""Redis-backed asynchronous Job Queue for background processing.

Decouples synchronous HTTP API endpoints from long-running ingestion pipelines.

The RedisJobQueue uses LPUSH (enqueue) and BRPOP (blocking dequeue) to implement
a reliable FIFO queue. The queue name is configurable via INGESTION_QUEUE_NAME.

Error handling:
- Credentials are never logged (@ character splits are sanitised before logging).
- All exceptions from Redis operations propagate to the caller for explicit handling.
- A queue_info() helper is provided for diagnostics/health endpoints.
"""

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.redis import get_redis_client

logger = get_logger("app.queue.job_queue")


class Job(BaseModel):
    """Represents a queued background task payload."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_type: str
    payload: dict[str, Any]
    created_at: float = Field(default_factory=time.time)


class JobQueue(ABC):
    """Abstract contract for background job queuing."""

    @abstractmethod
    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        """Enqueues a job payload for background processing.

        Returns:
            Unique job identifier string.

        Raises:
            Exception: If the enqueue operation fails (caller must handle).
        """
        ...

    @abstractmethod
    async def dequeue(self, timeout: int = 2) -> "Job | None":
        """Pulls the next job from the queue, blocking up to timeout seconds.

        Returns:
            Job instance or None if timeout expired with no jobs.
        """
        ...

    @abstractmethod
    async def length(self) -> int:
        """Returns the number of waiting jobs in the queue."""
        ...


class RedisJobQueue(JobQueue):
    """Production Redis-backed FIFO queue utilising LPUSH (enqueue) and BRPOP (dequeue).

    Using LPUSH + BRPOP gives a simple, reliable FIFO queue:
    - LPUSH pushes new jobs onto the left (head) of the list.
    - BRPOP pops from the right (tail), consuming the oldest job first.
    """

    def __init__(self, queue_name: str | None = None) -> None:
        settings = get_settings()
        self.queue_name = queue_name or settings.INGESTION_QUEUE_NAME

    @staticmethod
    def _sanitise_error(exc: Exception) -> str:
        """Strips Redis credentials from error messages before logging."""
        msg = str(exc)
        if "@" in msg:
            msg = msg.split("@")[-1]
        return msg

    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        """Pushes a new job to the left of the Redis list (LPUSH).

        Raises:
            Exception: Propagated from redis.asyncio on connection or command failure.
        """
        client = get_redis_client()
        job = Job(job_type=job_type, payload=payload)
        job_json = job.model_dump_json()

        try:
            await client.lpush(self.queue_name, job_json)
            logger.info(
                f"[QUEUE ENQUEUE] job_id={job.id} type='{job_type}' "
                f"queue='{self.queue_name}'"
            )
            return job.id
        except Exception as exc:
            safe_msg = self._sanitise_error(exc)
            logger.error(
                f"[QUEUE ENQUEUE FAILED] job_id={job.id} type='{job_type}' "
                f"queue='{self.queue_name}': {safe_msg}"
            )
            raise

    async def dequeue(self, timeout: int = 2) -> "Job | None":
        """Blocks up to timeout seconds waiting for a job from the right of the list (BRPOP).

        Returns:
            Job instance or None if the timeout expired.

        Raises:
            Exception: Propagated from redis.asyncio on connection failure.
        """
        client = get_redis_client()
        try:
            result = await client.brpop(self.queue_name, timeout=timeout)
            if not result:
                return None
            _queue, item_data = result
            data = json.loads(item_data)
            return Job(**data)
        except json.JSONDecodeError as exc:
            logger.error(
                f"[QUEUE DEQUEUE] Corrupt job payload — could not parse JSON: {exc}"
            )
            return None
        except Exception as exc:
            safe_msg = self._sanitise_error(exc)
            logger.error(
                f"[QUEUE DEQUEUE FAILED] queue='{self.queue_name}': {safe_msg}"
            )
            raise

    async def length(self) -> int:
        """Returns the current depth of the queue (number of pending jobs)."""
        client = get_redis_client()
        try:
            return await client.llen(self.queue_name)
        except Exception as exc:
            safe_msg = self._sanitise_error(exc)
            logger.warning(
                f"[QUEUE LENGTH FAILED] queue='{self.queue_name}': {safe_msg}"
            )
            return -1

    async def queue_info(self) -> dict[str, Any]:
        """Returns diagnostic information about the queue for health/debug endpoints."""
        try:
            depth = await self.length()
            return {
                "queue_name": self.queue_name,
                "depth": depth,
                "status": "ok" if depth >= 0 else "error",
            }
        except Exception as exc:
            return {
                "queue_name": self.queue_name,
                "depth": -1,
                "status": "error",
                "error": self._sanitise_error(exc),
            }


class MockJobQueue(JobQueue):
    """In-memory asyncio Queue for tests and local environments without Redis."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()

    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        job = Job(job_type=job_type, payload=payload)
        await self._queue.put(job)
        return job.id

    async def dequeue(self, timeout: int = 2) -> "Job | None":
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=float(timeout))
        except TimeoutError:
            return None

    async def length(self) -> int:
        return self._queue.qsize()


_job_queue_instance: JobQueue | None = None


def get_job_queue(settings: Settings | None = None) -> JobQueue:
    """Returns singleton JobQueue instance.

    - testing environment → MockJobQueue (no Redis required)
    - all other environments → RedisJobQueue
    """
    global _job_queue_instance
    if _job_queue_instance is not None:
        return _job_queue_instance

    if settings is None:
        settings = get_settings()

    if settings.ENVIRONMENT == "testing":
        _job_queue_instance = MockJobQueue()
    else:
        _job_queue_instance = RedisJobQueue(queue_name=settings.INGESTION_QUEUE_NAME)

    return _job_queue_instance


def reset_job_queue() -> None:
    """Resets the singleton job queue instance (for test teardown)."""
    global _job_queue_instance
    _job_queue_instance = None
