from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import FinancialInsight
from app.models.schemas import InsightResponse

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/{account_id}", response_model=list[InsightResponse])
async def get_financial_insights(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[InsightResponse]:
    """Retrieve financial insights generated for a given user account."""
    stmt = (
        select(FinancialInsight)
        .where(FinancialInsight.account_id == account_id)
        .order_by(FinancialInsight.generated_at.desc())
    )
    result = await db.execute(stmt)
    insights = result.scalars().all()

    return [InsightResponse.model_validate(ins) for ins in insights]
