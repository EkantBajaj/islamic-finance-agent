from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for the medallion data model."""


class RawTransaction(Base):
    __tablename__ = "raw_transactions"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_raw_transactions_processing_status",
        ),
        UniqueConstraint("source", "external_id", name="uq_raw_transactions_source_external"),
        Index("idx_raw_txn_account", "account_id"),
        Index("idx_raw_txn_status", "processing_status"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )


class MappedTransaction(Base):
    __tablename__ = "mapped_transactions"
    __table_args__ = (
        CheckConstraint("direction IN ('credit', 'debit')", name="ck_mapped_direction"),
        Index("idx_mapped_account", "account_id"),
        Index("idx_mapped_date", "transaction_date"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("raw_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(255))
    merchant_name: Mapped[str | None] = mapped_column(String(255))
    merchant_mcc: Mapped[str | None] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EnrichedTransaction(Base):
    __tablename__ = "enriched_transactions"
    __table_args__ = (
        CheckConstraint(
            "category_confidence BETWEEN 0 AND 1", name="ck_enriched_category_confidence"
        ),
        CheckConstraint(
            "shariah_confidence BETWEEN 0 AND 1", name="ck_enriched_shariah_confidence"
        ),
        CheckConstraint(
            "shariah_status IN ('compliant', 'non_compliant', 'review')",
            name="ck_enriched_shariah_status",
        ),
        CheckConstraint(
            "categorization_method IS NULL OR "
            "categorization_method IN ('mcc', 'rules', 'llm', 'hybrid')",
            name="ck_enriched_categorization_method",
        ),
        CheckConstraint(
            "cashflow_type IS NULL OR "
            "cashflow_type IN ('essential', 'discretionary', 'income', 'transfer')",
            name="ck_enriched_cashflow_type",
        ),
        Index("idx_enriched_account", "account_id"),
        Index("idx_enriched_category", "category"),
        Index("idx_enriched_shariah", "shariah_status"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    mapped_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("mapped_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(50))
    category_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    categorization_method: Mapped[str | None] = mapped_column(String(20))
    shariah_status: Mapped[str] = mapped_column(String(20), nullable=False)
    shariah_flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    shariah_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    is_recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    recurrence_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    recurrence_frequency: Mapped[str | None] = mapped_column(String(20))
    cashflow_type: Mapped[str | None] = mapped_column(String(20))
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FinancialInsight(Base):
    __tablename__ = "financial_insights"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_insights_period"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'action')", name="ck_insights_severity"
        ),
        Index("idx_insights_account", "account_id"),
        Index("idx_insights_period", "account_id", "period_start", "period_end"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    severity: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'info'")
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FinancialProfile(Base):
    __tablename__ = "financial_profile"
    __table_args__ = (
        CheckConstraint(
            "shariah_compliance_score BETWEEN 0 AND 1",
            name="ck_profile_shariah_compliance_score",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True
    )
    rfm_recency: Mapped[int | None] = mapped_column(Integer)
    rfm_frequency: Mapped[int | None] = mapped_column(Integer)
    rfm_monetary: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    rfm_segment: Mapped[str | None] = mapped_column(String(30))
    zakat_eligible_assets: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    zakat_nisab_threshold: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    zakat_due: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    zakat_year_start: Mapped[date | None] = mapped_column(Date)
    avg_monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    avg_monthly_spend: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    top_categories: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    shariah_compliance_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

