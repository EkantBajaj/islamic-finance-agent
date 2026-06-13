from __future__ import annotations

import redis.asyncio as aioredis
import structlog
from redis.exceptions import RedisError

from app.config import get_settings

logger = structlog.get_logger()


class RedisCache:
    """Redis cache adapter with graceful fallback.

    If Redis is unavailable or command execution fails, the operations
    will log a warning and return a default/fallback value (None or False)
    rather than raising exceptions.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or str(settings.redis_url)
        self._client: aioredis.Redis | None = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying Redis client connection."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.warning("failed_to_close_redis_client", error=str(e))
            finally:
                self._client = None

    async def get(self, key: str) -> str | None:
        """Retrieve a value from the cache. Returns None on miss or failure."""
        try:
            return await self.client.get(key)
        except RedisError as e:
            logger.warning(
                "redis_cache_get_failed",
                key=key,
                error=str(e),
                exc_info=True,
            )
            return None

    async def set(
        self, key: str, value: str, expire_seconds: int | None = None
    ) -> bool:
        """Store a value in the cache. Returns True if successful, False on failure."""
        try:
            await self.client.set(key, value, ex=expire_seconds)
            return True
        except RedisError as e:
            logger.warning(
                "redis_cache_set_failed",
                key=key,
                error=str(e),
                exc_info=True,
            )
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from the cache. Returns True if successful, False on failure."""
        try:
            await self.client.delete(key)
            return True
        except RedisError as e:
            logger.warning(
                "redis_cache_delete_failed",
                key=key,
                error=str(e),
                exc_info=True,
            )
            return False


# Expose LLMCache as an alias for RedisCache
LLMCache = RedisCache
