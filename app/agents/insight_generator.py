from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal
from pathlib import Path

import structlog

from app.services.llm_client import MODEL_REGISTRY, LLMClient

logger = structlog.get_logger()


class InsightGenerationAgent:
    """Personalized financial insight generator agent.
    
    Uses Claude Sonnet to generate friendly, professional, Shariah-conscious
    insights based on aggregated transaction and PFM data.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        data_dir = Path(__file__).parent.parent / "data"

        # Load prompt template
        with open(data_dir / "prompts" / "insight_generation.txt", encoding="utf-8") as f:
            self.prompt_template = f.read()

        # Metadata Versioning
        config = MODEL_REGISTRY.get("insight_generator", {})
        self.model = config.get("model", "claude-3-5-sonnet-20241022")
        self.model_version = config.get("version", "v1.0")
        self.prompt_version = config.get("prompt_version", "insight-v1")
        self.prompt_hash = hashlib.sha256(self.prompt_template.encode("utf-8")).hexdigest()[:8]

    async def generate(self, state: dict) -> list[dict]:
        """Generate insights based on current categorized and screened transactions."""
        start_time = time.perf_counter()

        categorized = state.get("categorized", [])
        shariah_screened = state.get("shariah_screened", [])
        recurrence_groups = state.get("recurrence_groups", [])

        # 1. Aggregate spending by category
        spending_by_category = {}
        total_spend = Decimal("0")
        for tx in categorized:
            cat = tx.get("category", "other")
            amt = Decimal(str(tx.get("amount", 0.0)))
            spending_by_category[cat] = spending_by_category.get(cat, Decimal("0")) + amt
            total_spend += amt

        # Format decimals as floats for serialization
        spending_by_category_float = {k: float(v) for k, v in spending_by_category.items()}

        # 2. Extract flagged transactions
        non_compliant = [
            {
                "merchant": tx.get("merchant_name") or "Unknown",
                "amount": float(tx.get("amount", 0.0)),
                "flags": tx.get("shariah_flags", []),
            }
            for tx in shariah_screened
            if tx.get("shariah_status") == "non_compliant"
        ]

        # 3. Extract recurring subscriptions
        recurring = [
            {
                "merchant": group.get("merchant"),
                "frequency": group.get("frequency"),
                "average_amount": float(group.get("avg_amount", 0.0)),
            }
            for group in recurrence_groups
        ]

        # 4. Simple anomaly detection: any category exceeding 40% of total spend
        anomalies = []
        for cat, amt in spending_by_category.items():
            if total_spend > 0 and (amt / total_spend) > Decimal("0.40"):
                anomalies.append({
                    "category": cat,
                    "percentage": float(round((amt / total_spend) * 100, 2)),
                    "amount": float(amt),
                    "message": (
                        f"Spending in '{cat}' accounts for a significant "
                        f"portion of total outflows."
                    ),
                })

        input_data = {
            "spending_by_category": spending_by_category_float,
            "total_spend": float(total_spend),
            "non_compliant_transactions": non_compliant,
            "recurring_payments": recurring,
            "anomalies": anomalies,
        }

        serialized_input = json.dumps(input_data, indent=2)
        user_message = (
            f"{self.prompt_template}\n\n"
            f"Input Transaction Summary:\n{serialized_input}"
        )

        try:
            response = await self.llm_client.invoke(
                model="insight_generator",
                messages=user_message,
                temperature=0.3,
            )

            # Strip markdown wrappers if any returned
            content = response.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n", "", content)
                content = re.sub(r"\n```$", "", content)

            parsed_data = json.loads(content)
            insights = parsed_data.get("insights", [])

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "insight_generation_completed",
                agent_name="insight_generator",
                latency_ms=latency_ms,
                model_version=self.model_version,
                prompt_version=self.prompt_version,
                prompt_hash=self.prompt_hash,
                confidence=1.00,
                insights_count=len(insights),
            )
            return insights

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "insight_generation_llm_failed_using_fallback",
                error=str(e),
            )

            # Fallback to deterministic template-based insights
            fallback_insights = []
            if total_spend > 0:
                top_cat = max(spending_by_category, key=spending_by_category.get)
                top_cat_amount = spending_by_category[top_cat]
                fallback_insights.append({
                    "title": "Spending Concentration",
                    "body": (
                        f"Your highest spending category this period is {top_cat}, "
                        f"representing AED {top_cat_amount:,.2f} of your total spending. "
                        f"Consider reviewing this category to manage your cash outflow."
                    ),
                    "severity": "info",
                    "data": {"top_category": top_cat, "amount": float(top_cat_amount)},
                })

            if non_compliant:
                fallback_insights.append({
                    "title": "Shariah Compliance Alert",
                    "body": (
                        f"We flagged {len(non_compliant)} transaction(s) as "
                        f"non-compliant under Shariah rules. Reviewing these "
                        f"transactions can help align your spending."
                    ),
                    "severity": "warning",
                    "data": {"flagged_count": len(non_compliant)},
                })

            logger.info(
                "insight_generation_completed",
                agent_name="insight_generator",
                latency_ms=latency_ms,
                model_version="N/A",
                prompt_version="N/A",
                prompt_hash="N/A",
                confidence=1.00,
                insights_count=len(fallback_insights),
            )
            return fallback_insights
