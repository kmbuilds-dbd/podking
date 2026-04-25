"""jobs.archived_at

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_jobs_user_archived_created",
        "jobs",
        ["user_id", "archived_at", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_user_archived_created", table_name="jobs")
    op.drop_column("jobs", "archived_at")
