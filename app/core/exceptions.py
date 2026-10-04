import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.exceptions")


class DomainError(Exception):
    """Base domain exception."""

    def __init__(
        self, message: str, error_code: str = "DOMAIN_ERROR", status_code: int = 400
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class NotFoundError(DomainError):
    def __init__(self, message: str = "Resource not found", error_code: str = "NOT_FOUND") -> None:
        super().__init__(
            message=message, error_code=error_code, status_code=status.HTTP_404_NOT_FOUND
        )


class ConflictError(DomainError):
    def __init__(self, message: str = "Resource conflict", error_code: str = "CONFLICT") -> None:
        super().__init__(
            message=message, error_code=error_code, status_code=status.HTTP_409_CONFLICT
        )


class UnauthorizedError(DomainError):
    def __init__(
        self, message: str = "Authentication required", error_code: str = "UNAUTHORIZED"
    ) -> None:
        super().__init__(
            message=message, error_code=error_code, status_code=status.HTTP_401_UNAUTHORIZED
        )


class ForbiddenError(DomainError):
    def __init__(self, message: str = "Access forbidden", error_code: str = "FORBIDDEN") -> None:
        super().__init__(
            message=message, error_code=error_code, status_code=status.HTTP_403_FORBIDDEN
        )


class BadRequestError(DomainError):
    def __init__(self, message: str = "Bad request", error_code: str = "BAD_REQUEST") -> None:
        super().__init__(
            message=message, error_code=error_code, status_code=status.HTTP_400_BAD_REQUEST
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers standard application exception handlers."""

    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error_code": exc.error_code},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "error_code": f"HTTP_{exc.status_code}",
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Avoid leaking internal schema objects, simplify errors
        sanitized_errors: list[dict[str, Any]] = []
        for err in exc.errors():
            sanitized_errors.append(
                {
                    "loc": err.get("loc"),
                    "msg": err.get("msg"),
                    "type": err.get("type"),
                }
            )
        return JSONResponse(
            status_code=422,
            content={"detail": sanitized_errors, "error_code": "VALIDATION_ERROR"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled exception during request {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )
        # Never leak raw stack traces or internal DB errors to client
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred.",
                "error_code": "INTERNAL_SERVER_ERROR",
            },
        )
