from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import get_db
from app.models.schemas import DependencyHealth, HealthResponse
from app.services.cache import RedisCache

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


@router.get("", response_model=HealthResponse)
async def check_health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Return health details of database, cache, and LLM connections."""
    
    # 1. Check Postgres
    postgres_status: Literal["healthy", "unhealthy"] = "healthy"
    postgres_latency: float | None = None
    postgres_detail: str | None = None
    
    start_time = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        postgres_latency = (time.perf_counter() - start_time) * 1000
    except Exception as e:
        postgres_status = "unhealthy"
        postgres_detail = str(e)
        
    # 2. Check Redis
    redis_status: Literal["healthy", "unhealthy"] = "healthy"
    redis_latency: float | None = None
    redis_detail: str | None = None
    
    cache = RedisCache()
    start_time = time.perf_counter()
    try:
        ping_ok = await cache.client.ping()
        if not ping_ok:
            redis_status = "unhealthy"
            redis_detail = "Redis ping returned False"
        redis_latency = (time.perf_counter() - start_time) * 1000
    except Exception as e:
        redis_status = "unhealthy"
        redis_detail = str(e)
    finally:
        await cache.close()
        
    # 3. Check LLM Config
    llm_status: Literal["healthy", "not_configured"] = "healthy"
    llm_detail: str | None = None
    if not settings.anthropic_api_key:
        llm_status = "not_configured"
        llm_detail = "Anthropic API key is not configured"
        
    # Global Status
    global_status: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    if postgres_status == "unhealthy" and redis_status == "unhealthy":
        global_status = "unhealthy"
    elif postgres_status == "unhealthy" or redis_status == "unhealthy":
        global_status = "degraded"
        
    return HealthResponse(
        status=global_status,
        postgres=DependencyHealth(
            status=postgres_status,
            latency_ms=postgres_latency,
            detail=postgres_detail,
        ),
        redis=DependencyHealth(
            status=redis_status,
            latency_ms=redis_latency,
            detail=redis_detail,
        ),
        llm_provider=DependencyHealth(
            status=llm_status,
            detail=llm_detail,
        ),
        version=settings.app_version,
    )
