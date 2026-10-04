import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_v1_router
from app.api.v1.health import router as root_health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.database.redis import close_redis
from app.database.session import engine

settings = get_settings()
setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting {settings.PROJECT_NAME} in '{settings.ENVIRONMENT}' environment")
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")
    await close_redis()
    await engine.dispose()
    logger.info("Database and Redis connections closed.")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a correlation request ID and logs request latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        try:
            response: Response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-ID"] = req_id

            # Avoid spamming logs with liveness checks
            if request.url.path not in ("/healthz", "/health/live"):
                logger.info(
                    f"{request.method} {request.url.path} completed "
                    f"with {response.status_code} in {elapsed_ms:.2f}ms"
                )
            return response
        finally:
            request_id_ctx.reset(token)


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="IntelligenceOS - AI/RAG Platform Foundation & Identity Layer",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestContextMiddleware)

    # Exception Handlers
    register_exception_handlers(app)

    # Routers
    # Direct liveness/readiness probes at root
    app.include_router(root_health_router)
    # API v1 routes
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    return app


app = create_application()
