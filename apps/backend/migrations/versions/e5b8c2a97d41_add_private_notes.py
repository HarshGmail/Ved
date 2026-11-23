from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "e5b8c2a97d41"
down_revision: str | Sequence[str] | None = "d7a3f0b8c215"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "private_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(text) BETWEEN 1 AND 1000", name="ck_private_notes_text_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_private_notes_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_private_notes_user_id"), "private_notes", ["user_id"], unique=False)
    op.create_index(op.f("ix_private_notes_created_at"), "private_notes", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_private_notes_created_at"), table_name="private_notes")
    op.drop_index(op.f("ix_private_notes_user_id"), table_name="private_notes")
    op.drop_table("private_notes")
