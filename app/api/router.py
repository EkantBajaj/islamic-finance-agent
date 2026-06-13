from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.insights import router as insights_router
from app.api.profile import router as profile_router
from app.api.transactions import router as transactions_router
from app.api.websocket import router as websocket_router
from app.api.zakat import router as zakat_router

api_router = APIRouter()

# Include versioned API routers
api_router.include_router(health_router, prefix="/api/v1")
api_router.include_router(insights_router, prefix="/api/v1")
api_router.include_router(profile_router, prefix="/api/v1")
api_router.include_router(transactions_router, prefix="/api/v1")
api_router.include_router(zakat_router, prefix="/api/v1")

# Include the websocket router (no version prefix since transactions.py returns `/ws/pipeline/{id}`)
api_router.include_router(websocket_router)
