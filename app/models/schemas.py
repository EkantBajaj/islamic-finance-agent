from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

CurrencyCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=3),
]
Confidence = Annotated[Decimal, Field(ge=0, le=1, max_digits=3, decimal_places=2)]
Money = Annotated[Decimal, Field(max_digits=15, decimal_places=2)]


class Direction(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ShariahStatus(StrEnum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    REVIEW = "review"


class CategorizationMethod(StrEnum):
    MCC = "mcc"
    RULES = "rules"
    LLM = "llm"
    HYBRID = "hybrid"


class CashflowType(StrEnum):
    ESSENTIAL = "essential"
    DISCRETIONARY = "discretionary"
    INCOME = "income"
    TRANSFER = "transfer"


class InsightSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ACTION = "action"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RawTransactionInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    amount: Money
    currency: CurrencyCode = "AED"
    direction: Direction
    transaction_date: date
    merchant_name: str | None = Field(default=None, max_length=255)
    merchant_mcc: str | None = Field(default=None, max_length=10)
    counterparty: str | None = Field(default=None, max_length=255)
    description: str | None = None
    booked_at: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="manual", min_length=1, max_length=50)


class TransactionIngestRequest(BaseModel):
    account_id: UUID
    transactions: list[RawTransactionInput] = Field(min_length=1, max_length=1000)


class PipelineAccepted(BaseModel):
    pipeline_id: UUID
    status: Literal["accepted"] = "accepted"
    ws_channel: str


class ShariahFlag(BaseModel):
    rule: str
    confidence: Confidence
    source: str
    industry: str | None = None
    matched_pattern: str | None = None
    reason: str | None = None


class EnrichedTransactionResponse(ORMModel):
    id: UUID
    mapped_id: UUID
    account_id: UUID
    category: str
    subcategory: str | None
    category_confidence: Confidence | None
    categorization_method: CategorizationMethod | None
    shariah_status: ShariahStatus
    shariah_flags: list[ShariahFlag] = Field(default_factory=list)
    shariah_confidence: Confidence | None
    is_recurring: bool
    recurrence_group_id: UUID | None
    recurrence_frequency: str | None
    cashflow_type: CashflowType | None
    enriched_at: datetime


class PaginatedTransactions(BaseModel):
    items: list[EnrichedTransactionResponse]
    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class InsightResponse(ORMModel):
    id: UUID
    account_id: UUID
    insight_type: str
    period_start: date
    period_end: date
    title: str
    body: str
    data: dict[str, Any] | None
    severity: InsightSeverity
    is_read: bool
    generated_at: datetime


class ZakatCalculationRequest(BaseModel):
    cash_balance: Money = Decimal("0")
    savings_balance: Money = Decimal("0")
    investment_value: Money = Decimal("0")
    immediate_debts: Money = Decimal("0")
    gold_price_per_gram: Money | None = None


class ZakatResult(BaseModel):
    eligible_assets: Money
    nisab_threshold: Money
    zakat_due: Money
    is_eligible: bool
    explanation: str
    calculated_at: datetime


class CategoryShare(BaseModel):
    category: str
    amount: Money
    pct: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class FinancialProfileResponse(ORMModel):
    id: UUID
    account_id: UUID
    rfm_recency: int | None
    rfm_frequency: int | None
    rfm_monetary: Money | None
    rfm_segment: str | None
    zakat_eligible_assets: Money | None
    zakat_nisab_threshold: Money | None
    zakat_due: Money | None
    zakat_year_start: date | None
    avg_monthly_income: Money | None
    avg_monthly_spend: Money | None
    top_categories: list[CategoryShare] | None
    shariah_compliance_score: Confidence | None
    updated_at: datetime


class DependencyHealth(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy", "not_configured"]
    latency_ms: float | None = Field(default=None, ge=0)
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    postgres: DependencyHealth
    redis: DependencyHealth
    llm_provider: DependencyHealth
    version: str


class StageStartedEvent(BaseModel):
    type: Literal["stage_started"] = "stage_started"
    stage: str
    timestamp: datetime


class StageCompletedEvent(BaseModel):
    type: Literal["stage_completed"] = "stage_completed"
    stage: str
    result_count: int = Field(ge=0)
    duration_ms: float = Field(ge=0)


class StageFailedEvent(BaseModel):
    type: Literal["stage_failed"] = "stage_failed"
    stage: str
    error: str
    fallback_used: bool


class PipelineSummary(BaseModel):
    total: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    error_count: int = Field(default=0, ge=0)


class PipelineCompletedEvent(BaseModel):
    type: Literal["pipeline_completed"] = "pipeline_completed"
    summary: PipelineSummary


class PipelineFailedEvent(BaseModel):
    type: Literal["pipeline_failed"] = "pipeline_failed"
    error: str


PipelineEvent = (
    StageStartedEvent
    | StageCompletedEvent
    | StageFailedEvent
    | PipelineCompletedEvent
    | PipelineFailedEvent
)


class DateRangeFilter(BaseModel):
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_range(self) -> DateRangeFilter:
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self
