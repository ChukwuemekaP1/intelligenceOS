"""Redis-backed asynchronous Job Queue for background processing.

Decouples synchronous HTTP API endpoints from long-running ingestion pipelines.
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
        """
        pass

    @abstractmethod
    async def dequeue(self, timeout: int = 2) -> Job | None:
        """Pulls the next job from the queue, blocking up to timeout seconds.

        Returns:
            Job instance or None if timeout expired with no jobs.
        """
        pass

    @abstractmethod
    async def length(self) -> int:
        """Returns the number of waiting jobs in the queue."""
        pass


class RedisJobQueue(JobQueue):
    """Production Redis-backed FIFO queue utilizing LPUSH and BRPOP."""

    def __init__(self, queue_name: str | None = None) -> None:
        settings = get_settings()
        self.queue_name = queue_name or settings.INGESTION_QUEUE_NAME

    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        client = get_redis_client()
        job = Job(job_type=job_type, payload=payload)
        job_json = job.model_dump_json()

        try:
            await client.lpush(self.queue_name, job_json)
            logger.info(f"Enqueued job {job.id} of type '{job_type}' to '{self.queue_name}'")
            return job.id
        except Exception as exc:
            err_msg = str(exc)
            if "@" in err_msg:
                err_msg = err_msg.split("@")[-1]
            logger.error(
                f"Failed to enqueue job {job.id} to Redis queue '{self.queue_name}': {err_msg}"
            )
            raise

    async def dequeue(self, timeout: int = 2) -> Job | None:
        client = get_redis_client()
        try:
            # brpop blocks until an item is available or timeout expires
            result = await client.brpop(self.queue_name, timeout=timeout)
            if not result:
                return None
            _queue, item_data = result
            data = json.loads(item_data)
            return Job(**data)
        except Exception as exc:
            err_msg = str(exc)
            if "@" in err_msg:
                err_msg = err_msg.split("@")[-1]
            logger.error(f"Error dequeuing job from Redis queue '{self.queue_name}': {err_msg}")
            return None

    async def length(self) -> int:
        client = get_redis_client()
        try:
            return await client.llen(self.queue_name)
        except Exception as exc:
            err_msg = str(exc)
            if "@" in err_msg:
                err_msg = err_msg.split("@")[-1]
            logger.warning(f"Error checking Redis queue length: {err_msg}")
            return 0


class MockJobQueue(JobQueue):
    """In-memory asyncio Queue for tests and local environments without Redis."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()

    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> str:
        job = Job(job_type=job_type, payload=payload)
        await self._queue.put(job)
        return job.id

    async def dequeue(self, timeout: int = 2) -> Job | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=float(timeout))
        except TimeoutError:
            return None

    async def length(self) -> int:
        return self._queue.qsize()


_job_queue_instance: JobQueue | None = None


def get_job_queue(settings: Settings | None = None) -> JobQueue:
    """Returns singleton JobQueue instance (MockJobQueue in testing, RedisJobQueue otherwise)."""
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
    """Resets the singleton job queue instance (for testing)."""
    global _job_queue_instance
    _job_queue_instance = None
