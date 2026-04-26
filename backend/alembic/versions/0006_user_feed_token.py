"""users.feed_token

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("feed_token", sa.Text(), nullable=True))
    op.create_index(
        "ix_users_feed_token",
        "users",
        ["feed_token"],
        unique=True,
        postgresql_where=sa.text("feed_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_feed_token", table_name="users")
    op.drop_column("users", "feed_token")
