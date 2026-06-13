from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import structlog

from app.services.llm_client import MODEL_REGISTRY, LLMClient

logger = structlog.get_logger()


class ShariahScreeningAgent:
    """Three-tier Shariah compliance screening agent.
    
    Tiers:
    1. MCC Blocklist: Checks if transaction MCC is in the prohibited MCC list.
    2. Keyword match: Checks if transaction text contains any forbidden keywords.
    3. LLM verification: Resolves ambiguous cases using Claude Haiku.
    """

    HARAM_MCC_CODES = {
        "5813": "drinking_places",
        "5921": "liquor_stores",
        "7995": "gambling",
        "5993": "tobacco",
        "7273": "dating_services",
        "5947": "gift_novelty_stores",
    }

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        data_dir = Path(__file__).parent.parent / "data"

        # Load blocklist definitions
        with open(data_dir / "shariah_blocklist.json", encoding="utf-8") as f:
            blocklist_data = json.load(f)
            self.blocklisted_mccs = blocklist_data.get("blocklisted_mcc", [])
            self.keyword_patterns = blocklist_data.get("keyword_patterns", [])

        # Load prompts
        with open(data_dir / "prompts" / "shariah_screening.txt", encoding="utf-8") as f:
            self.prompt_template = f.read()

        # Metadata Versioning
        config = MODEL_REGISTRY.get("shariah_screener", {})
        self.model = config.get("model", "claude-3-haiku-20240307")
        self.model_version = config.get("version", "v1.0")
        self.prompt_version = config.get("prompt_version", "shariah-v2")
        self.prompt_hash = hashlib.sha256(self.prompt_template.encode("utf-8")).hexdigest()[:8]

    async def screen(self, transaction: dict) -> dict:
        """Screen a single transaction for Shariah compliance."""
        start_time = time.perf_counter()
        tx_id = transaction.get("id")
        flags = []

        # Tier 1: MCC Blocklist check
        mcc = transaction.get("merchant_mcc")
        if mcc and str(mcc) in self.blocklisted_mccs:
            industry = self.HARAM_MCC_CODES.get(str(mcc), "prohibited_industry")
            flags.append({
                "rule": "mcc_blocklist",
                "confidence": 0.98,
                "source": "deterministic",
                "industry": industry,
                "reason": f"Merchant Category Code {mcc} is blocklisted under {industry}.",
            })

        # Tier 2: Keyword Screening check
        merchant_name = transaction.get("merchant_name") or ""
        description = transaction.get("description") or ""
        search_text = f"{merchant_name} {description}"

        matched_patterns = []
        for pattern in self.keyword_patterns:
            if re.search(pattern, search_text, re.IGNORECASE):
                matched_patterns.append(pattern)

        if matched_patterns:
            flags.append({
                "rule": "keyword_match",
                "confidence": 0.80,
                "source": "rules_engine",
                "matched_pattern": ", ".join(matched_patterns),
                "reason": (
                    f"Transaction description matched prohibited keyword "
                    f"pattern: {', '.join(matched_patterns)}"
                ),
            })

        # Tier 3: LLM verification for ambiguous cases
        # If we have keyword match flags but no absolute MCC blocklist flag,
        # we resolve ambiguity via LLM
        has_mcc_flag = any(f["rule"] == "mcc_blocklist" for f in flags)
        has_keyword_flag = any(f["rule"] == "keyword_match" for f in flags)

        if has_keyword_flag and not has_mcc_flag:
            prompt = (
                self.prompt_template
                .replace("{merchant}", merchant_name or "Unknown")
                .replace("{description}", description or "")
            )

            try:
                response = await self.llm_client.invoke(
                    model="shariah_screener",
                    messages=prompt,
                    temperature=0.0,
                )

                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.json:
                    data = response.json
                    status = data.get("status", "review")
                    reason = data.get("reason", "LLM returned review")
                    confidence = float(data.get("confidence", 0.70))
                else:
                    status = "review"
                    reason = "Failed to parse LLM JSON response"
                    confidence = 0.70

                logger.info(
                    "shariah_screening_completed",
                    transaction_id=str(tx_id),
                    agent_name="shariah_screener",
                    latency_ms=latency_ms,
                    model_version=self.model_version,
                    prompt_version=self.prompt_version,
                    prompt_hash=self.prompt_hash,
                    confidence=confidence,
                    status=status,
                )

                llm_flag = {
                    "rule": "llm_verification",
                    "confidence": confidence,
                    "source": "llm",
                    "reason": reason,
                }

                return {
                    "shariah_status": status,
                    "shariah_flags": flags + [llm_flag],
                    "shariah_confidence": confidence,
                }

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "shariah_screening_llm_failed_using_fallback",
                    transaction_id=str(tx_id),
                    error=str(e),
                )
                logger.info(
                    "shariah_screening_completed",
                    transaction_id=str(tx_id),
                    agent_name="shariah_screener",
                    latency_ms=latency_ms,
                    model_version="N/A",
                    prompt_version="N/A",
                    prompt_hash="N/A",
                    confidence=0.80,
                    status="review",
                )
                # Fallback: keep keyword flags and classify as review since LLM verification failed
                return {
                    "shariah_status": "review",
                    "shariah_flags": flags,
                    "shariah_confidence": 0.80,
                }

        # If it was a deterministic MCC blocklist violation
        if has_mcc_flag:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "shariah_screening_completed",
                transaction_id=str(tx_id),
                agent_name="shariah_screener",
                latency_ms=latency_ms,
                model_version="N/A",
                prompt_version="N/A",
                prompt_hash="N/A",
                confidence=0.98,
                status="non_compliant",
            )
            return {
                "shariah_status": "non_compliant",
                "shariah_flags": flags,
                "shariah_confidence": 0.98,
            }

        # Fully compliant transaction (no blocklists or keyword hits)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "shariah_screening_completed",
            transaction_id=str(tx_id),
            agent_name="shariah_screener",
            latency_ms=latency_ms,
            model_version="N/A",
            prompt_version="N/A",
            prompt_hash="N/A",
            confidence=1.00,
            status="compliant",
        )
        return {
            "shariah_status": "compliant",
            "shariah_flags": [],
            "shariah_confidence": 1.00,
        }
