"""Redis async client for cache and background queues.

Handles standard redis:// and rediss:// (TLS) URLs transparently.
The client is a module-level singleton to reuse connection pools.
"""

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.database.redis")
settings = get_settings()

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Returns or initialises the global async Redis client."""
    global _redis_client
    if _redis_client is None:
        url = settings.REDIS_URL

        # Sanitise URL for logging — strip password
        safe_url = url
        if "@" in url:
            scheme_part, host_part = url.split("@", 1)
            safe_url = f"{scheme_part.split('//')[0]}//***:***@{host_part}"

        logger.info(f"Initialising Redis client: {safe_url}")

        kwargs: dict = dict(
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            retry_on_timeout=True,
            health_check_interval=30,
        )

        _redis_client = aioredis.from_url(url, **kwargs)

    return _redis_client


async def close_redis() -> None:
    """Closes the async Redis client and clears the singleton."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:
            logger.warning(f"Error closing Redis connection: {exc}")
        finally:
            _redis_client = None


async def check_redis_health() -> bool:
    """Pings Redis to verify connectivity without exposing credentials in logs."""
    try:
        client = get_redis_client()
        pong = await client.ping()
        return bool(pong)
    except Exception as exc:
        err_msg = str(exc)
        # Strip password from error message
        if "@" in err_msg:
            err_msg = err_msg.split("@")[-1]
        logger.warning(f"Redis health check failed: {err_msg}")
        return False
