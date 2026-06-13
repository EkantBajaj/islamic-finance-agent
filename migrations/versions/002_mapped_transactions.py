"""Create the normalized transaction map layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mapped_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "raw_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_transactions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("counterparty", sa.String(255)),
        sa.Column("merchant_name", sa.String(255)),
        sa.Column("merchant_mcc", sa.String(10)),
        sa.Column("description", sa.Text()),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("booked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("direction IN ('credit', 'debit')", name="ck_mapped_direction"),
    )
    op.create_index("idx_mapped_account", "mapped_transactions", ["account_id"])
    op.create_index("idx_mapped_date", "mapped_transactions", ["transaction_date"])


def downgrade() -> None:
    op.drop_index("idx_mapped_date", table_name="mapped_transactions")
    op.drop_index("idx_mapped_account", table_name="mapped_transactions")
    op.drop_table("mapped_transactions")

