"""link reminders to check-in conversations

Revision ID: e8e5cbe39742
Revises: ad07d59e1c3f
Create Date: 2026-10-11 02:04:05.759190

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = 'e8e5cbe39742'
down_revision: str | Sequence[str] | None = 'ad07d59e1c3f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('reminders', sa.Column('conversation_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_reminders_conversation_id_conversations', 'reminders', 'conversations', ['conversation_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_reminders_conversation_id_conversations', 'reminders', type_='foreignkey')
    op.drop_column('reminders', 'conversation_id')
