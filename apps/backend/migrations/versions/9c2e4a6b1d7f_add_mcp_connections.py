"""add per-user MCP connections

Revision ID: 9c2e4a6b1d7f
Revises: 3f7a1c2d9b64
Create Date: 2026-11-13 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "9c2e4a6b1d7f"
down_revision: str | Sequence[str] | None = "3f7a1c2d9b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mcp_connections_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_mcp_connections_user_name"),
    )
    op.create_index(op.f("ix_mcp_connections_user_id"), "mcp_connections", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_connections_user_id"), table_name="mcp_connections")
    op.drop_table("mcp_connections")
