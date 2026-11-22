from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "d7a3f0b8c215"
down_revision: str | Sequence[str] | None = "b41e7c9d2a6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "family_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(text) BETWEEN 1 AND 1000", name="ck_family_notes_text_length"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], name="fk_family_notes_author_user_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_family_notes_author_user_id"), "family_notes", ["author_user_id"], unique=False)
    op.create_index(op.f("ix_family_notes_created_at"), "family_notes", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_family_notes_created_at"), table_name="family_notes")
    op.drop_index(op.f("ix_family_notes_author_user_id"), table_name="family_notes")
    op.drop_table("family_notes")
