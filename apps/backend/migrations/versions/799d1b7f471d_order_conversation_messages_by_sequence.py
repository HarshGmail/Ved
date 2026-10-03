"""order conversation messages by sequence

Revision ID: 799d1b7f471d
Revises: 89ef39787ce5
Create Date: 2026-10-04 02:37:30.484476

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = '799d1b7f471d'
down_revision: str | Sequence[str] | None = '89ef39787ce5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEQUENCE_NAME = "conversation_messages_sequence_seq"


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence(SEQUENCE_NAME)))
    op.add_column(
        "conversation_messages",
        sa.Column("sequence", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE conversation_messages AS target
        SET sequence = ordered.position
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                ORDER BY created_at, CASE role WHEN 'user' THEN 0 ELSE 1 END, id
            ) AS position
            FROM conversation_messages
        ) AS ordered
        WHERE target.id = ordered.id
        """
    )
    op.execute(
        f"SELECT setval('{SEQUENCE_NAME}', "
        "GREATEST((SELECT COALESCE(MAX(sequence), 0) FROM conversation_messages), 1))"
    )
    op.alter_column(
        "conversation_messages",
        "sequence",
        nullable=False,
        server_default=sa.text(f"nextval('{SEQUENCE_NAME}')"),
    )
    op.drop_index(
        op.f("ix_conversation_messages_thread"), table_name="conversation_messages"
    )
    op.create_index(
        "ix_conversation_messages_thread",
        "conversation_messages",
        ["conversation_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_messages_thread", table_name="conversation_messages"
    )
    op.create_index(
        op.f("ix_conversation_messages_thread"),
        "conversation_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.drop_column("conversation_messages", "sequence")
    op.execute(sa.schema.DropSequence(sa.Sequence(SEQUENCE_NAME)))
