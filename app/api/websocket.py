from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Connection manager for active WebSocket pipeline connections."""

    def __init__(self) -> None:
        self.active_connections: dict[UUID, list[WebSocket]] = {}

    async def connect(self, pipeline_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        if pipeline_id not in self.active_connections:
            self.active_connections[pipeline_id] = []
        self.active_connections[pipeline_id].append(websocket)
        logger.info("websocket_connected", pipeline_id=str(pipeline_id))

    def disconnect(self, pipeline_id: UUID, websocket: WebSocket) -> None:
        if pipeline_id in self.active_connections:
            if websocket in self.active_connections[pipeline_id]:
                self.active_connections[pipeline_id].remove(websocket)
            if not self.active_connections[pipeline_id]:
                del self.active_connections[pipeline_id]
        logger.info("websocket_disconnected", pipeline_id=str(pipeline_id))

    async def broadcast(self, pipeline_id: UUID, event: dict) -> None:
        """Broadcast structured event payload as JSON to pipeline listeners."""
        if pipeline_id not in self.active_connections:
            return

        class CustomEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                if isinstance(obj, UUID):
                    return str(obj)
                return super().default(obj)

        # Pre-serialize to ensure safe datetime/UUID formats
        event_json = json.loads(json.dumps(event, cls=CustomEncoder))

        for websocket in self.active_connections[pipeline_id]:
            try:
                await websocket.send_json(event_json)
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    pipeline_id=str(pipeline_id),
                    error=str(e),
                )


manager = ConnectionManager()


@router.websocket("/ws/pipeline/{pipeline_id}")
async def websocket_endpoint(websocket: WebSocket, pipeline_id: UUID) -> None:
    """WebSocket endpoint listening on stage pipelines."""
    await manager.connect(pipeline_id, websocket)
    try:
        while True:
            # Keeps the WebSocket connection alive and handles pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(pipeline_id, websocket)
    except Exception as e:
        logger.warning(
            "websocket_unexpected_closure",
            pipeline_id=str(pipeline_id),
            error=str(e),
        )
        manager.disconnect(pipeline_id, websocket)
