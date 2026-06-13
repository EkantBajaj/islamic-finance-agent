import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.services.cache import RedisCache


async def test_redis() -> None:
    print("Testing Redis cache...")
    settings = get_settings()
    print(f"Redis URL: {settings.redis_url}")
    cache = RedisCache()

    # Test setting a key
    print("Setting 'live-test-key' -> 'success'...")
    await cache.set("live-test-key", "success", expire_seconds=10)

    # Test getting the key
    val = await cache.get("live-test-key")
    print(f"Retrieved value: {val}")
    assert val == "success", "Failed to retrieve correct value from live Redis!"

    # Test delete
    await cache.delete("live-test-key")
    val_after_delete = await cache.get("live-test-key")
    print(f"Value after delete: {val_after_delete}")
    assert val_after_delete is None, "Failed to delete key from live Redis!"

    await cache.close()
    print("Redis cache test passed!")


async def test_postgres() -> None:
    print("Testing Postgres database...")
    settings = get_settings()
    print(f"Database URL: {settings.database_url}")
    engine = create_async_engine(str(settings.database_url))
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        val = result.scalar()
        print(f"SELECT 1 result: {val}")
        assert val == 1, "Failed database ping!"
    await engine.dispose()
    print("Postgres database test passed!")


async def main() -> None:
    try:
        await test_redis()
        print("-" * 40)
        await test_postgres()
        print("=" * 40)
        print("All live service checks passed successfully!")
    except Exception as e:
        print(f"ERROR: Live checks failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
