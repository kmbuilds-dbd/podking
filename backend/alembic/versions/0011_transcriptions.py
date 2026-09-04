"""persisted user-owned audio transcriptions

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcriptions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("segments", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_transcriptions_user_created",
        "transcriptions",
        ["user_id", sa.text("created_at DESC")],
    )

    op.add_column(
        "jobs",
        sa.Column(
            "transcription_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transcriptions.id", ondelete="CASCADE"),
            nullable=True, unique=True,
        ),
    )
    op.create_index("ix_jobs_transcription_id", "jobs", ["transcription_id"])
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('youtube', 'podcast', 'resummarize', 'feed_episode', 'tts', 'transcription')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('youtube', 'podcast', 'resummarize', 'feed_episode', 'tts')",
    )
    op.drop_index("ix_jobs_transcription_id", table_name="jobs")
    op.drop_column("jobs", "transcription_id")
    op.drop_index("ix_transcriptions_user_created", table_name="transcriptions")
    op.drop_table("transcriptions")
