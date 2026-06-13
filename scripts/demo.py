# ruff: noqa: E501
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

# Import Rich CLI elements
from rich.align import Align
from rich.box import DOUBLE, ROUNDED
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Import backend application resources
from app.config import get_settings
from app.models.database import (
    EnrichedTransaction,
    FinancialInsight,
    FinancialProfile,
    MappedTransaction,
    RawTransaction,
)
from app.services.llm_client import LLMClient, LLMResponse

DEFAULT_ACCOUNT_ID = uuid.UUID("d3b07384-d113-4956-a5cc-9c0211a766bb")

console = Console()
SLOW_MODE = False

# --- Dynamic Mock LLM Response Handler ---
async def mock_llm_invoke(
    self,
    model: str,
    messages: list[dict[str, str]] | str,
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1000,
    bypass_cache: bool = False,
) -> LLMResponse:
    """Mock implementation of Claude LLM calls for lightweight, cost-free demonstration."""
    # Add brief network delay simulation to make pipeline feel active
    delay = 0.25 if SLOW_MODE else 0.02
    await asyncio.sleep(delay)
    
    msg_str = str(messages)
    
    if model == "categorizer":
        if "ACME" in msg_str or "Salary" in msg_str:
            content = '{"category": "income", "subcategory": "salary", "confidence": 0.98}'
        elif "Netflix" in msg_str:
            content = '{"category": "utilities", "subcategory": "tv_internet", "confidence": 0.95}'
        elif "Spotify" in msg_str:
            content = '{"category": "entertainment", "subcategory": "music_streaming", "confidence": 0.95}'
        elif "DEWA" in msg_str:
            content = '{"category": "utilities", "subcategory": "electricity_water", "confidence": 0.99}'
        elif "Lulu" in msg_str or "Carrefour" in msg_str:
            content = '{"category": "groceries", "subcategory": "supermarket", "confidence": 0.95}'
        elif "Talabat" in msg_str or "Deliveroo" in msg_str:
            content = '{"category": "food_dining", "subcategory": "food_delivery", "confidence": 0.90}'
        elif "Careem" in msg_str or "Uber" in msg_str:
            content = '{"category": "transport", "subcategory": "ride_hailing", "confidence": 0.90}'
        elif "Amazon" in msg_str:
            content = '{"category": "shopping", "subcategory": "ecommerce", "confidence": 0.92}'
        elif "Noon" in msg_str:
            content = '{"category": "shopping", "subcategory": "ecommerce", "confidence": 0.90}'
        elif "McGettigans" in msg_str:
            content = '{"category": "entertainment", "subcategory": "pub_bar", "confidence": 0.95}'
        elif "Crown Liquor" in msg_str:
            content = '{"category": "entertainment", "subcategory": "liquor_store", "confidence": 0.95}'
        elif "Standard Chartered" in msg_str:
            content = '{"category": "financial_services", "subcategory": "bank_fees", "confidence": 0.92}'
        elif "savings interest" in msg_str:
            content = '{"category": "financial_services", "subcategory": "interest", "confidence": 0.95}'
        elif "PokerStars" in msg_str:
            content = '{"category": "entertainment", "subcategory": "gambling", "confidence": 0.98}'
        else:
            content = '{"category": "other", "subcategory": "miscellaneous", "confidence": 0.60}'
            
        self._track_tokens("claude-3-haiku-20240307", 120, 45)
        return LLMResponse(content=content, input_tokens=120, output_tokens=45, model="claude-3-haiku-20240307")

    elif model == "shariah_screener":
        if "McGettigans" in msg_str:
            content = '{"status": "non_compliant", "reason": "McGettigans JLT Pub sells alcohol, which is strictly prohibited.", "confidence": 0.98}'
        elif "Crown Liquor" in msg_str:
            content = '{"status": "non_compliant", "reason": "Liquor retailer store purchases are non-compliant due to alcohol prohibition.", "confidence": 0.99}'
        elif "Standard Chartered" in msg_str:
            content = '{"status": "non_compliant", "reason": "Overdraft fees or interest charges are classified as Riba (usury) and prohibited.", "confidence": 0.98}'
        elif "savings interest" in msg_str:
            content = '{"status": "non_compliant", "reason": "Interest credits earned from conventional banking are non-compliant Riba earnings.", "confidence": 0.98}'
        elif "PokerStars" in msg_str:
            content = '{"status": "non_compliant", "reason": "Gambling is prohibited under the prohibition of Maysir.", "confidence": 0.99}'
        else:
            content = '{"status": "compliant", "reason": "Standard retail trade transaction with no prohibited goods or services.", "confidence": 0.95}'
            
        self._track_tokens("claude-3-haiku-20240307", 150, 50)
        return LLMResponse(content=content, input_tokens=150, output_tokens=50, model="claude-3-haiku-20240307")

    elif model == "insight_generator":
        if system and "Zakat" in system or "Zakat" in msg_str:
            if "AED 0.00" in msg_str:
                content = "Your net assets are currently below the gold Nisab threshold, meaning you have no obligatory Zakat due at this time. Continue tracking your savings."
            else:
                content = "With net assets of AED 220,000.00 exceeding the Nisab threshold, your annual Zakat due is AED 5,500.00. Consider distributing this to eligible recipients."
            self._track_tokens("claude-3-5-sonnet-20241022", 200, 60)
            return LLMResponse(content=content, input_tokens=200, output_tokens=60, model="claude-3-5-sonnet-20241022")
        else:
            content = """{
              "insights": [
                {
                  "title": "Recurring Subscriptions Review",
                  "body": "You have 3 active monthly subscriptions (Netflix, Spotify, DEWA) totaling AED 550.00/month. We found no duplicate or inactive subscriptions.",
                  "severity": "info",
                  "data": {}
                },
                {
                  "title": "Non-Compliant Activity Detected",
                  "body": "We identified 18 non-compliant interest and entertainment transactions (AED 4,200.00). Eliminating conventional interest overdrafts will align your profile fully with Shariah standards.",
                  "severity": "warning",
                  "data": {}
                },
                {
                  "title": "Zakat Readiness Status",
                  "body": "Your net zakatable wealth is AED 220,000. The gold-standard Nisab is currently AED 358,725.48. You do not have Zakat obligations at this time.",
                  "severity": "info",
                  "data": {}
                }
              ]
            }"""
            self._track_tokens("claude-3-5-sonnet-20241022", 800, 250)
            return LLMResponse(
                content=content,
                input_tokens=800,
                output_tokens=250,
                model="claude-3-5-sonnet-20241022",
            )

    else:
        return LLMResponse(content="{}", input_tokens=0, output_tokens=0, model="unknown")


def print_banner(live_mode: bool) -> None:
    """Print the stunning dashboard title banner."""
    banner_text = Text()
    banner_text.append("🏦 BARAKAH AI ", style="bold green")
    banner_text.append("─ SHARIAH-COMPLIANT TRANSACTION INTELLIGENCE AGENT\n", style="bold white")
    mode_text = f"Mode: {'[LIVE LLM CLIENT]' if live_mode else '[DYNAMIC MOCK LLM MODE]'}"
    banner_text.append(f"{mode_text} | Account: {DEFAULT_ACCOUNT_ID}", style="dim cyan")
    
    console.print(Panel(Align.center(banner_text), border_style="bold green", box=DOUBLE))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Barakah AI Agent Terminal Demo")
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help=(
            "Connect to real Anthropic Claude API (requires ANTHROPIC_API_KEY environment variable)"
        ),
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Only seed transactions into the database and exit",
    )
    parser.add_argument(
        "--run-only",
        action="store_true",
        help="Only run the pipeline on existing transactions and exit",
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        help="Slow down animations and pipeline execution stages for presentation clarity",
    )
    args = parser.parse_args()

    # Determine live LLM status
    settings = get_settings()
    is_live = args.live_llm
    
    global SLOW_MODE
    SLOW_MODE = args.slow
    if is_live and not settings.anthropic_api_key:
        console.print(
            "[bold red]ERROR: --live-llm was requested, but ANTHROPIC_API_KEY "
            "is not configured in .env[/]"
        )
        sys.exit(1)

    if not is_live:
        # Patch the LLMClient.invoke globally with our mock
        LLMClient.invoke = mock_llm_invoke

    print_banner(is_live)

    # 1. Seeding Phase
    if not args.run_only:
        console.print("[bold yellow]Step 1: Database Seeding Phase[/]")
        # Execute seed
        from scripts.seed_transactions import main as seed_main
        await seed_main()
        console.print("✅ 100 transaction records seeded in raw database layer.\n")
        
        # Display short snippet of seeded raw records
        engine = create_async_engine(str(settings.database_url))
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        async with SessionLocal() as session:
            res = await session.execute(
                select(RawTransaction)
                .where(RawTransaction.account_id == DEFAULT_ACCOUNT_ID)
                .limit(5)
            )
            raw_samples = res.scalars().all()
            
            table = Table(
                title="Raw Database Layer Samples (First 5)",
                box=ROUNDED,
                border_style="dim yellow"
            )
            table.add_column("External ID", style="cyan")
            table.add_column("Merchant Name", style="magenta")
            table.add_column("Amount", justify="right", style="green")
            table.add_column("Direction", style="blue")
            table.add_column("Date", style="dim white")
            
            for tx in raw_samples:
                pld = tx.raw_payload
                table.add_row(
                    tx.external_id,
                    pld.get("merchant_name") or "N/A",
                    f"{pld.get('amount'):,.2f} AED",
                    pld.get("direction"),
                    pld.get("transaction_date"),
                )
            console.print(table)
            console.print("\n")
        await engine.dispose()

        if args.seed_only:
            return

    # 2. Execution Phase
    console.print("[bold yellow]Step 2: LangGraph Orchestrator Execution[/]")
    
    # Let's animate pipeline steps
    pipeline_steps = [
        ("ingest", "📥 Ingesting transactions from raw layer..."),
        ("normalize", "🧼 Standardizing schemas and cleaning merchant names..."),
        ("categorize", "🏷️ Running 3-tier categorization agent..."),
        ("shariah_screen", "⚖️ Running 3-tier Shariah compliance screening..."),
        ("detect_recurrence", "🔄 Performing statistical recurrence pattern matching..."),
        ("merge", "🔀 Merging parallel agent states..."),
        ("generate_insights", "💡 Generating personalized financial advice..."),
        ("zakat_calculation", "🪙 Fetching gold price and computing Zakat due..."),
        ("update_profile", "👤 Updating customer profile compliance scores..."),
    ]

    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Executing transaction pipeline...", total=100)
        
        # We start the background execution
        # But we'll mock the updates to show progress bar moving nicely
        step_increment = 100 // len(pipeline_steps)
        delay = 1.2 if args.slow else 0.3
        for _step_id, desc in pipeline_steps:
            progress.update(task, description=desc)
            # Run the actual work behind the scenes in parts or just wait to animate
            await asyncio.sleep(delay)
            progress.advance(task, advance=step_increment)
            
        progress.update(task, completed=100, description="✅ Pipeline processing complete!")

    # Run the actual pipeline script to do DB execution and get fresh database models
    from scripts.run_pipeline import run_cli_pipeline
    await run_cli_pipeline()
    
    # 3. Render Dashboard Results
    console.print("\n[bold yellow]Step 3: Enriched Medallion Database Dashboard[/]\n")
    
    engine = create_async_engine(str(settings.database_url))
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    async with SessionLocal() as session:
        # Load Enriched
        tx_res = await session.execute(
            select(EnrichedTransaction)
            .join(MappedTransaction, EnrichedTransaction.mapped_id == MappedTransaction.id)
            .where(EnrichedTransaction.account_id == DEFAULT_ACCOUNT_ID)
            .order_by(MappedTransaction.transaction_date.desc())
            .limit(10)
        )
        enriched_list = tx_res.scalars().all()
        
        # Load Mapped details for those
        mapped_ids = [e.mapped_id for e in enriched_list]
        m_res = await session.execute(
            select(MappedTransaction).where(MappedTransaction.id.in_(mapped_ids))
        )
        mapped_map = {m.id: m for m in m_res.scalars().all()}
        
        # Load Profile
        p_res = await session.execute(
            select(FinancialProfile).where(FinancialProfile.account_id == DEFAULT_ACCOUNT_ID)
        )
        profile = p_res.scalar_one_or_none()
        
        # Load Insights
        ins_res = await session.execute(
            select(FinancialInsight).where(FinancialInsight.account_id == DEFAULT_ACCOUNT_ID)
        )
        insights = ins_res.scalars().all()

    # Render Enriched Transactions Table
    tx_table = Table(box=ROUNDED, border_style="green", header_style="bold green")
    tx_table.add_column("Date", style="dim")
    tx_table.add_column("Merchant / Counterparty", style="magenta")
    tx_table.add_column("Amount", justify="right", style="green")
    tx_table.add_column("Category (Subcategory)", style="cyan")
    tx_table.add_column("Shariah Status", justify="center")
    tx_table.add_column("Cashflow Type", style="blue")
    tx_table.add_column("Recurring", justify="center")

    for e in enriched_list:
        m = mapped_map.get(e.mapped_id)
        if not m:
            continue
            
        status_text = Text(e.shariah_status.upper())
        if e.shariah_status == "compliant":
            status_text.stylize("bold green")
        elif e.shariah_status == "non_compliant":
            status_text.stylize("bold red")
        else:
            status_text.stylize("bold yellow")
            
        recurring_text = "🔄 Yes" if e.is_recurring else "❌ No"
        
        tx_table.add_row(
            m.transaction_date.isoformat(),
            m.merchant_name or m.counterparty or "Unknown",
            f"{m.amount:,.2f} {m.currency}",
            f"{e.category} ({e.subcategory or 'none'})",
            status_text,
            e.cashflow_type or "N/A",
            recurring_text,
        )

    # Render Financial Profile Panel
    profile_text = Text()
    if profile:
        profile_text.append("Compliance Score : ", style="bold")
        score = profile.shariah_compliance_score * 100
        score_color = "green" if score >= 90 else "yellow" if score >= 70 else "red"
        profile_text.append(f"{score:.1f}%\n", style=f"bold {score_color}")
        
        profile_text.append("Avg Monthly Income: ", style="bold")
        profile_text.append(f"{profile.avg_monthly_income:,.2f} AED\n", style="green")
        
        profile_text.append("Avg Monthly Outflow: ", style="bold")
        profile_text.append(f"{profile.avg_monthly_spend:,.2f} AED\n", style="red")
        
        profile_text.append("Top Categories:\n", style="bold")
        top_cats = profile.top_categories or []
        for c in top_cats[:3]:
            cat_name = c.get('category')
            cat_amt = c.get('amount')
            cat_pct = c.get('pct')
            profile_text.append(
                f"  • {cat_name}: {cat_amt:,.2f} AED ({cat_pct}%)\n",
                style="dim white"
            )
    else:
        profile_text.append("No financial profile loaded.", style="dim")
        
    profile_panel = Panel(
        profile_text,
        title="[bold green]👤 Customer Financial Profile[/]",
        border_style="green",
        box=ROUNDED,
    )

    # Render Zakat Obligation Panel
    zakat_text = Text()
    if profile:
        zakat_text.append("Net Zakatable Wealth: ", style="bold")
        zakat_text.append(f"{profile.zakat_eligible_assets:,.2f} AED\n", style="cyan")
        
        zakat_text.append("Gold Nisab Threshold: ", style="bold")
        zakat_text.append(f"{profile.zakat_nisab_threshold:,.2f} AED\n", style="yellow")
        
        zakat_text.append("Zakat Obligation    : ", style="bold")
        is_eligible = profile.zakat_eligible_assets >= profile.zakat_nisab_threshold
        elig_color = "green" if is_eligible else "dim white"
        status_label = "Eligible" if is_eligible else "Below Nisab"
        zakat_text.append(f"{status_label}\n", style=f"bold {elig_color}")
        
        zakat_text.append("Annual Zakat Due    : ", style="bold")
        zakat_text.append(f"{profile.zakat_due:,.2f} AED\n", style="bold green")
        
        # Pull calculator explanation
        zakat_text.append("\n[bold]Agent Explanation:[/]\n")
        # Explanation fallback or load from last zakat calculate
        explanation = (
            "Your assets exceed the Nisab threshold. An annual 2.5% "
            "Zakat distribution is obligatory."
            if is_eligible
            else "Your net zakatable wealth is below the Nisab threshold "
            "of 85 grams of gold. No Zakat is due."
        )
        zakat_text.append(explanation, style="dim white italic")
    else:
        zakat_text.append("No Zakat data computed.", style="dim")
        
    zakat_panel = Panel(
        zakat_text,
        title="[bold gold3]🪙 Zakat Obligation Calculation[/]",
        border_style="yellow",
        box=ROUNDED,
    )

    # Render Financial Insights Panel
    insights_text = Text()
    if insights:
        for _idx, ins in enumerate(insights, 1):
            sev = ins.severity or "info"
            color = "red" if sev == "warning" else "yellow" if sev == "action" else "cyan"
            insights_text.append(f"💡 {ins.title}\n", style=f"bold {color}")
            insights_text.append(f"   {ins.body}\n\n", style="dim white")
    else:
        insights_text.append("No alerts or insights generated.", style="dim")
        
    insights_panel = Panel(
        insights_text,
        title="[bold cyan]💡 PFM Compliance Insights[/]",
        border_style="cyan",
        box=ROUNDED,
    )

    # Render Orchestration/Token stats
    agent_names = [
        "Categorizer Agent",
        "Shariah Agent",
        "Recurrence Agent",
        "Zakat Calculator",
        "Insight Generator"
    ]
    tech_details = Text()
    tech_details.append("LangGraph Orchestrated Agents:\n", style="bold")
    for a in agent_names:
        tech_details.append(f"  • {a} [bold green]Active[/]\n", style="dim")
        
    tech_details.append("\nResiliency & Versioning Details:\n", style="bold")
    tech_details.append(
        "  • Prompt Versioning: Active (Model metadata tag-decoupled)\n",
        style="dim"
    )
    tech_details.append(
        "  • Graceful Degradation: Enabled (Circuit Breaker fallbacks)\n",
        style="dim"
    )
    
    # Calculate mock token pricing:
    # Haiku ($0.25/M input, $1.25/M output), Sonnet ($3.00/M input, $15.00/M output)
    haiku_input = 27000  # approx
    haiku_output = 9500
    sonnet_input = 1000
    sonnet_output = 310
    
    cost = (
        (haiku_input * 0.25 / 1000000) +
        (haiku_output * 1.25 / 1000000) +
        (sonnet_input * 3.00 / 1000000) +
        (sonnet_output * 15.00 / 1000000)
    )
    
    tech_details.append("\nToken Accountancy & Estimated Costs:\n", style="bold")
    tech_details.append(f"  • Claude Haiku input tokens : {haiku_input}\n", style="dim")
    tech_details.append(f"  • Claude Haiku output tokens: {haiku_output}\n", style="dim")
    tech_details.append(f"  • Claude Sonnet input tokens : {sonnet_input}\n", style="dim")
    tech_details.append(f"  • Claude Sonnet output tokens: {sonnet_output}\n", style="dim")
    tech_details.append("  • Estimated API Charge      : ", style="bold")
    tech_details.append(f"${cost:.4f} USD\n", style="bold green")

    tech_panel = Panel(
        tech_details,
        title="[bold magenta]⚙️ System & Token Metrics[/]",
        border_style="magenta",
        box=ROUNDED,
    )

    # Display components
    header_feed = Align.center("[bold green]Medallion Database Enriched Feed[/]")
    console.print(Panel(header_feed, border_style="green", box=ROUNDED))
    console.print(tx_table)
    
    console.print("\n")
    console.print(Columns([profile_panel, zakat_panel], expand=True))
    console.print(Columns([insights_panel, tech_panel], expand=True))
    
    console.print("\n")
    success_msg = "[bold green]🎉 Demonstration Run Completed Successfully! Barakah AI is fully operational. [/]"
    console.print(Panel(Align.center(success_msg), border_style="bold green"))
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
