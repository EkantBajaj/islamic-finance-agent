from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.categorizer import CategorizationAgent
from app.agents.insight_generator import InsightGenerationAgent
from app.agents.recurrence_detector import RecurrenceDetectionAgent
from app.agents.shariah_screener import ShariahScreeningAgent
from app.agents.zakat_calculator import ZakatCalculationAgent
from app.models.state import TransactionState
from app.services.llm_client import LLMClient

# Shared service instances
llm_client = LLMClient()
categorizer_agent = CategorizationAgent(llm_client)
shariah_agent = ShariahScreeningAgent(llm_client)
recurrence_agent = RecurrenceDetectionAgent()
zakat_agent = ZakatCalculationAgent(llm_client)
insight_agent = InsightGenerationAgent(llm_client)


async def ingest_node(state: TransactionState) -> dict[str, Any]:
    """Ingests raw transactions from the state inputs."""
    raw = state.get("raw_transactions", [])
    # Simply forwards raw transactions or loads them if needed
    return {"raw_transactions": raw}


def clean_merchant_name(name: str | None) -> str:
    """Utility to clean merchant name strings."""
    if not name:
        return "Unknown"
    # Basic cleaning
    clean = re.sub(r"\d+", "", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or name


async def normalize_node(state: TransactionState) -> dict[str, Any]:
    """Normalizes raw transaction payloads into mapped transaction formats."""
    raw_txs = state.get("raw_transactions", [])
    mapped = []

    for tx in raw_txs:
        # Standardize dictionaries or objects
        is_dict = isinstance(tx, dict)
        raw_payload = tx.get("raw_payload", {}) if is_dict else getattr(tx, "raw_payload", {})
        
        tx_id = tx.get("id") if is_dict else getattr(tx, "id", None)
        external_id = tx.get("external_id") if is_dict else getattr(tx, "external_id", None)
        if not external_id:
            external_id = raw_payload.get("external_id")
            
        account_id = tx.get("account_id") if is_dict else getattr(tx, "account_id", None)
        amount = tx.get("amount") if is_dict else getattr(tx, "amount", Decimal("0"))
        currency = tx.get("currency", "AED") if is_dict else getattr(tx, "currency", "AED")
        direction = tx.get("direction", "debit") if is_dict else getattr(tx, "direction", "debit")
        counterparty = tx.get("counterparty") if is_dict else getattr(tx, "counterparty", None)
        booked_at = tx.get("booked_at") if is_dict else getattr(tx, "booked_at", None)

        merchant_name = tx.get("merchant_name") if is_dict else getattr(tx, "merchant_name", None)
        if not merchant_name:
            merchant_name = raw_payload.get("merchant_name") or ""

        merchant_mcc = tx.get("merchant_mcc") if is_dict else getattr(tx, "merchant_mcc", None)
        if not merchant_mcc:
            merchant_mcc = raw_payload.get("merchant_mcc") or ""

        description = tx.get("description") if is_dict else getattr(tx, "description", None)
        if not description:
            description = raw_payload.get("description") or ""

        tx_date = tx.get("transaction_date") if is_dict else getattr(tx, "transaction_date", None)
        if isinstance(tx_date, str):
            tx_date = datetime.strptime(tx_date[:10], "%Y-%m-%d").date()
        elif not tx_date:
            raw_date = raw_payload.get("transaction_date")
            if isinstance(raw_date, str):
                tx_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
            else:
                tx_date = date.today()


        mapped.append({
            "id": tx_id or uuid.uuid4(),
            "raw_id": tx_id,
            "external_id": external_id,
            "account_id": account_id,
            "amount": Decimal(str(amount)),
            "currency": currency,
            "direction": direction,
            "counterparty": counterparty,
            "merchant_name": clean_merchant_name(merchant_name),
            "merchant_mcc": str(merchant_mcc) if merchant_mcc else None,
            "description": description,
            "transaction_date": tx_date,
            "booked_at": booked_at,
        })

    return {"mapped_transactions": mapped}


async def categorize_node(state: TransactionState) -> dict[str, Any]:
    """Parallel Node: Classifies transactions by categories and subcategories."""
    mapped = state.get("mapped_transactions", [])
    categorized = []
    for tx in mapped:
        res = await categorizer_agent.categorize(tx)
        enriched = dict(tx)
        enriched.update(res)
        categorized.append(enriched)
    return {"categorized": categorized}


async def shariah_screen_node(state: TransactionState) -> dict[str, Any]:
    """Parallel Node: Screens transactions for Shariah compliance."""
    mapped = state.get("mapped_transactions", [])
    screened = []
    for tx in mapped:
        res = await shariah_agent.screen(tx)
        enriched = dict(tx)
        enriched.update(res)
        screened.append(enriched)
    return {"shariah_screened": screened}


async def detect_recurrence_node(state: TransactionState) -> dict[str, Any]:
    """Parallel Node: Statistical recurrence detection engine."""
    mapped = state.get("mapped_transactions", [])
    groups = await recurrence_agent.detect(mapped)
    return {"recurrence_groups": groups}


async def merge_node(state: TransactionState) -> dict[str, Any]:
    """Fan-in Node: Merges outcomes from parallel categorization, screening, and recurrence."""
    categorized = {tx["id"]: tx for tx in state.get("categorized", [])}
    shariah = {tx["id"]: tx for tx in state.get("shariah_screened", [])}
    recurrence_groups = state.get("recurrence_groups", [])

    # Map transaction ID to its recurrence properties
    recurrence_map = {}
    for group in recurrence_groups:
        group_id = group.get("id")
        freq = group.get("frequency")
        for tx_id in group.get("transaction_ids", []):
            recurrence_map[tx_id] = {
                "is_recurring": True,
                "recurrence_group_id": group_id,
                "recurrence_frequency": freq,
            }

    merged = []
    for tx_id, tx_cat in categorized.items():
        tx_shariah = shariah.get(tx_id, {})
        tx_recur = recurrence_map.get(tx_id, {
            "is_recurring": False,
            "recurrence_group_id": None,
            "recurrence_frequency": None,
        })

        # Match Cashflow Type: Essential, Discretionary, Income, Transfer
        cat = tx_cat.get("category", "other")
        dir_val = tx_cat.get("direction", "debit")

        if dir_val == "credit":
            cashflow_type = "income"
        elif cat in ["groceries", "utilities", "housing", "health_medical", "education"]:
            cashflow_type = "essential"
        elif cat in ["transfers"]:
            cashflow_type = "transfer"
        else:
            cashflow_type = "discretionary"

        enriched = dict(tx_cat)
        enriched.update({
            "shariah_status": tx_shariah.get("shariah_status", "review"),
            "shariah_flags": tx_shariah.get("shariah_flags", []),
            "shariah_confidence": tx_shariah.get("shariah_confidence"),
            "is_recurring": tx_recur["is_recurring"],
            "recurrence_group_id": tx_recur["recurrence_group_id"],
            "recurrence_frequency": tx_recur["recurrence_frequency"],
            "cashflow_type": cashflow_type,
        })
        merged.append(enriched)

    return {"mapped_transactions": merged}


async def generate_insights_node(state: TransactionState) -> dict[str, Any]:
    """Sequential Node: Generates natural language insights from merged transactions."""
    merged = state.get("mapped_transactions", [])
    recurrence_groups = state.get("recurrence_groups", [])

    insight_state = {
        "categorized": merged,
        "shariah_screened": merged,
        "recurrence_groups": recurrence_groups,
    }

    insights = await insight_agent.generate(insight_state)
    return {"insights": insights}


async def update_profile_node(state: TransactionState) -> dict[str, Any]:
    """Sequential Node: Calculates financial stats and Zakat due, updating profiles."""
    txs = state.get("mapped_transactions", [])
    if not txs:
        return {"profile_updates": {}}

    account_id = txs[0].get("account_id")

    # Shariah Score
    compliant_txs = [t for t in txs if t.get("shariah_status") == "compliant"]
    shariah_score = len(compliant_txs) / len(txs) if txs else 1.0

    # Income & Spending
    total_income = Decimal("0")
    total_spend = Decimal("0")
    cat_spend = {}

    for t in txs:
        amt = Decimal(str(t.get("amount") or 0.00))
        direction = t.get("direction")
        if direction == "credit":
            total_income += amt
        else:
            total_spend += amt
            cat = t.get("category", "other")
            cat_spend[cat] = cat_spend.get(cat, Decimal("0")) + amt

    top_categories = []
    for cat, amt in cat_spend.items():
        pct = (amt / total_spend * 100) if total_spend > Decimal("0") else Decimal("0")
        top_categories.append({
            "category": cat,
            "amount": float(amt),
            "pct": float(round(pct, 2)),
        })
    top_categories.sort(key=lambda x: x["amount"], reverse=True)

    # Zakat calculation using default starting assets for profile calculations
    default_profile_assets = {
        "cash_balance": Decimal("50000.00"),
        "savings_balance": Decimal("120000.00"),
        "investment_value": Decimal("80000.00"),
        "immediate_debts": Decimal("30000.00"),
    }

    zakat_res = await zakat_agent.calculate(default_profile_assets)

    profile_updates = {
        "account_id": account_id,
        "avg_monthly_income": float(total_income),
        "avg_monthly_spend": float(total_spend),
        "shariah_compliance_score": float(round(shariah_score, 2)),
        "top_categories": top_categories,
        "zakat_eligible_assets": float(zakat_res.eligible_assets),
        "zakat_nisab_threshold": float(zakat_res.nisab_threshold),
        "zakat_due": float(zakat_res.zakat_due),
        "zakat_year_start": date.today(),
    }

    return {"profile_updates": profile_updates}


def build_pipeline() -> StateGraph:
    """Builds and compiles the LangGraph StateGraph pipeline."""
    workflow = StateGraph(TransactionState)

    # Add Nodes
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("normalize", normalize_node)
    workflow.add_node("categorize", categorize_node)
    workflow.add_node("shariah_screen", shariah_screen_node)
    workflow.add_node("detect_recurrence", detect_recurrence_node)
    workflow.add_node("merge", merge_node)
    workflow.add_node("generate_insights", generate_insights_node)
    workflow.add_node("update_profile", update_profile_node)

    # Define edges
    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "normalize")

    # Fan out to parallel paths
    workflow.add_edge("normalize", "categorize")
    workflow.add_edge("normalize", "shariah_screen")
    workflow.add_edge("normalize", "detect_recurrence")

    # Fan in to merge
    workflow.add_edge("categorize", "merge")
    workflow.add_edge("shariah_screen", "merge")
    workflow.add_edge("detect_recurrence", "merge")

    # Sequential final processing
    workflow.add_edge("merge", "generate_insights")
    workflow.add_edge("generate_insights", "update_profile")
    workflow.add_edge("update_profile", END)

    return workflow.compile()
