from __future__ import annotations

import re
import statistics
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger()


class RecurrenceDetectionAgent:
    """Statistical recurring transaction detector (no LLM required).
    
    Identifies subscription-like behavior by grouping transactions by merchant,
    measuring interval spacing consistency, and verifying amount consistency.
    """

    def __init__(self) -> None:
        # Consistency markers matching versioning strategy for agents
        self.model = "N/A"
        self.model_version = "N/A"
        self.prompt_version = "N/A"
        self.prompt_hash = "N/A"

    def _normalize_merchant(self, name: str) -> str:
        """Helper to clean and normalize merchant names."""
        if not name:
            return ""
        name = name.lower()
        name = re.sub(r"\d+", "", name)  # Remove numeric ids
        name = re.sub(r"[^\w\s]", "", name)  # Remove special characters
        name = " ".join(name.split())  # Clean whitespaces
        return name

    def _get_date(self, val: Any) -> date | None:
        """Helper to safely parse Date objects."""
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            try:
                return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    def _detect_frequency(self, avg_interval: float) -> str | None:
        """Map day interval to standard recurring frequency."""
        if 5 <= avg_interval <= 9:
            return "weekly"
        elif 12 <= avg_interval <= 17:
            return "biweekly"
        elif 25 <= avg_interval <= 35:
            return "monthly"
        elif 85 <= avg_interval <= 95:
            return "quarterly"
        elif 355 <= avg_interval <= 375:
            return "yearly"
        return None

    async def detect(self, transactions: list[dict]) -> list[dict]:
        """Detect recurring transaction groups from a list of transactions."""
        start_time = time.perf_counter()

        # Group by normalized merchant
        merchant_groups = defaultdict(list)
        for tx in transactions:
            m_name = tx.get("merchant_name") or ""
            clean_m = self._normalize_merchant(m_name)
            if clean_m:
                merchant_groups[clean_m].append(tx)

        recurrence_groups = []

        for merchant, txs in merchant_groups.items():
            if len(txs) < 2:
                continue

            # Sort by transaction date
            valid_txs = []
            for tx in txs:
                tx_date = self._get_date(tx.get("transaction_date"))
                if tx_date:
                    valid_txs.append((tx_date, tx))

            if len(valid_txs) < 2:
                continue

            valid_txs.sort(key=lambda x: x[0])

            # Compute intervals in days
            intervals = [
                (valid_txs[i + 1][0] - valid_txs[i][0]).days
                for i in range(len(valid_txs) - 1)
            ]

            avg_interval = sum(intervals) / len(intervals)
            std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0.0

            # Check interval coefficient of variation (skip if highly irregular)
            if avg_interval > 0 and (std_interval / avg_interval) > 0.3:
                continue

            frequency = self._detect_frequency(avg_interval)
            if not frequency:
                continue

            # Check amount consistency (within 10% tolerance from mean)
            amounts = [float(tx[1].get("amount") or 0.0) for tx in valid_txs]
            avg_amount = sum(amounts) / len(amounts)

            if avg_amount > 0:
                is_consistent = all(abs(a - avg_amount) / avg_amount <= 0.10 for a in amounts)
            else:
                is_consistent = False

            if not is_consistent:
                continue

            # Determine confidence
            if len(intervals) == 1:
                confidence = 0.90
            else:
                cv = std_interval / avg_interval if avg_interval > 0 else 0.0
                confidence = max(0.50, min(0.99, 1.0 - cv))

            # Success, recurring pattern detected
            group_id = uuid.uuid4()
            last_date = valid_txs[-1][0]
            next_expected = last_date + timedelta(days=round(avg_interval))

            group_data = {
                "id": group_id,
                "merchant": merchant,
                "frequency": frequency,
                "avg_amount": avg_amount,
                "next_expected": next_expected,
                "transaction_ids": [tx[1].get("id") for tx in valid_txs],
                "confidence": confidence,
            }
            recurrence_groups.append(group_data)

            # Log completion for each transaction in the group
            for _, tx in valid_txs:
                tx_id = tx.get("id")
                logger.info(
                    "recurrence_detection_completed",
                    transaction_id=str(tx_id),
                    agent_name="recurrence_detector",
                    latency_ms=0.0,  # bulk operation
                    model_version="N/A",
                    prompt_version="N/A",
                    prompt_hash="N/A",
                    confidence=confidence,
                )

        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "recurrence_agent_run_completed",
            latency_ms=latency_ms,
            groups_count=len(recurrence_groups),
        )
        return recurrence_groups
