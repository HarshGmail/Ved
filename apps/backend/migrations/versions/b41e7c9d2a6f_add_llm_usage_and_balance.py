from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "b41e7c9d2a6f"
down_revision: str | Sequence[str] | None = "9c2e4a6b1d7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_creation_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_created_at"), "llm_usage", ["created_at"], unique=False)
    op.create_table(
        "llm_balance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("balance_usd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_llm_balance_single_row"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("llm_balance")
    op.drop_index(op.f("ix_llm_usage_created_at"), table_name="llm_usage")
    op.drop_table("llm_usage")
