from fastapi import FastAPI

app = FastAPI(
    title="Barakah Transaction Intelligence Agent",
    version="0.1.0",
    description="Shariah-compliant transaction intelligence API.",
)


@app.get("/", tags=["service"])
async def service_info() -> dict[str, str]:
    """Return basic service metadata until the versioned API is added."""
    return {
        "name": "Barakah Transaction Intelligence Agent",
        "version": "0.1.0",
        "status": "building",
    }

