from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_endpoint(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_liveness_alias(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_healthy(client: AsyncClient) -> None:
    with (
        patch("app.api.v1.health.check_database_health", return_value=True),
        patch("app.api.v1.health.check_redis_health", return_value=True),
    ):
        response = await client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["redis"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_db_down(client: AsyncClient) -> None:
    with (
        patch("app.api.v1.health.check_database_health", return_value=False),
        patch("app.api.v1.health.check_redis_health", return_value=True),
    ):
        response = await client.get("/readyz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"] == "unhealthy"
        assert data["checks"]["redis"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_redis_down(client: AsyncClient) -> None:
    with (
        patch("app.api.v1.health.check_database_health", return_value=True),
        patch("app.api.v1.health.check_redis_health", return_value=False),
    ):
        response = await client.get("/readyz")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["redis"] == "unhealthy"
