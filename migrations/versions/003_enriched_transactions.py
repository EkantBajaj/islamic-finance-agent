"""Create the categorized and screened core layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enriched_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "mapped_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mapped_transactions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("subcategory", sa.String(50)),
        sa.Column("category_confidence", sa.Numeric(3, 2)),
        sa.Column("categorization_method", sa.String(20)),
        sa.Column("shariah_status", sa.String(20), nullable=False),
        sa.Column(
            "shariah_flags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("shariah_confidence", sa.Numeric(3, 2)),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recurrence_group_id", postgresql.UUID(as_uuid=True)),
        sa.Column("recurrence_frequency", sa.String(20)),
        sa.Column("cashflow_type", sa.String(20)),
        sa.Column(
            "enriched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "category_confidence BETWEEN 0 AND 1", name="ck_enriched_category_confidence"
        ),
        sa.CheckConstraint(
            "shariah_confidence BETWEEN 0 AND 1", name="ck_enriched_shariah_confidence"
        ),
        sa.CheckConstraint(
            "shariah_status IN ('compliant', 'non_compliant', 'review')",
            name="ck_enriched_shariah_status",
        ),
        sa.CheckConstraint(
            "categorization_method IS NULL OR "
            "categorization_method IN ('mcc', 'rules', 'llm', 'hybrid')",
            name="ck_enriched_categorization_method",
        ),
        sa.CheckConstraint(
            "cashflow_type IS NULL OR "
            "cashflow_type IN ('essential', 'discretionary', 'income', 'transfer')",
            name="ck_enriched_cashflow_type",
        ),
    )
    op.create_index("idx_enriched_account", "enriched_transactions", ["account_id"])
    op.create_index("idx_enriched_category", "enriched_transactions", ["category"])
    op.create_index("idx_enriched_shariah", "enriched_transactions", ["shariah_status"])


def downgrade() -> None:
    op.drop_index("idx_enriched_shariah", table_name="enriched_transactions")
    op.drop_index("idx_enriched_category", table_name="enriched_transactions")
    op.drop_index("idx_enriched_account", table_name="enriched_transactions")
    op.drop_table("enriched_transactions")

