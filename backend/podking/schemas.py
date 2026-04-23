from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

# ── settings ──────────────────────────────────────────────────────────────────

class KeyStatus(BaseModel):
    set: bool


class SettingsResponse(BaseModel):
    system_prompt: str
    anthropic_key: KeyStatus
    elevenlabs_key: KeyStatus
    voyage_key: KeyStatus


class SettingsPatch(BaseModel):
    system_prompt: str | None = None
    anthropic_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    voyage_api_key: str | None = None


# ── jobs ──────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    source_url: str


class ResumamarizeCreate(BaseModel):
    episode_id: uuid.UUID


class JobResponse(BaseModel):
    id: uuid.UUID
    kind: str
    source_url: str | None
    episode_id: uuid.UUID | None
    status: str
    progress_pct: int
    progress_message: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


# ── episodes ──────────────────────────────────────────────────────────────────

class EpisodeResponse(BaseModel):
    id: uuid.UUID
    source_type: str
    source_url: str
    external_id: str
    title: str | None
    author: str | None
    published_at: datetime | None
    duration_seconds: int | None
    thumbnail_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── transcripts ───────────────────────────────────────────────────────────────

class TranscriptResponse(BaseModel):
    id: uuid.UUID
    source: str
    text: str
    segments: object | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── tags ──────────────────────────────────────────────────────────────────────

class TagResponse(BaseModel):
    id: uuid.UUID
    name: str
    count: int = 0


class SummaryTagResponse(BaseModel):
    name: str
    source: str  # 'llm' | 'user'


class TagPatch(BaseModel):
    add: list[str] = []
    remove: list[str] = []


# ── summaries ─────────────────────────────────────────────────────────────────

class SummaryResponse(BaseModel):
    id: uuid.UUID
    episode: EpisodeResponse
    system_prompt: str
    model: str
    content: object  # {tldr, key_points, quotes, suggested_tags}
    tags: list[SummaryTagResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── search ────────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    summary_id: uuid.UUID
    score: float
    matched_fields: list[str]
    episode: EpisodeResponse
    summary: SummaryResponse


# ── subscriptions ─────────────────────────────────────────────────────────────

class SubscriptionCreate(BaseModel):
    url: str


class SubscriptionPatch(BaseModel):
    active: bool


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    kind: str
    feed_url: str
    title: str | None
    last_checked_at: datetime | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
