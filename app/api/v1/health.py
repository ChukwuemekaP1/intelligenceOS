"""Health, liveness, and readiness probes.

Exposes:
- /health       — comprehensive check (DB + Redis + Qdrant + Storage + Queue depth)
- /healthz      — liveness (process alive)
- /health/live  — liveness alias
- /readyz       — readiness (DB + Redis required)
- /health/ready — readiness alias
"""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app.database.redis import check_redis_health
from app.database.session import check_database_health
from app.schemas.health import ComprehensiveHealthResponse, HealthResponse, ReadinessResponse
from app.storage.factory import get_storage_backend
from app.vectorstore.factory import get_vector_store

router = APIRouter(tags=["Health & Readiness"])


async def check_qdrant_health() -> bool:
    try:
        vstore = get_vector_store()
        return await vstore.health_check()
    except Exception:
        return False


async def check_storage_health() -> bool:
    try:
        storage = get_storage_backend()
        return await storage.health_check()
    except Exception:
        return False


async def get_queue_depth() -> int:
    """Returns current ingestion queue depth, or -1 on error."""
    try:
        from app.queue.job_queue import get_job_queue
        queue = get_job_queue()
        return await queue.length()
    except Exception:
        return -1


@router.get(
    "/health",
    response_model=ComprehensiveHealthResponse,
    summary="Production System Health",
)
async def health(response: Response) -> ComprehensiveHealthResponse:
    """Comprehensive readiness probe: PostgreSQL + Redis + Qdrant + Supabase Storage + Queue."""
    db_ok, redis_ok, qdrant_ok, storage_ok, queue_depth = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
        check_qdrant_health(),
        check_storage_health(),
        get_queue_depth(),
    )

    all_ok = db_ok and redis_ok and qdrant_ok and storage_ok
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ComprehensiveHealthResponse(
        status="ok" if all_ok else "degraded",
        database="ok" if db_ok else "unhealthy",
        redis="ok" if redis_ok else "unhealthy",
        qdrant="ok" if qdrant_ok else "unhealthy",
        storage="ok" if storage_ok else "unhealthy",
        queue_depth=queue_depth,
        timestamp=datetime.now(UTC),
    )


@router.get("/healthz", response_model=HealthResponse, summary="Liveness Probe")
@router.get("/health/live", response_model=HealthResponse, summary="Liveness Probe (Alias)")
async def liveness() -> HealthResponse:
    """Basic liveness probe — confirms the application process is running."""
    return HealthResponse(status="ok", timestamp=datetime.now(UTC))


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness Probe")
@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness Probe (Alias)")
async def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe — confirms PostgreSQL and Redis are reachable."""
    db_healthy, redis_healthy = await asyncio.gather(
        check_database_health(),
        check_redis_health(),
    )

    checks = {
        "database": "healthy" if db_healthy else "unhealthy",
        "redis": "healthy" if redis_healthy else "unhealthy",
    }

    is_ready = db_healthy and redis_healthy
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if is_ready else "degraded",
        checks=checks,
        timestamp=datetime.now(UTC),
    )
