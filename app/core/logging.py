import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable to hold request correlation ID across async tasks
request_id_ctx: ContextVar[str | None] = ContextVar("request_id_ctx", default=None)

SENSITIVE_PATTERNS = [
    re.compile(r"(password['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE),
    re.compile(r"(secret['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE),
    re.compile(r"(api[-_]?key['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE),
    re.compile(r"(authorization['\"]?\s*[:=]\s*['\"]Bearer\s+)([^'\"]+)(['\"])", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([A-Za-z0-9\-_\.]*)", re.IGNORECASE),
]


def redact_sensitive_data(message: str) -> str:
    """Masks tokens, passwords, and sensitive keys in log strings."""
    redacted = message
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(
            r"\g<1>[REDACTED]\g<3>" if pattern.groups == 3 else r"\g<1>[REDACTED]", redacted
        )
    return redacted


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        message = record.getMessage()

        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(message),
        }

        if req_id:
            log_data["request_id"] = req_id

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_data["exception"] = redact_sensitive_data(record.exc_text)

        # Include custom extra fields if provided
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            ):
                if isinstance(value, (str, int, float, bool, list, dict)):
                    log_data[key] = value

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Readable console formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        req_part = f" [{req_id}]" if req_id else ""
        time_part = datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        message = redact_sensitive_data(record.getMessage())
        base = f"{time_part} | {record.levelname:<8} | {record.name}{req_part} - {message}"
        if record.exc_info:
            base += "\n" + redact_sensitive_data(self.formatException(record.exc_info))
        return base


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configures application-wide structured logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Clear existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(handler)

    # Silence overly verbose libraries if needed
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience helper to obtain a named logger."""
    return logging.getLogger(name)
