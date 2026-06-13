from fastapi import FastAPI

from app.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings)
logger = get_logger(component="api")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Shariah-compliant transaction intelligence API.",
)


@app.get("/", tags=["service"])
async def service_info() -> dict[str, str]:
    """Return basic service metadata until the versioned API is added."""
    logger.info("service_info_requested")
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "building",
    }
