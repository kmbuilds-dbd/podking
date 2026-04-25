"""episodes.audio_url + jobs.kind allows feed_episode

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "episodes",
        sa.Column("audio_url", sa.Text(), nullable=True),
    )
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('youtube', 'podcast', 'resummarize', 'feed_episode')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('youtube', 'podcast', 'resummarize')",
    )
    op.drop_column("episodes", "audio_url")
