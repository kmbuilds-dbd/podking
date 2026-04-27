"""drop unused subscriptions columns

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-27

Both columns became dead weight when subscriptions stopped auto-queueing
episodes (the user explicitly picks which episodes to summarize from
the subscription detail page now):

- last_seen_external_id was the cursor used to detect newly-published
  episodes between polls. The poller no longer enqueues anything, so
  the column is never read or written.
- active gated which subscriptions the poller would refresh metadata
  for. With auto-queue gone there's nothing meaningful to "pause" —
  metadata refresh is cheap and there's no per-subscription cost.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("subscriptions", "last_seen_external_id")
    op.drop_column("subscriptions", "active")


def downgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column("last_seen_external_id", sa.Text(), nullable=True),
    )
