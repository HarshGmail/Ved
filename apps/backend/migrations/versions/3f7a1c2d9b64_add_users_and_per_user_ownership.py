"""add users and per-user ownership

Revision ID: 3f7a1c2d9b64
Revises: 0c5bb64b7977
Create Date: 2026-11-13 16:50:00.000000

"""

import os
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "3f7a1c2d9b64"
down_revision: str | Sequence[str] | None = "0c5bb64b7977"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_EMAIL_VARIABLE = "VED_OWNER_EMAIL"
DEFAULT_OWNER_EMAIL = "owner@ved.local"
OWNED_TABLES = (
    "people",
    "reminders",
    "push_subscriptions",
    "conversations",
    "documents",
)


def owner_email() -> str:
    configured = os.environ.get(OWNER_EMAIL_VARIABLE, "").strip()
    return (configured or DEFAULT_OWNER_EMAIL).lower()


def foreign_key_name(table: str) -> str:
    return f"fk_{table}_user_id_users"


def index_name(table: str) -> str:
    return f"ix_{table}_user_id"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    connection = op.get_bind()
    owner_id = uuid.uuid4()
    connection.execute(
        sa.text("INSERT INTO users (id, email) VALUES (:id, :email)"),
        {"id": owner_id, "email": owner_email()},
    )

    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", sa.UUID(), nullable=True))
        connection.execute(
            sa.text(f"UPDATE {table} SET user_id = :owner_id"), {"owner_id": owner_id}
        )
        op.alter_column(table, "user_id", nullable=False)
        op.create_foreign_key(
            foreign_key_name(table),
            table,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(op.f(index_name(table)), table, ["user_id"], unique=False)

    op.drop_index("uq_people_name_lower", table_name="people")
    op.create_index(
        "uq_people_user_name_lower",
        "people",
        ["user_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.drop_constraint("documents_sha256_key", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_user_sha256", "documents", ["user_id", "sha256"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_user_sha256", "documents", type_="unique")
    op.create_unique_constraint("documents_sha256_key", "documents", ["sha256"])
    op.drop_index("uq_people_user_name_lower", table_name="people")
    op.create_index(
        "uq_people_name_lower",
        "people",
        [sa.literal_column("lower(name)")],
        unique=True,
    )

    for table in reversed(OWNED_TABLES):
        op.drop_index(op.f(index_name(table)), table_name=table)
        op.drop_constraint(foreign_key_name(table), table, type_="foreignkey")
        op.drop_column(table, "user_id")

    op.drop_table("users")
