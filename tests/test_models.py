from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.database import Base
from app.models.schemas import DateRangeFilter, RawTransactionInput


def test_medallion_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "raw_transactions",
        "mapped_transactions",
        "enriched_transactions",
        "financial_insights",
        "financial_profile",
    }


def test_transaction_input_normalizes_currency() -> None:
    transaction = RawTransactionInput(
        external_id="txn-1",
        amount=Decimal("42.50"),
        currency="aed",
        direction="debit",
        transaction_date="2026-06-13",
    )

    assert transaction.currency == "AED"
    assert transaction.amount == Decimal("42.50")


def test_transaction_input_rejects_invalid_currency() -> None:
    with pytest.raises(ValidationError):
        RawTransactionInput(
            external_id="txn-1",
            amount=Decimal("42.50"),
            currency="US",
            direction="debit",
            transaction_date="2026-06-13",
        )


def test_date_range_rejects_inverted_dates() -> None:
    with pytest.raises(ValidationError, match="date_to must be on or after date_from"):
        DateRangeFilter(date_from="2026-06-14", date_to="2026-06-13")

