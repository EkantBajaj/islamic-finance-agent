from __future__ import annotations

import unittest.mock as mock

from redis.exceptions import ConnectionError

from app.services.cache import LLMCache, RedisCache


class MockRedis:
    def __init__(self, *args, **kwargs) -> None:
        self.store: dict[str, str] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        if self.closed:
            raise RuntimeError("Client is closed")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        if self.closed:
            raise RuntimeError("Client is closed")
        self.store[key] = value
        return True

    async def delete(self, key: str) -> int:
        if self.closed:
            raise RuntimeError("Client is closed")
        if key in self.store:
            del self.store[key]
            return 1
        return 0

    async def aclose(self) -> None:
        self.closed = True


class FailingMockRedis:
    async def get(self, key: str) -> str | None:
        raise ConnectionError("Could not connect to Redis server")

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        raise ConnectionError("Could not connect to Redis server")

    async def delete(self, key: str) -> int:
        raise ConnectionError("Could not connect to Redis server")

    async def aclose(self) -> None:
        pass


async def test_cache_set_and_get() -> None:
    # Test setting and getting keys under normal conditions
    mock_redis = MockRedis()
    with mock.patch("redis.asyncio.from_url", return_value=mock_redis) as mock_from_url:
        cache = RedisCache(redis_url="redis://localhost:9999/0")

        # Verify that get on non-existent key returns None
        val1 = await cache.get("test-key")
        assert val1 is None

        # Set a key-value pair
        set_ok = await cache.set("test-key", "test-value")
        assert set_ok is True

        # Get the value back
        val2 = await cache.get("test-key")
        assert val2 == "test-value"

        # Check from_url was called with correct arguments
        mock_from_url.assert_called_once_with(
            "redis://localhost:9999/0",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )


async def test_cache_delete() -> None:
    mock_redis = MockRedis()
    with mock.patch("redis.asyncio.from_url", return_value=mock_redis):
        cache = RedisCache()

        await cache.set("delete-key", "some-value")
        assert await cache.get("delete-key") == "some-value"

        # Delete existing key
        del_ok = await cache.delete("delete-key")
        assert del_ok is True
        assert await cache.get("delete-key") is None

        # Delete non-existing key
        del_ok_non_exist = await cache.delete("delete-key")
        assert del_ok_non_exist is True


async def test_cache_ttl_parameter_passed() -> None:
    mock_redis = mock.AsyncMock()
    with mock.patch("redis.asyncio.from_url", return_value=mock_redis):
        cache = RedisCache()

        await cache.set("ttl-key", "val", expire_seconds=3600)
        mock_redis.set.assert_called_once_with("ttl-key", "val", ex=3600)


async def test_cache_graceful_fallback_on_connection_error() -> None:
    # Test that connection issues don't bubble up exceptions
    failing_redis = FailingMockRedis()
    with mock.patch("redis.asyncio.from_url", return_value=failing_redis):
        cache = RedisCache()

        # get should return None and log warning
        val = await cache.get("some-key")
        assert val is None

        # set should return False and log warning
        set_ok = await cache.set("some-key", "some-val")
        assert set_ok is False

        # delete should return False and log warning
        del_ok = await cache.delete("some-key")
        assert del_ok is False


async def test_cache_close() -> None:
    mock_redis = MockRedis()
    with mock.patch("redis.asyncio.from_url", return_value=mock_redis):
        cache = RedisCache()

        # Initialize client
        assert cache.client is mock_redis
        assert not mock_redis.closed

        # Close connection
        await cache.close()
        assert mock_redis.closed
        assert cache._client is None


async def test_llm_cache_alias() -> None:
    # Ensure LLMCache is indeed the same class
    assert LLMCache is RedisCache
