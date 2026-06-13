from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.zakat_calculator import ZakatCalculationAgent
from app.core.database import get_db
from app.models.database import FinancialProfile
from app.models.schemas import ZakatResult
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/zakat", tags=["zakat"])

# Share an LLM client and agent instance
llm_client = LLMClient()
zakat_agent = ZakatCalculationAgent(llm_client)


@router.get("/{account_id}", response_model=ZakatResult)
async def get_zakat_calculation(
    account_id: UUID,
    cash_balance: Decimal | None = None,
    savings_balance: Decimal | None = None,
    investment_value: Decimal | None = None,
    immediate_debts: Decimal | None = None,
    db: AsyncSession = Depends(get_db),
) -> ZakatResult:
    """Calculate Zakat obligation dynamically.
    
    If balances are not provided as query parameters, they fallback to profile values or
    default prototype balances (AED 50k cash, 120k savings, 80k investments, 30k debts).
    """
    stmt = select(FinancialProfile).where(FinancialProfile.account_id == account_id)
    res = await db.execute(stmt)
    profile = res.scalar_one_or_none()

    # Determine values
    cash = cash_balance
    if cash is None:
        cash = (
            profile.zakat_eligible_assets
            if (profile and profile.zakat_eligible_assets is not None)
            else Decimal("50000.00")
        )

    savings = savings_balance
    if savings is None:
        savings = Decimal("120000.00")

    investments = investment_value
    if investments is None:
        investments = Decimal("80000.00")

    debts = immediate_debts
    if debts is None:
        debts = Decimal("30000.00")

    profile_data = {
        "cash_balance": cash,
        "savings_balance": savings,
        "investment_value": investments,
        "immediate_debts": debts,
    }

    # Run Zakat Calculation Agent
    result = await zakat_agent.calculate(profile_data)
    return result
