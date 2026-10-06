from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Process liveness indicator")
    timestamp: datetime = Field(description="Current UTC timestamp")


class ReadinessResponse(BaseModel):
    status: str = Field(
        description="'ready' if all critical dependencies are healthy, else 'degraded'"
    )
    checks: dict[str, str] = Field(description="Health status of external dependencies")
    timestamp: datetime = Field(description="Current UTC timestamp")


class ComprehensiveHealthResponse(BaseModel):
    status: str = Field(description="'ok' if healthy, else 'degraded'")
    database: str = Field(description="Database health: 'ok' or 'unhealthy'")
    redis: str = Field(description="Redis health: 'ok' or 'unhealthy'")
    qdrant: str = Field(description="Qdrant vector store health: 'ok' or 'unhealthy'")
    storage: str = Field(description="Object storage health: 'ok' or 'unhealthy'")
    queue_depth: int = Field(
        default=-1,
        description="Current ingestion queue depth (-1 if unavailable)",
    )
    timestamp: datetime = Field(description="Current UTC timestamp")
