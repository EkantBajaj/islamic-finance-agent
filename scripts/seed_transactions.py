from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.database import RawTransaction

# Consistent default account ID for seeding and demo runs
DEFAULT_ACCOUNT_ID = uuid.UUID("d3b07384-d113-4956-a5cc-9c0211a766bb")


def generate_transactions(account_id: uuid.UUID, count: int = 100) -> list[RawTransaction]:
    """Generate 100 realistic transaction records representing the medallion Raw state."""
    txs: list[RawTransaction] = []
    today = date.today()

    # Base date 120 days ago
    current_date = today - timedelta(days=120)
    ext_id_counter = 1000

    # 1. Generate monthly recurring subscriptions & utilities over the 4-month span
    for month_offset in range(4):
        month_start = current_date + timedelta(days=30 * month_offset)
        if month_start > today:
            break

        # A. Salary (Income)
        sal_date = date(month_start.year, month_start.month, 28)
        if sal_date <= today:
            ext_id = f"TXN_SALARY_{month_offset}"
            txs.append(
                RawTransaction(
                    external_id=ext_id,
                    account_id=account_id,
                    source="manual",
                    processing_status="pending",
                    raw_payload={
                        "external_id": ext_id,
                        "amount": 25000.00,
                        "currency": "AED",
                        "direction": "credit",
                        "transaction_date": sal_date.isoformat(),
                        "merchant_name": "ACME Corporation UAE",
                        "merchant_mcc": "8999",
                        "counterparty": "ACME Corp",
                        "description": "Monthly Payroll Transfer Salary Payment",
                    },
                )
            )

        # B. Netflix Subscription (Recurring, Essential)
        net_date = date(month_start.year, month_start.month, 10)
        if net_date <= today:
            ext_id = f"TXN_NETFLIX_{month_offset}"
            txs.append(
                RawTransaction(
                    external_id=ext_id,
                    account_id=account_id,
                    source="manual",
                    processing_status="pending",
                    raw_payload={
                        "external_id": ext_id,
                        "amount": 59.00,
                        "currency": "AED",
                        "direction": "debit",
                        "transaction_date": net_date.isoformat(),
                        "merchant_name": "Netflix Inc",
                        "merchant_mcc": "4899",
                        "counterparty": "Netflix",
                        "description": "NETFLIX.COM STREAMING SUBSCRIPTION DIRECT DEBIT",
                    },
                )
            )

        # C. Spotify Subscription (Recurring, Discretionary)
        spot_date = date(month_start.year, month_start.month, 15)
        if spot_date <= today:
            ext_id = f"TXN_SPOTIFY_{month_offset}"
            txs.append(
                RawTransaction(
                    external_id=ext_id,
                    account_id=account_id,
                    source="manual",
                    processing_status="pending",
                    raw_payload={
                        "external_id": ext_id,
                        "amount": 21.99,
                        "currency": "AED",
                        "direction": "debit",
                        "transaction_date": spot_date.isoformat(),
                        "merchant_name": "Spotify AB Premium",
                        "merchant_mcc": "4899",
                        "counterparty": "Spotify AB",
                        "description": "Spotify Premium Digital Subscription Payment",
                    },
                )
            )

        # D. DEWA Bill (Utility, Essential recurring)
        dewa_date = date(month_start.year, month_start.month, 5)
        if dewa_date <= today:
            ext_id = f"TXN_DEWA_{month_offset}"
            amt = round(random.uniform(350.0, 480.0), 2)
            txs.append(
                RawTransaction(
                    external_id=ext_id,
                    account_id=account_id,
                    source="manual",
                    processing_status="pending",
                    raw_payload={
                        "external_id": ext_id,
                        "amount": amt,
                        "currency": "AED",
                        "direction": "debit",
                        "transaction_date": dewa_date.isoformat(),
                        "merchant_name": "DEWA Dubai Water and Electricity",
                        "merchant_mcc": "4900",
                        "counterparty": "DEWA Authority",
                        "description": "DEWA UTILITIES ON-LINE PAYMENT",
                    },
                )
            )

    # 2. Daily/Weekly spend categories
    merchants = [
        {
            "name": "Lulu Hypermarket LLC Al Barsha",
            "mcc": "5411",
            "counterparty": "Lulu Hypermarket",
            "direction": "debit",
            "min_amt": 100.0,
            "max_amt": 600.0,
            "desc": "Grocery items and essentials",
        },
        {
            "name": "Carrefour Dubai Marina Mall",
            "mcc": "5411",
            "counterparty": "Carrefour",
            "direction": "debit",
            "min_amt": 50.0,
            "max_amt": 350.0,
            "desc": "Fresh fruits, vegetables and dairy",
        },
        {
            "name": "Talabat LLC",
            "mcc": "5812",
            "counterparty": "Talabat Delivery",
            "direction": "debit",
            "min_amt": 30.0,
            "max_amt": 150.0,
            "desc": "Food delivery order from restaurant",
        },
        {
            "name": "Deliveroo Dubai",
            "mcc": "5812",
            "counterparty": "Deliveroo Delivery",
            "direction": "debit",
            "min_amt": 45.0,
            "max_amt": 220.0,
            "desc": "Dinner food courier delivery",
        },
        {
            "name": "Careem Ride Taxi",
            "mcc": "4121",
            "counterparty": "Careem Ride",
            "direction": "debit",
            "min_amt": 15.0,
            "max_amt": 85.0,
            "desc": "Cab ride within Dubai Marina",
        },
        {
            "name": "Uber Gulf Taxi",
            "mcc": "4121",
            "counterparty": "Uber Taxi",
            "direction": "debit",
            "min_amt": 20.0,
            "max_amt": 100.0,
            "desc": "Airport pickup ride-hailing taxi",
        },
        {
            "name": "Amazon.ae Dubai Retail",
            "mcc": "5942",
            "counterparty": "Amazon UAE",
            "direction": "debit",
            "min_amt": 40.0,
            "max_amt": 850.0,
            "desc": "Home electronic items and books purchase",
        },
        {
            "name": "Noon Ecommerce Retailer",
            "mcc": "5942",
            "counterparty": "Noon.com",
            "direction": "debit",
            "min_amt": 50.0,
            "max_amt": 650.0,
            "desc": "Retail goods ordering online",
        },
        {
            "name": "ADNOC Service Station",
            "mcc": "5541",
            "counterparty": "ADNOC Gas Station",
            "direction": "debit",
            "min_amt": 80.0,
            "max_amt": 180.0,
            "desc": "Gasoline fill-up petrol",
        },
        # Non-compliant items:
        {
            "name": "McGettigans JLT Pub Bar",
            "mcc": "5813",
            "counterparty": "McGettigans Bar JLT",
            "direction": "debit",
            "min_amt": 150.0,
            "max_amt": 450.0,
            "desc": "Bar drinks and evening beverages",
        },
        {
            "name": "Crown Liquor Cellar Retailer",
            "mcc": "5921",
            "counterparty": "Crown Liquor Store",
            "direction": "debit",
            "min_amt": 100.0,
            "max_amt": 380.0,
            "desc": "Alcohol and spirits retail buy",
        },
        {
            "name": "Standard Chartered Conventional Overdraft Fee",
            "mcc": "6011",
            "counterparty": "Standard Chartered Bank",
            "direction": "debit",
            "min_amt": 80.0,
            "max_amt": 150.0,
            "desc": "Conventional overdraft account interest charge",
        },
        {
            "name": "Conventional savings interest payment",
            "mcc": "6011",
            "counterparty": "Savings account interest",
            "direction": "credit",
            "min_amt": 15.0,
            "max_amt": 65.0,
            "desc": "Interest credit payout conventional account",
        },
        {
            "name": "PokerStars Online Gamble",
            "mcc": "7995",
            "counterparty": "PokerStars Online Casino",
            "direction": "debit",
            "min_amt": 200.0,
            "max_amt": 1200.0,
            "desc": "Online betting and chip deposits",
        },
    ]

    # Fill up until we reach exactly `count` items
    while len(txs) < count:
        day_offset = random.randint(1, 115)
        tx_date = today - timedelta(days=day_offset)
        merch = random.choice(merchants)

        amt = round(random.uniform(merch["min_amt"], merch["max_amt"]), 2)
        ext_id = f"TXN_RAW_{ext_id_counter}"
        ext_id_counter += 1

        txs.append(
            RawTransaction(
                external_id=ext_id,
                account_id=account_id,
                source="manual",
                processing_status="pending",
                raw_payload={
                    "external_id": ext_id,
                    "amount": float(amt),
                    "currency": "AED",
                    "direction": merch["direction"],
                    "transaction_date": tx_date.isoformat(),
                    "merchant_name": merch["name"],
                    "merchant_mcc": merch["mcc"],
                    "counterparty": merch["counterparty"],
                    "description": merch["desc"],
                },
            )
        )

    return txs


async def main() -> None:
    print("Initializing Seeding script...")
    settings = get_settings()
    print(f"Database URL: {settings.database_url}")

    engine = create_async_engine(str(settings.database_url))
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    print(f"Generating 100 transaction records for account {DEFAULT_ACCOUNT_ID}...")
    txs = generate_transactions(DEFAULT_ACCOUNT_ID, 100)

    async with SessionLocal() as session:
        try:
            # Clean up old records for this account to guarantee clean slate
            print("Purging existing raw transactions for the demo account...")
            await session.execute(
                delete(RawTransaction).where(RawTransaction.account_id == DEFAULT_ACCOUNT_ID)
            )

            print("Saving new seeded raw transactions to database...")
            session.add_all(txs)
            await session.commit()
            print("Database commits completed successfully!")
        except Exception as e:
            await session.rollback()
            print(f"Database seeding failed: {e}")
            raise
        finally:
            await session.close()

    await engine.dispose()
    print("Seeding script execution completed.")


if __name__ == "__main__":
    asyncio.run(main())
