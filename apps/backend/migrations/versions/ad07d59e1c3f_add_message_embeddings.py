"""add message embeddings

Revision ID: ad07d59e1c3f
Revises: 524b5b58ae88
Create Date: 2026-10-11 00:47:38.063955

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op


revision: str = 'ad07d59e1c3f'
down_revision: str | Sequence[str] | None = '524b5b58ae88'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "conversation_messages",
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=True),
    )
    op.create_index(
        "ix_conversation_messages_embedding",
        "conversation_messages",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_messages_embedding",
        table_name="conversation_messages",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_column("conversation_messages", "embedding")
