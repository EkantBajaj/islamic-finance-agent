from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import FinancialProfile
from app.models.schemas import FinancialProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{account_id}", response_model=FinancialProfileResponse)
async def get_financial_profile(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FinancialProfileResponse:
    """Retrieve financial profile statistics and RFM segmentation details."""
    stmt = select(FinancialProfile).where(FinancialProfile.account_id == account_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Financial profile not found for account {account_id}",
        )

    return FinancialProfileResponse.model_validate(profile)
