from __future__ import annotations

import unittest.mock as mock
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.agents import (
    CategorizationAgent,
    InsightGenerationAgent,
    RecurrenceDetectionAgent,
    ShariahScreeningAgent,
    ZakatCalculationAgent,
    build_pipeline,
)
from app.models.schemas import ZakatResult
from app.services.llm_client import LLMClient, LLMResponse


@pytest.fixture
def mock_llm_client() -> mock.MagicMock:
    return mock.MagicMock(spec=LLMClient)


# --- Categorizer Agent Tests ---

async def test_categorizer_mcc_lookup(mock_llm_client: mock.MagicMock) -> None:
    agent = CategorizationAgent(llm_client=mock_llm_client)
    # MCC 5411 -> groceries, supermarket
    tx = {"id": "1", "merchant_mcc": "5411", "merchant_name": "Lulu", "amount": 100.0}
    res = await agent.categorize(tx)
    assert res["category"] == "groceries"
    assert res["subcategory"] == "supermarket"
    assert res["category_confidence"] == 0.95
    assert res["categorization_method"] == "mcc"
    mock_llm_client.invoke.assert_not_called()


async def test_categorizer_rules_engine(mock_llm_client: mock.MagicMock) -> None:
    agent = CategorizationAgent(llm_client=mock_llm_client)
    # Careem matching rules
    tx = {"id": "2", "merchant_mcc": "9999", "merchant_name": "Careem Ride", "amount": 50.0}
    res = await agent.categorize(tx)
    assert res["category"] == "transport"
    assert res["subcategory"] == "ride_hailing"
    assert res["category_confidence"] == 0.85
    assert res["categorization_method"] == "rules"
    mock_llm_client.invoke.assert_not_called()


async def test_categorizer_llm_fallback(mock_llm_client: mock.MagicMock) -> None:
    agent = CategorizationAgent(llm_client=mock_llm_client)
    tx = {
        "id": "3",
        "merchant_mcc": "9999",
        "merchant_name": "Unknown Corp",
        "amount": 200.0,
        "description": "Consulting",
    }
    
    mock_llm_client.invoke.return_value = LLMResponse(
        content='{"category": "income", "subcategory": "freelance_gig", "confidence": 0.92}'
    )
    
    res = await agent.categorize(tx)
    assert res["category"] == "income"
    assert res["subcategory"] == "freelance_gig"
    assert res["category_confidence"] == 0.92
    assert res["categorization_method"] == "llm"
    mock_llm_client.invoke.assert_called_once()


async def test_categorizer_llm_failure_degradation(mock_llm_client: mock.MagicMock) -> None:
    agent = CategorizationAgent(llm_client=mock_llm_client)
    tx = {"id": "4", "merchant_mcc": "9999", "merchant_name": "Unknown Corp", "amount": 200.0}
    
    mock_llm_client.invoke.side_effect = RuntimeError("API down")
    
    res = await agent.categorize(tx)
    assert res["category"] == "other"
    assert res["subcategory"] is None
    assert res["category_confidence"] == 0.30
    assert res["categorization_method"] == "rules"


# --- Shariah Screener Tests ---

async def test_shariah_screener_mcc_blocklist(mock_llm_client: mock.MagicMock) -> None:
    agent = ShariahScreeningAgent(llm_client=mock_llm_client)
    # MCC 5813 -> drinking places
    tx = {"id": "5", "merchant_mcc": "5813", "merchant_name": "The Tavern", "amount": 120.0}
    res = await agent.screen(tx)
    assert res["shariah_status"] == "non_compliant"
    assert len(res["shariah_flags"]) == 1
    assert res["shariah_flags"][0]["rule"] == "mcc_blocklist"
    assert res["shariah_flags"][0]["industry"] == "drinking_places"
    assert res["shariah_confidence"] == 0.98
    mock_llm_client.invoke.assert_not_called()


async def test_shariah_screener_keyword_match_triggers_llm(mock_llm_client: mock.MagicMock) -> None:
    agent = ShariahScreeningAgent(llm_client=mock_llm_client)
    tx = {
        "id": "6",
        "merchant_mcc": "9999",
        "merchant_name": "Lulu Liquors",
        "amount": 80.0,
        "description": "Juice and soda",
    }
    
    mock_llm_client.invoke.return_value = LLMResponse(
        content=(
            '{"status": "non_compliant", '
            '"reason": "Purchased alcohol establishment product", '
            '"confidence": 0.90}'
        )
    )
    
    res = await agent.screen(tx)
    assert res["shariah_status"] == "non_compliant"
    assert len(res["shariah_flags"]) == 2  # Keyword match flag + LLM flag
    assert res["shariah_confidence"] == 0.90
    mock_llm_client.invoke.assert_called_once()


async def test_shariah_screener_llm_failure_degradation(mock_llm_client: mock.MagicMock) -> None:
    agent = ShariahScreeningAgent(llm_client=mock_llm_client)
    tx = {"id": "7", "merchant_mcc": "9999", "merchant_name": "Betting Parlor", "amount": 300.0}
    
    mock_llm_client.invoke.side_effect = Exception("Anthropic overloaded")
    
    # Will hit the keyword check, fail LLM verification, and fall back to "review"
    res = await agent.screen(tx)
    assert res["shariah_status"] == "review"
    assert len(res["shariah_flags"]) == 1
    assert res["shariah_flags"][0]["rule"] == "keyword_match"
    assert res["shariah_confidence"] == 0.80


# --- Recurrence Detection Tests ---

async def test_recurrence_detector_monthly() -> None:
    agent = RecurrenceDetectionAgent()
    base_date = date(2026, 1, 1)
    
    txs = [
        {
            "id": "t1",
            "merchant_name": "Netflix Sub",
            "amount": 49.99,
            "transaction_date": base_date,
        },
        {
            "id": "t2",
            "merchant_name": "Netflix Sub",
            "amount": 49.99,
            "transaction_date": base_date + timedelta(days=30),
        },
        {
            "id": "t3",
            "merchant_name": "Netflix Sub",
            "amount": 49.99,
            "transaction_date": base_date + timedelta(days=60),
        },
        {
            "id": "t4",
            "merchant_name": "Netflix Sub",
            "amount": 49.99,
            "transaction_date": base_date + timedelta(days=90),
        },
    ]
    
    res = await agent.detect(txs)
    assert len(res) == 1
    group = res[0]
    assert group["merchant"] == "netflix sub"
    assert group["frequency"] == "monthly"
    assert group["avg_amount"] == 49.99
    assert group["next_expected"] == base_date + timedelta(days=120)
    assert len(group["transaction_ids"]) == 4


# --- Zakat Calculator Tests ---

async def test_zakat_calculator_below_nisab(mock_llm_client: mock.MagicMock) -> None:
    # Gold price: 320 AED/gram. Nisab = 320 * 85 = 27,200 AED
    agent = ZakatCalculationAgent(llm_client=mock_llm_client)
    mock_llm_client.invoke.return_value = LLMResponse(
        content="You have no Zakat due as you are below the Nisab."
    )
    profile = {
        "cash_balance": 5000.0,
        "savings_balance": 10000.0,
        "investment_value": 2000.0,
        "immediate_debts": 1000.0,
    }
    
    res = await agent.calculate(profile, gold_price_per_gram=Decimal("320.00"))
    assert isinstance(res, ZakatResult)
    assert res.eligible_assets == Decimal("16000.00")
    assert res.nisab_threshold == Decimal("27200.00")
    assert res.is_eligible is False
    assert res.zakat_due == Decimal("0.00")
    assert "below the Nisab" in res.explanation


async def test_zakat_calculator_above_nisab(mock_llm_client: mock.MagicMock) -> None:
    agent = ZakatCalculationAgent(llm_client=mock_llm_client)
    profile = {
        "cash_balance": 50000.0,
        "savings_balance": 120000.0,
        "investment_value": 80000.0,
        "immediate_debts": 30000.0,
    }
    
    mock_llm_client.invoke.return_value = LLMResponse(content="Your Zakat due is AED 5,500.")
    
    res = await agent.calculate(profile, gold_price_per_gram=Decimal("320.00"))
    assert res.eligible_assets == Decimal("220000.00")
    assert res.is_eligible is True
    # Zakat = 2.5% of 220,000 = 5,500
    assert res.zakat_due == Decimal("5500.00")
    assert res.explanation == "Your Zakat due is AED 5,500."


# --- Insight Generator Tests ---

async def test_insight_generator_success(mock_llm_client: mock.MagicMock) -> None:
    agent = InsightGenerationAgent(llm_client=mock_llm_client)
    
    mock_llm_client.invoke.return_value = LLMResponse(
        content=(
            '{"insights": [{"title": "Israf Warning", '
            '"body": "Reduce dining spend", '
            '"severity": "warning", "data": {}}]}'
        )
    )
    
    state = {
        "categorized": [{"id": "1", "amount": 100.0, "category": "food_dining"}],
        "shariah_screened": [],
        "recurrence_groups": [],
    }
    
    res = await agent.generate(state)
    assert len(res) == 1
    assert res[0]["title"] == "Israf Warning"
    assert res[0]["severity"] == "warning"


# --- Orchestrator Pipeline Tests ---

async def test_orchestrator_pipeline_run() -> None:
    # Ingest mock raw transaction, verify LangGraph executes parallel
    # categorization/screening nodes, merge, insights, profile
    txs = [
        {
            "id": "t1",
            "account_id": "00000000-0000-0000-0000-000000000000",
            "amount": 120.0,
            "currency": "AED",
            "direction": "debit",
            "merchant_name": "Lulu Hypermarket",
            "merchant_mcc": "5411",
            "description": "weekly groceries",
            "transaction_date": "2026-06-01",
        }
    ]
    
    workflow = build_pipeline()
    
    # We patch LLM calls to prevent live hits during orchestrator tests
    with (
        mock.patch("app.agents.orchestrator.categorizer_agent.llm_client.invoke") as mock_invoke,
        mock.patch(
            "app.services.gold_price.GoldPriceService.get_gold_price",
            return_value=Decimal("320.00"),
        ),
    ):
        mock_invoke.return_value = LLMResponse(content="{}")
        
        state = {
            "raw_transactions": txs,
            "mapped_transactions": [],
            "categorized": [],
            "shariah_screened": [],
            "recurrence_groups": [],
            "insights": [],
            "profile_updates": {},
            "errors": [],
            "metadata": {},
        }
        
        result = await workflow.ainvoke(state)
        
        assert len(result["mapped_transactions"]) == 1
        merged_tx = result["mapped_transactions"][0]
        
        # Verify merged features
        assert merged_tx["category"] == "groceries"
        assert merged_tx["subcategory"] == "supermarket"
        assert merged_tx["shariah_status"] == "compliant"
        assert merged_tx["is_recurring"] is False
        assert merged_tx["cashflow_type"] == "essential"
        
        # Verify Zakat outputs in profile updates
        profile = result["profile_updates"]
        assert profile["avg_monthly_spend"] == 120.0
        assert profile["avg_monthly_income"] == 0.0
        assert profile["zakat_due"] == 5500.0  # default starting profile calculation


# --- Metadata & Versioning Verification ---

def test_agent_metadata_versioning() -> None:
    llm = mock.MagicMock(spec=LLMClient)
    
    categorizer = CategorizationAgent(llm_client=llm)
    screener = ShariahScreeningAgent(llm_client=llm)
    recurrence = RecurrenceDetectionAgent()
    zakat = ZakatCalculationAgent(llm_client=llm)
    insight = InsightGenerationAgent(llm_client=llm)
    
    # Verify that all agents define model and prompt version details
    for agent in [categorizer, screener, recurrence, zakat, insight]:
        assert hasattr(agent, "model")
        assert hasattr(agent, "model_version")
        assert hasattr(agent, "prompt_version")
        assert hasattr(agent, "prompt_hash")
        
        # For non-LLM agents, it should explicitly mark as N/A
        if isinstance(agent, RecurrenceDetectionAgent):
            assert agent.model == "N/A"
            assert agent.prompt_version == "N/A"
            assert agent.prompt_hash == "N/A"
        else:
            # LLM-based agents must have actual names and 8-char hex hashes
            assert agent.model != "N/A"
            assert agent.prompt_version != "N/A"
            assert len(agent.prompt_hash) == 8
            assert all(c in "0123456789abcdef" for c in agent.prompt_hash)
