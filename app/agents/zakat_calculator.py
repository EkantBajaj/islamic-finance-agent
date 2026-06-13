from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from decimal import Decimal

import structlog

from app.models.schemas import ZakatResult
from app.services.gold_price import GoldPriceService
from app.services.llm_client import LLMClient

logger = structlog.get_logger()


class ZakatCalculationAgent:
    """Zakat Calculation Agent.
    
    Computes obligatory Zakat (2.5% of net assets held above the gold Nisab threshold)
    and generates natural-language explanations using Claude.
    """

    ZAKAT_RATE = Decimal("0.025")

    def __init__(
        self,
        llm_client: LLMClient,
        gold_price_service: GoldPriceService | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.gold_price_service = gold_price_service or GoldPriceService()

        self.system_prompt = (
            "You are a helpful Islamic finance expert explaining Zakat obligations."
        )
        self.model = "claude-3-5-sonnet-20241022"
        self.model_version = "v1.0"
        self.prompt_version = "zakat-v1"
        self.prompt_hash = hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()[:8]

    async def calculate(
        self,
        profile: dict,
        gold_price_per_gram: Decimal | None = None,
    ) -> ZakatResult:
        """Calculate the user's Zakat obligation."""
        start_time = time.perf_counter()

        # Fetch gold price if not injected
        if gold_price_per_gram is None:
            gold_price_per_gram = await self.gold_price_service.get_gold_price()

        # 85 grams of gold is the traditional Nisab threshold
        nisab_gold = (gold_price_per_gram * Decimal("85")).quantize(Decimal("0.01"))

        # Net Zakatable Assets calculation
        cash = Decimal(str(profile.get("cash_balance", 0.0)))
        savings = Decimal(str(profile.get("savings_balance", 0.0)))
        investments = Decimal(str(profile.get("investment_value", 0.0)))
        debts = Decimal(str(profile.get("immediate_debts", 0.0)))

        zakatable = (cash + savings + investments - debts).quantize(Decimal("0.01"))
        if zakatable < Decimal("0"):
            zakatable = Decimal("0.00")

        is_eligible = zakatable >= nisab_gold
        zakat_due = (
            (zakatable * self.ZAKAT_RATE).quantize(Decimal("0.01"))
            if is_eligible
            else Decimal("0.00")
        )

        # LLM explanation generation
        user_message = (
            "Please explain the following Zakat calculation details "
            "in 1-2 friendly, professional sentences. "
            f"Address the user directly. "
            f"Details:\n"
            f"- Net Zakatable Assets: AED {zakatable:,.2f}\n"
            f"- Nisab Threshold (value of 85g gold): AED {nisab_gold:,.2f}\n"
            f"- Zakat Obligation: "
            f"{'Obligatory (exceeds Nisab)' if is_eligible else 'Not Obligatory (below Nisab)'}\n"
            f"- Zakat Due (2.5%): AED {zakat_due:,.2f}"
        )

        try:
            response = await self.llm_client.invoke(
                model="insight_generator",  # maps to Claude Sonnet
                messages=user_message,
                system=self.system_prompt,
                temperature=0.3,
            )
            explanation = response.content.strip()

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "zakat_calculation_completed",
                agent_name="zakat_calculator",
                latency_ms=latency_ms,
                model_version=self.model_version,
                prompt_version=self.prompt_version,
                prompt_hash=self.prompt_hash,
                confidence=1.00,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "zakat_explanation_llm_failed_using_fallback",
                error=str(e),
            )
            if is_eligible:
                explanation = (
                    f"Based on your current assets of AED {zakatable:,.2f}, "
                    f"which exceeds the Nisab threshold of "
                    f"AED {nisab_gold:,.2f}, your annual Zakat obligation is AED {zakat_due:,.2f}. "
                    f"Consider distributing to those in need before the end of your Zakat year."
                )
            else:
                explanation = (
                    f"Based on your current assets of AED {zakatable:,.2f}, "
                    f"which is below the Nisab threshold of "
                    f"AED {nisab_gold:,.2f}, you have no obligatory Zakat due at this time."
                )

            logger.info(
                "zakat_calculation_completed",
                agent_name="zakat_calculator",
                latency_ms=latency_ms,
                model_version="N/A",
                prompt_version="N/A",
                prompt_hash="N/A",
                confidence=1.00,
            )

        return ZakatResult(
            eligible_assets=zakatable,
            nisab_threshold=nisab_gold,
            zakat_due=zakat_due,
            is_eligible=is_eligible,
            explanation=explanation,
            calculated_at=datetime.now(UTC),
        )
