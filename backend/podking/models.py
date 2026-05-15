from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    google_sub: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    feed_token: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    settings: Mapped[UserSettings | None] = relationship(
        "UserSettings",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    episodes: Mapped[list[Episode]] = relationship("Episode", back_populates="user")
    jobs: Mapped[list[Job]] = relationship("Job", back_populates="user")
    summaries: Mapped[list[Summary]] = relationship("Summary", back_populates="user")
    tags: Mapped[list[Tag]] = relationship("Tag", back_populates="user")
    subscriptions: Mapped[list[Subscription]] = relationship(
        "Subscription", back_populates="user"
    )
    audio_episodes: Mapped[list[AudioEpisode]] = relationship(
        "AudioEpisode", back_populates="user"
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    system_prompt: Mapped[str] = mapped_column(String, nullable=False, default="")
    anthropic_api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    elevenlabs_api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    voyage_api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    tts_voice_a_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_voice_b_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="settings")


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "external_id", name="uq_episode_user_source"),
        CheckConstraint("source_type IN ('youtube', 'podcast')", name="ck_episode_source_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="episodes")
    transcript: Mapped[Transcript | None] = relationship(
        "Transcript", back_populates="episode", uselist=False, cascade="all, delete-orphan"
    )
    summaries: Mapped[list[Summary]] = relationship(
        "Summary", back_populates="episode", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship("Job", back_populates="episode")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('youtube', 'podcast', 'resummarize', 'feed_episode', 'tts')",
            name="ck_job_kind",
        ),
        CheckConstraint(
            "status IN ('queued','fetching','transcribing','summarizing','embedding',"
            "'scripting','speaking','publishing','done','failed')",
            name="ck_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True
    )
    summary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("summaries.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="jobs")
    episode: Mapped[Episode | None] = relationship("Episode", back_populates="jobs")
    audio_episode: Mapped[AudioEpisode | None] = relationship(
        "AudioEpisode", back_populates="job", uselist=False
    )


class Transcript(Base):
    __tablename__ = "transcripts"
    __table_args__ = (
        CheckConstraint(
            "source IN ('youtube_captions', 'elevenlabs')", name="ck_transcript_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("episodes.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    episode: Mapped[Episode] = relationship("Episode", back_populates="transcript")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    episode: Mapped[Episode] = relationship("Episode", back_populates="summaries")
    user: Mapped[User] = relationship("User", back_populates="summaries")
    summary_tags: Mapped[list[SummaryTag]] = relationship(
        "SummaryTag", back_populates="summary", cascade="all, delete-orphan"
    )
    audio_episode: Mapped[AudioEpisode | None] = relationship(
        "AudioEpisode",
        back_populates="summary",
        primaryjoin=(
            "and_(AudioEpisode.summary_id == Summary.id, "
            "AudioEpisode.archived_at.is_(None))"
        ),
        uselist=False,
        viewonly=True,
    )


class AudioEpisode(Base):
    __tablename__ = "audio_episodes"
    __table_args__ = (
        Index(
            "uq_audio_episode_live_per_summary",
            "user_id",
            "summary_id",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    script: Mapped[Any] = mapped_column(JSONB, nullable=False)
    mp3_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mp3_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    voice_a_id: Mapped[str] = mapped_column(Text, nullable=False)
    voice_b_id: Mapped[str] = mapped_column(Text, nullable=False)
    published_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="audio_episodes")
    summary: Mapped[Summary] = relationship("Summary", back_populates="audio_episode")
    job: Mapped[Job | None] = relationship("Job", back_populates="audio_episode")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="tags")
    summary_tags: Mapped[list[SummaryTag]] = relationship("SummaryTag", back_populates="tag")


class SummaryTag(Base):
    __tablename__ = "summary_tags"
    __table_args__ = (
        CheckConstraint("source IN ('llm', 'user')", name="ck_summary_tag_source"),
    )

    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("summaries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False)

    summary: Mapped[Summary] = relationship("Summary", back_populates="summary_tags")
    tag: Mapped[Tag] = relationship("Tag", back_populates="summary_tags")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "feed_url", name="uq_subscription_user_feed"),
        CheckConstraint(
            "kind IN ('youtube_channel', 'podcast_feed')", name="ck_subscription_kind"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="subscriptions")
