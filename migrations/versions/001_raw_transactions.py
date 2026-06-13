"""Create the raw transaction ingestion layer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "raw_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "processing_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_raw_transactions_processing_status",
        ),
        sa.UniqueConstraint("source", "external_id", name="uq_raw_transactions_source_external"),
    )
    op.create_index("idx_raw_txn_account", "raw_transactions", ["account_id"])
    op.create_index("idx_raw_txn_status", "raw_transactions", ["processing_status"])


def downgrade() -> None:
    op.drop_index("idx_raw_txn_status", table_name="raw_transactions")
    op.drop_index("idx_raw_txn_account", table_name="raw_transactions")
    op.drop_table("raw_transactions")

