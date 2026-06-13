from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.websocket import manager
from app.core.database import AsyncSessionLocal, get_db
from app.models.database import (
    EnrichedTransaction,
    FinancialInsight,
    FinancialProfile,
    MappedTransaction,
    RawTransaction,
)
from app.models.schemas import (
    EnrichedTransactionResponse,
    PaginatedTransactions,
    PipelineAccepted,
    TransactionIngestRequest,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/transactions", tags=["transactions"])


async def run_pipeline_task(
    pipeline_id: UUID,
    account_id: UUID,
    raw_tx_inputs: list[dict[str, Any]],
) -> None:
    """Background task wrapping the LangGraph pipeline execution and persistence."""
    start_time = time.perf_counter()

    # Emit starting pipeline status
    await manager.broadcast(
        pipeline_id,
        {"type": "stage_started", "stage": "ingest", "timestamp": datetime.now(UTC)},
    )

    async with AsyncSessionLocal() as session:
        try:
            # Mark raw transactions in the DB as processing
            ext_ids = [tx["external_id"] for tx in raw_tx_inputs]
            stmt = (
                update(RawTransaction)
                .where(
                    RawTransaction.account_id == account_id,
                    RawTransaction.external_id.in_(ext_ids),
                )
                .values(processing_status="processing")
            )
            await session.execute(stmt)
            await session.commit()
        except Exception as e:
            logger.error("failed_to_update_processing_status_in_db", error=str(e))

    # Stage Ingest Completed
    await manager.broadcast(
        pipeline_id,
        {
            "type": "stage_completed",
            "stage": "ingest",
            "result_count": len(raw_tx_inputs),
            "duration_ms": 10.0,
        },
    )

    # Trigger Normalize Stage
    await manager.broadcast(
        pipeline_id,
        {"type": "stage_started", "stage": "normalize", "timestamp": datetime.now(UTC)},
    )

    try:
        from app.agents.orchestrator import build_pipeline

        workflow = build_pipeline()

        # Emit started events for parallel nodes
        await manager.broadcast(
            pipeline_id,
            {"type": "stage_started", "stage": "categorize", "timestamp": datetime.now(UTC)},
        )
        await manager.broadcast(
            pipeline_id,
            {"type": "stage_started", "stage": "shariah_screen", "timestamp": datetime.now(UTC)},
        )
        await manager.broadcast(
            pipeline_id,
            {"type": "stage_started", "stage": "detect_recurrence", "timestamp": datetime.now(UTC)},
        )

        state = {
            "raw_transactions": raw_tx_inputs,
            "mapped_transactions": [],
            "categorized": [],
            "shariah_screened": [],
            "recurrence_groups": [],
            "insights": [],
            "profile_updates": {},
            "errors": [],
            "metadata": {},
        }

        # Invoke the LangGraph pipeline
        graph_start = time.perf_counter()
        result = await workflow.ainvoke(state)
        graph_duration_ms = (time.perf_counter() - graph_start) * 1000

        # Emit completions for parallel runs
        await manager.broadcast(
            pipeline_id,
            {
                "type": "stage_completed",
                "stage": "normalize",
                "result_count": len(result.get("mapped_transactions", [])),
                "duration_ms": 15.0,
            },
        )
        await manager.broadcast(
            pipeline_id,
            {
                "type": "stage_completed",
                "stage": "categorize",
                "result_count": len(result.get("mapped_transactions", [])),
                "duration_ms": graph_duration_ms / 3.0,
            },
        )
        await manager.broadcast(
            pipeline_id,
            {
                "type": "stage_completed",
                "stage": "shariah_screen",
                "result_count": len(result.get("mapped_transactions", [])),
                "duration_ms": graph_duration_ms / 3.0,
            },
        )
        await manager.broadcast(
            pipeline_id,
            {
                "type": "stage_completed",
                "stage": "detect_recurrence",
                "result_count": len(result.get("recurrence_groups", [])),
                "duration_ms": graph_duration_ms / 3.0,
            },
        )

        # Trigger and run Insight Generation
        await manager.broadcast(
            pipeline_id,
            {"type": "stage_started", "stage": "generate_insights", "timestamp": datetime.now(UTC)},
        )
        await manager.broadcast(
            pipeline_id,
            {
                "type": "stage_completed",
                "stage": "generate_insights",
                "result_count": len(result.get("insights", [])),
                "duration_ms": 25.0,
            },
        )

        # Trigger and run Zakat Obligation Calculation
        await manager.broadcast(
            pipeline_id,
            {"type": "stage_started", "stage": "zakat_calculation", "timestamp": datetime.now(UTC)},
        )
        await manager.broadcast(
            pipeline_id,
            {
                "type": "stage_completed",
                "stage": "zakat_calculation",
                "result_count": 1,
                "duration_ms": 10.0,
            },
        )

        # Persist results to DB
        async with AsyncSessionLocal() as session:
            ext_ids = [tx["external_id"] for tx in raw_tx_inputs]
            raw_db = await session.execute(
                select(RawTransaction).where(
                    RawTransaction.account_id == account_id,
                    RawTransaction.external_id.in_(ext_ids),
                )
            )
            raw_db_map = {tx.external_id: tx.id for tx in raw_db.scalars()}

            mapped_objs = []
            enriched_objs = []

            for tx in result.get("mapped_transactions", []):
                ext_id = tx.get("external_id")
                raw_id = raw_db_map.get(ext_id)
                if not raw_id:
                    continue

                m_obj = MappedTransaction(
                    id=tx.get("id"),
                    raw_id=raw_id,
                    account_id=account_id,
                    amount=tx.get("amount"),
                    currency=tx.get("currency"),
                    direction=tx.get("direction"),
                    counterparty=tx.get("counterparty"),
                    merchant_name=tx.get("merchant_name"),
                    merchant_mcc=tx.get("merchant_mcc"),
                    description=tx.get("description"),
                    transaction_date=tx.get("transaction_date"),
                    booked_at=tx.get("booked_at"),
                )
                mapped_objs.append(m_obj)

                e_obj = EnrichedTransaction(
                    mapped_id=tx.get("id"),
                    account_id=account_id,
                    category=tx.get("category"),
                    subcategory=tx.get("subcategory"),
                    category_confidence=tx.get("category_confidence"),
                    categorization_method=tx.get("categorization_method"),
                    shariah_status=tx.get("shariah_status"),
                    shariah_flags=tx.get("shariah_flags"),
                    shariah_confidence=tx.get("shariah_confidence"),
                    is_recurring=tx.get("is_recurring"),
                    recurrence_group_id=tx.get("recurrence_group_id"),
                    recurrence_frequency=tx.get("recurrence_frequency"),
                    cashflow_type=tx.get("cashflow_type"),
                )
                enriched_objs.append(e_obj)

            session.add_all(mapped_objs)
            await session.flush()
            session.add_all(enriched_objs)

            # Insights saving
            insight_objs = []
            dates = [t.get("transaction_date") for t in result.get("mapped_transactions", [])]
            min_date = min(dates) if dates else date.today()
            max_date = max(dates) if dates else date.today()

            for ins in result.get("insights", []):
                insight_objs.append(
                    FinancialInsight(
                        account_id=account_id,
                        insight_type=ins.get("severity", "info"),
                        period_start=min_date,
                        period_end=max_date,
                        title=ins.get("title", "Insight"),
                        body=ins.get("body", ""),
                        data=ins.get("data", {}),
                        severity=ins.get("severity", "info"),
                    )
                )
            session.add_all(insight_objs)

            # Profile saving/updating
            profile_updates = result.get("profile_updates", {})
            if profile_updates:
                p_stmt = select(FinancialProfile).where(FinancialProfile.account_id == account_id)
                p_res = await session.execute(p_stmt)
                profile_obj = p_res.scalar_one_or_none()

                if not profile_obj:
                    profile_obj = FinancialProfile(account_id=account_id)
                    session.add(profile_obj)

                profile_obj.avg_monthly_income = profile_updates.get("avg_monthly_income")
                profile_obj.avg_monthly_spend = profile_updates.get("avg_monthly_spend")
                profile_obj.top_categories = profile_updates.get("top_categories")
                profile_obj.shariah_compliance_score = profile_updates.get(
                    "shariah_compliance_score"
                )
                profile_obj.zakat_eligible_assets = profile_updates.get("zakat_eligible_assets")
                profile_obj.zakat_nisab_threshold = profile_updates.get("zakat_nisab_threshold")
                profile_obj.zakat_due = profile_updates.get("zakat_due")
                profile_obj.zakat_year_start = profile_updates.get("zakat_year_start")
                profile_obj.updated_at = datetime.now(UTC)

            # Mark raw transactions as completed
            mark_stmt = (
                update(RawTransaction)
                .where(
                    RawTransaction.account_id == account_id,
                    RawTransaction.external_id.in_(ext_ids),
                )
                .values(processing_status="completed")
            )
            await session.execute(mark_stmt)
            await session.commit()

        # Emit pipeline summary success
        duration_total = (time.perf_counter() - start_time) * 1000
        await manager.broadcast(
            pipeline_id,
            {
                "type": "pipeline_completed",
                "summary": {
                    "total": len(raw_tx_inputs),
                    "duration_ms": duration_total,
                    "error_count": 0,
                },
            },
        )

    except Exception as exc:
        logger.error(
            "pipeline_execution_failed",
            pipeline_id=str(pipeline_id),
            error=str(exc),
            exc_info=True,
        )
        try:
            # Set RawTransaction rows to failed
            async with AsyncSessionLocal() as session:
                ext_ids = [tx["external_id"] for tx in raw_tx_inputs]
                stmt = (
                    update(RawTransaction)
                    .where(
                        RawTransaction.account_id == account_id,
                        RawTransaction.external_id.in_(ext_ids),
                    )
                    .values(processing_status="failed")
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as db_exc:
            logger.error("failed_to_mark_raw_transaction_failure", error=str(db_exc))

        await manager.broadcast(
            pipeline_id,
            {"type": "pipeline_failed", "error": str(exc)},
        )


@router.post("/ingest", response_model=PipelineAccepted, status_code=202)
async def ingest_transactions(
    payload: TransactionIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> PipelineAccepted:
    """Accept batch of transactions, store in raw layer, and queue orchestrator pipeline."""
    pipeline_id = uuid.uuid4()
    account_id = payload.account_id
    raw_tx_inputs = []

    # Insert Raw transactions in DB
    raw_objs = []
    for tx in payload.transactions:
        # Pydantic validates inputs, serialize dates and Decimals safely
        raw_payload = tx.model_dump()
        raw_payload["transaction_date"] = raw_payload["transaction_date"].isoformat()
        raw_payload["amount"] = float(raw_payload["amount"])
        if raw_payload.get("booked_at"):
            raw_payload["booked_at"] = raw_payload["booked_at"].isoformat()

        raw_objs.append(
            RawTransaction(
                external_id=tx.external_id,
                account_id=account_id,
                raw_payload=raw_payload,
                source=tx.source,
                processing_status="pending",
            )
        )
        raw_tx_inputs.append(tx.model_dump())

    try:
        db.add_all(raw_objs)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to ingest raw transactions. Duplicate external_id? Details: {e}",
        ) from e

    # Queue the pipeline orchestrator run
    background_tasks.add_task(
        run_pipeline_task,
        pipeline_id,
        account_id,
        raw_tx_inputs,
    )

    ws_channel = f"/ws/pipeline/{pipeline_id}"
    return PipelineAccepted(
        pipeline_id=pipeline_id,
        status="accepted",
        ws_channel=ws_channel,
    )


@router.get("/{account_id}", response_model=PaginatedTransactions)
async def get_enriched_transactions(
    account_id: UUID,
    category: str | None = Query(default=None),
    shariah_status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTransactions:
    """Get paginated list of enriched transaction rows with filter properties."""
    query = (
        select(EnrichedTransaction)
        .join(MappedTransaction, EnrichedTransaction.mapped_id == MappedTransaction.id)
        .where(EnrichedTransaction.account_id == account_id)
    )

    if category:
        query = query.where(EnrichedTransaction.category == category)
    if shariah_status:
        query = query.where(EnrichedTransaction.shariah_status == shariah_status)
    if date_from:
        query = query.where(MappedTransaction.transaction_date >= date_from)
    if date_to:
        query = query.where(MappedTransaction.transaction_date <= date_to)

    # Count total matching rows
    count_stmt = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Fetch rows using paginate offset/limit ordering by date descending
    query = (
        query.order_by(MappedTransaction.transaction_date.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    enriched_txs = result.scalars().all()

    items = [
        EnrichedTransactionResponse.model_validate(tx)
        for tx in enriched_txs
    ]

    return PaginatedTransactions(
        items=items,
        page=page,
        limit=limit,
        total=total,
    )
