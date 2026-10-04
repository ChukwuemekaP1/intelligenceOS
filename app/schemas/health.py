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
