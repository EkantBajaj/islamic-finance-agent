"""Create the personal financial management insight layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_insights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB()),
        sa.Column(
            "severity", sa.String(10), nullable=False, server_default=sa.text("'info'")
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_insights_period"),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'action')", name="ck_insights_severity"
        ),
    )
    op.create_index("idx_insights_account", "financial_insights", ["account_id"])
    op.create_index(
        "idx_insights_period", "financial_insights", ["account_id", "period_start", "period_end"]
    )


def downgrade() -> None:
    op.drop_index("idx_insights_period", table_name="financial_insights")
    op.drop_index("idx_insights_account", table_name="financial_insights")
    op.drop_table("financial_insights")

