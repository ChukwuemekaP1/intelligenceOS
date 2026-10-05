import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.database.redis")
settings = get_settings()

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Returns or initializes the global async Redis client with robust cloud timeouts and retry."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _redis_client


async def close_redis() -> None:
    """Closes the async Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def check_redis_health() -> bool:
    """Pings Redis to check connectivity and readiness without exposing credentials on error."""
    try:
        client = get_redis_client()
        pong = await client.ping()
        return bool(pong)
    except Exception as exc:
        # Log clean error message without leaking Redis password or full connection URL
        err_msg = str(exc)
        if "@" in err_msg:
            # Strip potential user:pass in error message if any
            err_msg = err_msg.split("@")[-1]
        logger.warning(f"Redis health check failed: {err_msg}")
        return False
