from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.config import Settings
from app.services.gold_price import GoldPriceService


@pytest.mark.asyncio
async def test_gold_price_success_price_key() -> None:
    """Test fetching gold price successfully with 'price' JSON key."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"price": 320.45}
    mock_client.get.return_value = mock_response

    service = GoldPriceService(client=mock_client)
    price = await service.get_gold_price()

    assert price == Decimal("320.45")
    mock_client.get.assert_called_once_with("https://api.gold-api.com/price/XAU")


@pytest.mark.asyncio
async def test_gold_price_success_price_per_gram_key() -> None:
    """Test fetching gold price successfully with 'price_per_gram' JSON key."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"price_per_gram": "325.50"}
    mock_client.get.return_value = mock_response

    service = GoldPriceService(client=mock_client)
    price = await service.get_gold_price()

    assert price == Decimal("325.50")
    mock_client.get.assert_called_once_with("https://api.gold-api.com/price/XAU")


@pytest.mark.asyncio
async def test_gold_price_success_price_per_ounce_key() -> None:
    """Test fetching gold price successfully with 'price_per_ounce' JSON key."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    # 3110.34768 / 31.1034768 = 100.00
    mock_response.json.return_value = {"price_per_ounce": "3110.34768"}
    mock_client.get.return_value = mock_response

    service = GoldPriceService(client=mock_client)
    price = await service.get_gold_price()

    assert price == Decimal("100")
    mock_client.get.assert_called_once_with("https://api.gold-api.com/price/XAU")


@pytest.mark.asyncio
async def test_gold_price_fallback_on_http_error() -> None:
    """Test that GoldPriceService returns the fallback price on HTTP errors."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    # Mock raise_for_status to raise an HTTPError
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Internal Server Error",
        request=MagicMock(spec=httpx.Request),
        response=mock_response,
    )
    mock_client.get.return_value = mock_response

    settings = Settings(
        gold_price_url="https://example.com/api",
        gold_fallback_price=Decimal("300.00"),
    )
    service = GoldPriceService(settings=settings, client=mock_client)
    price = await service.get_gold_price()

    assert price == Decimal("300.00")
    mock_client.get.assert_called_once_with("https://example.com/api")


@pytest.mark.asyncio
async def test_gold_price_fallback_on_timeout() -> None:
    """Test that GoldPriceService returns the fallback price on timeout."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

    settings = Settings(gold_fallback_price=Decimal("280.00"))
    service = GoldPriceService(settings=settings, client=mock_client)
    price = await service.get_gold_price()

    assert price == Decimal("280.00")


@pytest.mark.asyncio
async def test_gold_price_fallback_on_invalid_json() -> None:
    """Test that GoldPriceService returns the fallback price on invalid JSON payload."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"invalid_key": "some_value"}
    mock_client.get.return_value = mock_response

    service = GoldPriceService(client=mock_client)
    price = await service.get_gold_price()

    # Should fallback to default fallback price: 320.45
    assert price == Decimal("320.45")


@pytest.mark.asyncio
async def test_gold_price_fallback_on_non_dict_json() -> None:
    """Test that GoldPriceService returns the fallback price on non-dict JSON response."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [320.45]
    mock_client.get.return_value = mock_response

    service = GoldPriceService(client=mock_client)
    price = await service.get_gold_price()

    # Should fallback to default fallback price: 320.45
    assert price == Decimal("320.45")
