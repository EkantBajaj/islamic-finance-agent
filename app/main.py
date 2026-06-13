from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.cache import RedisCache

settings = get_settings()
configure_logging(settings)
logger = get_logger(component="api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("api_startup_commenced", app_name=settings.app_name, version=settings.app_version)
    yield
    # Shutdown actions
    logger.info("api_shutdown_commenced")
    cache = RedisCache()
    await cache.close()
    logger.info("api_shutdown_completed")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Shariah-compliant transaction intelligence API.",
    lifespan=lifespan,
)

# Enable CORS for frontend and API integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "http_exception_encountered",
        path=request.url.path,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "validation_exception_encountered",
        path=request.url.path,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

# Register aggregated router
app.include_router(api_router)


@app.get("/", tags=["service"])
async def service_info() -> dict[str, str]:
    """Return basic service metadata."""
    logger.info("service_info_requested")
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "active",
    }

