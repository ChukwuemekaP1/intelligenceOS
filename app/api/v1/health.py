import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app.database.redis import check_redis_health
from app.database.session import check_database_health
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["Health & Readiness"])


@router.get("/healthz", response_model=HealthResponse, summary="Liveness Probe")
@router.get("/health/live", response_model=HealthResponse, summary="Liveness Probe (Alias)")
async def liveness() -> HealthResponse:
    """Basic liveness probe checking that the application process is running."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC),
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness Probe")
@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness Probe (Alias)")
async def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe evaluating connectivity to PostgreSQL and Redis."""
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
