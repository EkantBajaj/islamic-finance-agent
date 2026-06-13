from __future__ import annotations

import unittest.mock as mock
import uuid

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.websocket import ConnectionManager
from app.config import get_settings
from app.core.database import get_db
from app.main import app

settings = get_settings()

# Use NullPool in tests to avoid event-loop connection reuse conflicts
test_engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


async def override_get_db():
    """Inject database session using NullPool for test isolation."""
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

DEFAULT_ACCOUNT_ID = uuid.UUID("d3b07384-d113-4956-a5cc-9c0211a766bb")


def test_health_check() -> None:
    """Test the /api/v1/health status endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "postgres" in data
    assert "redis" in data
    assert "llm_provider" in data


def test_get_enriched_transactions() -> None:
    """Test retrieving the paginated enriched transaction feed."""
    response = client.get(f"/api/v1/transactions/{DEFAULT_ACCOUNT_ID}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "page" in data
    assert "limit" in data
    assert "total" in data
    
    # Verify structure of items if present
    if data["items"]:
        item = data["items"][0]
        assert "id" in item
        assert "category" in item
        assert "shariah_status" in item
        assert "cashflow_type" in item


def test_get_financial_insights() -> None:
    """Test retrieving Shariah and PFM insights for an account."""
    response = client.get(f"/api/v1/insights/{DEFAULT_ACCOUNT_ID}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        insight = data[0]
        assert "title" in insight
        assert "body" in insight
        assert "severity" in insight


def test_get_zakat_calculations() -> None:
    """Test retrieving Nisab gold-standard calculations."""
    response = client.get(f"/api/v1/zakat/{DEFAULT_ACCOUNT_ID}")
    assert response.status_code == 200
    data = response.json()
    assert "eligible_assets" in data
    assert "nisab_threshold" in data
    assert "zakat_due" in data
    assert "is_eligible" in data
    assert "explanation" in data


def test_get_customer_profile() -> None:
    """Test retrieving compliance profiling details."""
    response = client.get(f"/api/v1/profile/{DEFAULT_ACCOUNT_ID}")
    assert response.status_code == 200
    data = response.json()
    assert "account_id" in data
    assert "shariah_compliance_score" in data
    assert "avg_monthly_income" in data
    assert "avg_monthly_spend" in data


def test_ingest_transactions() -> None:
    """Test posting a batch of raw transaction records for ingestion."""
    payload = {
        "account_id": str(DEFAULT_ACCOUNT_ID),
        "transactions": [
            {
                "external_id": f"TEST_INGEST_{uuid.uuid4().hex[:6]}",
                "amount": "150.00",
                "currency": "AED",
                "direction": "debit",
                "transaction_date": "2026-06-13",
                "merchant_name": "Test Merchant Ingest",
                "merchant_mcc": "5411",
                "description": "Weekly test groceries",
            }
        ],
    }
    
    # Mock out background task to avoid event loop conflicts or
    # raw database calls in background thread
    with mock.patch("app.api.transactions.run_pipeline_task") as mock_run_task:
        response = client.post("/api/v1/transactions/ingest", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert "pipeline_id" in data
        assert data["status"] == "accepted"
        assert "ws_channel" in data
        mock_run_task.assert_called_once()


@pytest.mark.anyio
async def test_websocket_manager() -> None:
    """Test ConnectionManager connecting, disconnecting, and broadcasting."""
    manager = ConnectionManager()
    pipeline_id = uuid.uuid4()
    
    mock_ws = mock.AsyncMock(spec=WebSocket)
    
    # Test connect
    await manager.connect(pipeline_id, mock_ws)
    mock_ws.accept.assert_awaited_once()
    assert pipeline_id in manager.active_connections
    assert mock_ws in manager.active_connections[pipeline_id]
    
    # Test broadcast
    event = {"type": "stage_started", "stage": "ingest"}
    await manager.broadcast(pipeline_id, event)
    mock_ws.send_json.assert_awaited_once_with(event)
    
    # Test disconnect
    manager.disconnect(pipeline_id, mock_ws)
    assert pipeline_id not in manager.active_connections
