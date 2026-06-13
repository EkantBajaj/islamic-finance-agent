"""Create the aggregated financial profile layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_profile",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("rfm_recency", sa.Integer()),
        sa.Column("rfm_frequency", sa.Integer()),
        sa.Column("rfm_monetary", sa.Numeric(15, 2)),
        sa.Column("rfm_segment", sa.String(30)),
        sa.Column("zakat_eligible_assets", sa.Numeric(15, 2)),
        sa.Column("zakat_nisab_threshold", sa.Numeric(15, 2)),
        sa.Column("zakat_due", sa.Numeric(15, 2)),
        sa.Column("zakat_year_start", sa.Date()),
        sa.Column("avg_monthly_income", sa.Numeric(15, 2)),
        sa.Column("avg_monthly_spend", sa.Numeric(15, 2)),
        sa.Column("top_categories", postgresql.JSONB()),
        sa.Column("shariah_compliance_score", sa.Numeric(3, 2)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "shariah_compliance_score BETWEEN 0 AND 1",
            name="ck_profile_shariah_compliance_score",
        ),
    )


def downgrade() -> None:
    op.drop_table("financial_profile")

