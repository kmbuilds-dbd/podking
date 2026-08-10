"""link episodes and jobs to the subscription they were queued from

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-10

NOTE: the columns intentionally carry NO database-level foreign-key
constraint. Deploy-time DDL that takes ACCESS EXCLUSIVE locks (FK
constraint add + validation) blocks behind the still-running previous
replica during Railway's rolling deploy and blows the healthcheck
window. The app resolves the link at runtime and already handles a
missing/orphaned subscription gracefully, so integrity enforcement is
left to the application layer.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "episodes",
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "subscription_id")
    op.drop_column("episodes", "subscription_id")
