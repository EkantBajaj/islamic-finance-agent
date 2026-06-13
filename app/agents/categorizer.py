from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import structlog

from app.services.llm_client import MODEL_REGISTRY, LLMClient

logger = structlog.get_logger()


class CategorizationAgent:
    """Three-tier transaction categorization agent.
    
    Tiers:
    1. MCC Lookup: Matches MCC against categories in mcc_codes.json.
    2. Rules Engine: Matches cleaned merchant name patterns in merchant_rules.json.
    3. LLM Fallback: Calls Anthropic Claude using prompts/categorization.txt.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        data_dir = Path(__file__).parent.parent / "data"

        # Load MCC mappings
        with open(data_dir / "mcc_codes.json", encoding="utf-8") as f:
            self.mcc_map = json.load(f)

        # Load merchant pattern rules
        with open(data_dir / "merchant_rules.json", encoding="utf-8") as f:
            self.merchant_rules = json.load(f).get("rules", [])

        # Load taxonomy
        with open(data_dir / "category_taxonomy.json", encoding="utf-8") as f:
            self.category_taxonomy = json.load(f)

        # Load prompts
        with open(data_dir / "prompts" / "categorization.txt", encoding="utf-8") as f:
            self.prompt_template = f.read()

        # Metadata Versioning
        config = MODEL_REGISTRY.get("categorizer", {})
        self.model = config.get("model", "claude-3-haiku-20240307")
        self.model_version = config.get("version", "v1.0")
        self.prompt_version = config.get("prompt_version", "cat-v3")
        self.prompt_hash = hashlib.sha256(self.prompt_template.encode("utf-8")).hexdigest()[:8]

    async def categorize(self, transaction: dict) -> dict:
        """Categorize a single transaction using the three-tier system."""
        start_time = time.perf_counter()
        tx_id = transaction.get("id")

        # Tier 1: MCC Lookup
        mcc = transaction.get("merchant_mcc")
        if mcc and str(mcc) in self.mcc_map:
            cat, subcat = self.mcc_map[str(mcc)]
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "categorization_completed",
                transaction_id=str(tx_id),
                agent_name="categorizer",
                latency_ms=latency_ms,
                model_version="N/A",
                prompt_version="N/A",
                prompt_hash="N/A",
                confidence=0.95,
                method="mcc",
            )
            return {
                "category": cat,
                "subcategory": subcat,
                "category_confidence": 0.95,
                "categorization_method": "mcc",
            }

        # Tier 2: Rules Engine
        merchant_name = transaction.get("merchant_name") or ""
        for pattern, cat, subcat in self.merchant_rules:
            if re.search(pattern, merchant_name, re.IGNORECASE):
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "categorization_completed",
                    transaction_id=str(tx_id),
                    agent_name="categorizer",
                    latency_ms=latency_ms,
                    model_version="N/A",
                    prompt_version="N/A",
                    prompt_hash="N/A",
                    confidence=0.85,
                    method="rules",
                )
                return {
                    "category": cat,
                    "subcategory": subcat,
                    "category_confidence": 0.85,
                    "categorization_method": "rules",
                }

        # Tier 3: LLM Fallback
        formatted_taxonomy = json.dumps(self.category_taxonomy, indent=2)
        prompt = (
            self.prompt_template
            .replace("{category_taxonomy}", formatted_taxonomy)
            .replace("{merchant}", merchant_name or "Unknown")
            .replace("{amount}", str(transaction.get("amount") or 0.00))
            .replace("{description}", transaction.get("description") or "")
        )

        try:
            response = await self.llm_client.invoke(
                model="categorizer",
                messages=prompt,
                temperature=0.0,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if response.json:
                data = response.json
                cat = data.get("category", "other")
                subcat = data.get("subcategory")
                confidence = float(data.get("confidence", 0.50))
            else:
                cat = "other"
                subcat = None
                confidence = 0.50

            logger.info(
                "categorization_completed",
                transaction_id=str(tx_id),
                agent_name="categorizer",
                latency_ms=latency_ms,
                model_version=self.model_version,
                prompt_version=self.prompt_version,
                prompt_hash=self.prompt_hash,
                confidence=confidence,
                method="llm",
            )
            return {
                "category": cat,
                "subcategory": subcat,
                "category_confidence": confidence,
                "categorization_method": "llm",
            }

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "categorization_llm_failed_using_fallback",
                transaction_id=str(tx_id),
                error=str(e),
            )
            logger.info(
                "categorization_completed",
                transaction_id=str(tx_id),
                agent_name="categorizer",
                latency_ms=latency_ms,
                model_version="N/A",
                prompt_version="N/A",
                prompt_hash="N/A",
                confidence=0.30,
                method="rules",
            )
            return {
                "category": "other",
                "subcategory": None,
                "category_confidence": 0.30,
                "categorization_method": "rules",
            }
