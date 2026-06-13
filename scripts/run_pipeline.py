from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.orchestrator import build_pipeline
from app.config import get_settings
from app.models.database import (
    EnrichedTransaction,
    FinancialInsight,
    FinancialProfile,
    MappedTransaction,
    RawTransaction,
)

DEFAULT_ACCOUNT_ID = uuid.UUID("d3b07384-d113-4956-a5cc-9c0211a766bb")


async def run_cli_pipeline() -> None:
    """Run the transaction intelligence LangGraph pipeline from CLI on seeded raw transactions."""
    settings = get_settings()
    print("=" * 60)
    print("🚀 BARAKAH AI: TRANSACTION INTELLIGENCE PIPELINE RUNNER")
    print("=" * 60)
    print(f"Database: {settings.database_url}")
    print(f"Account ID: {DEFAULT_ACCOUNT_ID}")

    engine = create_async_engine(str(settings.database_url))
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # 1. Fetch pending transactions
    async with SessionLocal() as session:
        result = await session.execute(
            select(RawTransaction).where(
                RawTransaction.account_id == DEFAULT_ACCOUNT_ID,
                RawTransaction.processing_status == "pending",
            )
        )
        raw_txs = result.scalars().all()

    if not raw_txs:
        print("⚠️ No pending transactions found for this account. Please seed transactions first!")
        await engine.dispose()
        return

    print(f"📋 Found {len(raw_txs)} pending transactions.")

    # 2. Update status to processing
    async with SessionLocal() as session:
        await session.execute(
            update(RawTransaction)
            .where(
                RawTransaction.account_id == DEFAULT_ACCOUNT_ID,
                RawTransaction.processing_status == "pending",
            )
            .values(processing_status="processing")
        )
        await session.commit()

    raw_inputs = [tx.raw_payload for tx in raw_txs]

    # 3. Construct pipeline state
    state = {
        "raw_transactions": raw_inputs,
        "mapped_transactions": [],
        "categorized": [],
        "shariah_screened": [],
        "recurrence_groups": [],
        "insights": [],
        "profile_updates": {},
        "errors": [],
        "metadata": {},
    }

    # 4. Invoke the LangGraph pipeline
    print("🔄 Invoking LangGraph Pipeline...")
    workflow = build_pipeline()
    start_time = datetime.now(UTC)
    
    # We run the compiled state graph
    result_state = await workflow.ainvoke(state)
    
    duration = (datetime.now(UTC) - start_time).total_seconds()
    print(f"✅ LangGraph execution completed in {duration:.2f}s.")

    # 5. Extract results
    mapped_txs = result_state.get("mapped_transactions", [])
    insights = result_state.get("insights", [])
    profile_updates = result_state.get("profile_updates", {})
    recurrence_groups = result_state.get("recurrence_groups", [])

    print(f"🔹 Normalized & Mapped: {len(mapped_txs)} rows")
    print(f"🔹 Detected Recurrence Groups: {len(recurrence_groups)} groups")
    print(f"🔹 Generated Insights: {len(insights)}")

    # 6. Save results to the database (Medallion schema)
    async with SessionLocal() as session:
        try:
            # Clear previous runs data for this account to guarantee clean slate
            await session.execute(
                delete(EnrichedTransaction).where(
                    EnrichedTransaction.account_id == DEFAULT_ACCOUNT_ID
                )
            )
            await session.execute(
                delete(MappedTransaction).where(
                    MappedTransaction.account_id == DEFAULT_ACCOUNT_ID
                )
            )
            await session.execute(
                delete(FinancialInsight).where(
                    FinancialInsight.account_id == DEFAULT_ACCOUNT_ID
                )
            )
            await session.commit()

            # Create ID map of new RawTransactions
            raw_db = await session.execute(
                select(RawTransaction).where(RawTransaction.account_id == DEFAULT_ACCOUNT_ID)
            )
            raw_map = {tx.external_id: tx.id for tx in raw_db.scalars()}

            mapped_objs = []
            enriched_objs = []

            for tx in mapped_txs:
                ext_id = tx.get("external_id")
                raw_id = raw_map.get(ext_id)
                if not raw_id:
                    continue

                m_obj = MappedTransaction(
                    id=tx.get("id"),
                    raw_id=raw_id,
                    account_id=DEFAULT_ACCOUNT_ID,
                    amount=tx.get("amount"),
                    currency=tx.get("currency", "AED"),
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
                    account_id=DEFAULT_ACCOUNT_ID,
                    category=tx.get("category", "other"),
                    subcategory=tx.get("subcategory"),
                    category_confidence=tx.get("category_confidence"),
                    categorization_method=tx.get("categorization_method"),
                    shariah_status=tx.get("shariah_status", "review"),
                    shariah_flags=tx.get("shariah_flags", []),
                    shariah_confidence=tx.get("shariah_confidence"),
                    is_recurring=tx.get("is_recurring", False),
                    recurrence_group_id=tx.get("recurrence_group_id"),
                    recurrence_frequency=tx.get("recurrence_frequency"),
                    cashflow_type=tx.get("cashflow_type"),
                )
                enriched_objs.append(e_obj)

            print("💾 Saving Mapped & Enriched transactions to DB...")
            session.add_all(mapped_objs)
            await session.flush()
            session.add_all(enriched_objs)

            # Insights saving
            insight_objs = []
            dates = [t.get("transaction_date") for t in mapped_txs if t.get("transaction_date")]
            min_date = min(dates) if dates else date.today()
            max_date = max(dates) if dates else date.today()

            for ins in insights:
                insight_objs.append(
                    FinancialInsight(
                        account_id=DEFAULT_ACCOUNT_ID,
                        insight_type=ins.get("severity", "info"),
                        period_start=min_date,
                        period_end=max_date,
                        title=ins.get("title", "Insight"),
                        body=ins.get("body", ""),
                        data=ins.get("data", {}),
                        severity=ins.get("severity", "info"),
                    )
                )
            
            if insight_objs:
                print("💾 Saving Financial Insights to DB...")
                session.add_all(insight_objs)

            # Profile updates
            if profile_updates:
                print("💾 Updating Financial Profile statistics...")
                p_res = await session.execute(
                    select(FinancialProfile).where(
                        FinancialProfile.account_id == DEFAULT_ACCOUNT_ID
                    )
                )
                profile_obj = p_res.scalar_one_or_none()

                if not profile_obj:
                    profile_obj = FinancialProfile(account_id=DEFAULT_ACCOUNT_ID)
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
            await session.execute(
                update(RawTransaction)
                .where(
                    RawTransaction.account_id == DEFAULT_ACCOUNT_ID,
                    RawTransaction.processing_status == "processing",
                )
                .values(processing_status="completed")
            )
            await session.commit()
            print("🎉 Database transactions persisted successfully!")

        except Exception as e:
            await session.rollback()
            print(f"❌ Database save failed, rolling back changes: {e}")
            
            # Set RawTransaction rows to failed
            await session.execute(
                update(RawTransaction)
                .where(
                    RawTransaction.account_id == DEFAULT_ACCOUNT_ID,
                    RawTransaction.processing_status == "processing",
                )
                .values(processing_status="failed")
            )
            await session.commit()
            raise

    # 7. Print Console Summary Details
    print("-" * 60)
    print("📈 SUMMARY STATISTICS:")
    print("-" * 60)
    compliant_count = sum(1 for t in mapped_txs if t.get("shariah_status") == "compliant")
    non_compliant_count = sum(1 for t in mapped_txs if t.get("shariah_status") == "non_compliant")
    review_count = sum(1 for t in mapped_txs if t.get("shariah_status") == "review")

    print(f"🟢 Compliant Transactions: {compliant_count}")
    print(f"🔴 Non-Compliant Transactions: {non_compliant_count}")
    print(f"🟡 Review Flagged Transactions: {review_count}")

    if profile_updates:
        print(f"📊 Compliance Score: {profile_updates.get('shariah_compliance_score') * 100:.1f}%")
        print(f"💰 Average Monthly Income: {profile_updates.get('avg_monthly_income'):,.2f} AED")
        print(f"💸 Average Monthly Outflow: {profile_updates.get('avg_monthly_spend'):,.2f} AED")
        zakat_nisab = profile_updates.get("zakat_nisab_threshold") or 0.0
        print(
            f"⚖️ Calculated Zakat Due: {profile_updates.get('zakat_due'):,.2f} AED "
            f"(Nisab: {zakat_nisab:,.2f} AED)"
        )

    if insights:
        print("\n💡 GENERATED INSIGHTS:")
        for idx, ins in enumerate(insights, 1):
            print(f"  {idx}. [{ins.get('severity', 'info').upper()}] {ins.get('title')}")
            print(f"     {ins.get('body')}")
            
    print("=" * 60)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_cli_pipeline())
