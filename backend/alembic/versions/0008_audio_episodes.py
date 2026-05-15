"""audio_episodes + tts job/settings columns

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── extend job kind / status check constraints ────────────────────────
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('youtube', 'podcast', 'resummarize', 'feed_episode', 'tts')",
    )
    op.drop_constraint("ck_job_status", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_status",
        "jobs",
        "status IN ('queued','fetching','transcribing','summarizing','embedding',"
        "'scripting','speaking','publishing','done','failed')",
    )

    # ── jobs.summary_id (nullable) ────────────────────────────────────────
    op.add_column(
        "jobs",
        sa.Column(
            "summary_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("summaries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_jobs_summary_id", "jobs", ["summary_id"])

    # ── user_settings voice overrides ─────────────────────────────────────
    op.add_column(
        "user_settings",
        sa.Column("tts_voice_a_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_settings",
        sa.Column("tts_voice_b_id", sa.Text(), nullable=True),
    )

    # ── audio_episodes ────────────────────────────────────────────────────
    op.create_table(
        "audio_episodes",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "summary_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("summaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("script", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("mp3_filename", sa.Text(), nullable=False),
        sa.Column("mp3_path", sa.Text(), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("voice_a_id", sa.Text(), nullable=False),
        sa.Column("voice_b_id", sa.Text(), nullable=False),
        sa.Column("published_url", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # one live audio per (user, summary)
    op.create_index(
        "uq_audio_episode_live_per_summary",
        "audio_episodes",
        ["user_id", "summary_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "ix_audio_episodes_user_created",
        "audio_episodes",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_audio_episodes_user_created", table_name="audio_episodes")
    op.drop_index("uq_audio_episode_live_per_summary", table_name="audio_episodes")
    op.drop_table("audio_episodes")
    op.drop_column("user_settings", "tts_voice_b_id")
    op.drop_column("user_settings", "tts_voice_a_id")
    op.drop_index("ix_jobs_summary_id", table_name="jobs")
    op.drop_column("jobs", "summary_id")
    op.drop_constraint("ck_job_status", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_status",
        "jobs",
        "status IN ('queued','fetching','transcribing','summarizing','embedding','done','failed')",
    )
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('youtube', 'podcast', 'resummarize', 'feed_episode')",
    )
