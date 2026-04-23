"""episodes, jobs, transcripts, summaries, tags, summary_tags, subscriptions

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("audio_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('youtube', 'podcast')", name="ck_episode_source_type"
        ),
        sa.UniqueConstraint(
            "user_id", "source_type", "external_id", name="uq_episode_user_source"
        ),
    )
    op.execute("CREATE INDEX ix_episodes_user_created ON episodes (user_id, created_at DESC)")

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "episode_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("episodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('youtube', 'podcast', 'resummarize')", name="ck_job_kind"
        ),
        sa.CheckConstraint(
            "status IN ('queued','fetching','transcribing','summarizing','embedding','done','failed')",  # noqa: E501
            name="ck_job_status",
        ),
    )
    op.execute("CREATE INDEX ix_jobs_user_created ON jobs (user_id, created_at DESC)")
    op.create_index(
        "ix_jobs_active_status",
        "jobs",
        ["status"],
        postgresql_where=sa.text(
            "status IN ('queued', 'fetching', 'transcribing', 'summarizing', 'embedding')"
        ),
    )

    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "episode_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segments", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('youtube_captions', 'elevenlabs')", name="ck_transcript_source"
        ),
    )

    op.create_table(
        "summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "episode_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # Add vector column and tsv generated column via raw SQL
    op.execute("ALTER TABLE summaries ADD COLUMN embedding vector(1024)")
    op.execute(
        """
        ALTER TABLE summaries ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(content::text, ''))
        ) STORED
        """
    )
    op.execute("CREATE INDEX ix_summaries_user_created ON summaries (user_id, created_at DESC)")
    op.execute("CREATE INDEX ix_summaries_tsv ON summaries USING GIN (tsv)")
    op.execute(
        "CREATE INDEX ix_summaries_embedding ON summaries USING hnsw (embedding vector_cosine_ops)"
        " WHERE embedding IS NOT NULL"
    )

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
    )

    op.create_table(
        "summary_tags",
        sa.Column(
            "summary_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("summaries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.CheckConstraint("source IN ('llm', 'user')", name="ck_summary_tag_source"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_external_id", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('youtube_channel', 'podcast_feed')", name="ck_subscription_kind"
        ),
        sa.UniqueConstraint("user_id", "feed_url", name="uq_subscription_user_feed"),
    )
    op.create_index(
        "ix_subscriptions_active_checked",
        "subscriptions",
        ["active", "last_checked_at"],
        postgresql_where=sa.text("active = true"),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("summary_tags")
    op.drop_table("tags")
    op.drop_table("summaries")
    op.drop_table("transcripts")
    op.drop_table("jobs")
    op.drop_table("episodes")
