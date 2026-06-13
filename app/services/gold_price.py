from __future__ import annotations

from decimal import Decimal

import httpx
import structlog

from app.config import Settings, get_settings

logger = structlog.get_logger()


class GoldPriceService:
    """Service to fetch the current gold price from an external API with deterministic fallback."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client

    async def get_gold_price(self) -> Decimal:
        """Fetch the current gold price per gram.

        If the fetch fails due to timeout, connection issue, or invalid response,
        it gracefully logs a warning and returns the configured fallback price.
        """
        url = str(self.settings.gold_price_url)
        logger.info("fetching_gold_price", url=url)

        # Use the injected client or instantiate one for this call
        client = self.client or httpx.AsyncClient(timeout=5.0)
        close_client = self.client is None

        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            # Support parsing various formats
            if isinstance(data, dict):
                if "price" in data:
                    price = Decimal(str(data["price"]))
                elif "price_per_gram" in data:
                    price = Decimal(str(data["price_per_gram"]))
                elif "price_per_ounce" in data:
                    # 1 troy ounce = 31.1034768 grams
                    price = Decimal(str(data["price_per_ounce"])) / Decimal("31.1034768")
                else:
                    keys = list(data.keys())
                    raise ValueError(f"Could not find gold price in response keys: {keys}")
            else:
                raise ValueError("Response data is not a dictionary JSON object")

            logger.info("fetched_gold_price_success", price=price)
            return price

        except Exception as e:
            fallback = self.settings.gold_fallback_price
            logger.warning(
                "fetched_gold_price_failed_using_fallback",
                error=str(e),
                fallback_price=str(fallback),
            )
            return fallback
        finally:
            if close_client:
                await client.aclose()
