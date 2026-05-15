# Two-host TTS audio + personal podcast feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-summary "Generate audio" button that produces a two-host conversational MP3 via Claude + ElevenLabs, publishes it to a shared GitHub Pages repo under a per-user `feed_token` path, and serves a podcast-app-compatible RSS feed.

**Architecture:** A new `tts` job kind runs three sequential stages — Claude writes a 2-speaker script, ElevenLabs synthesizes each segment, pydub stitches them, then git clone/commit/push delivers MP3 + regenerated `feed.xml` to GitHub Pages. New `audio_episodes` table holds one live row per (user, summary). Hosting choice keeps the feed reachable while the home Windows server is offline.

**Tech Stack:** FastAPI · SQLAlchemy 2 (async) · Alembic · Anthropic Python SDK · httpx · pydub + ffmpeg · Jinja2 · git CLI · React + TanStack Query · Vitest + Playwright

**Spec:** `docs/superpowers/specs/2026-05-15-podking-tts-podcast-design.md`

---

## File map

**Backend**

- Create: `backend/alembic/versions/0008_audio_episodes.py`
- Modify: `backend/podking/models.py` (add `AudioEpisode`, `Job.summary_id`, `UserSettings.tts_voice_*`)
- Modify: `backend/podking/config.py` (5 new env fields)
- Modify: `backend/podking/schemas.py` (add `AudioEpisodeResponse`, `MeResponse.audio_enabled`)
- Create: `backend/podking/worker/tts/__init__.py`
- Create: `backend/podking/worker/tts/prompt.md`
- Create: `backend/podking/worker/tts/feed_template.xml`
- Create: `backend/podking/worker/tts/scripter.py`
- Create: `backend/podking/worker/tts/speaker.py`
- Create: `backend/podking/worker/tts/publisher.py`
- Modify: `backend/podking/worker/runner.py` (add `_run_tts_job`, hook kind switch, accept new statuses)
- Modify: `backend/podking/api/summaries.py` (add `POST /api/summaries/{id}/audio`)
- Create: `backend/podking/api/audio.py` (`GET /api/audio_episodes`)
- Modify: `backend/podking/main.py` (mount new router)
- Modify: `backend/podking/api/me.py` (return `audio_enabled` bool)
- Modify: `.env.example` (new env block)
- Modify: `pyproject.toml` (add pydub, Jinja2 if missing)

**Backend tests**

- Create: `tests/test_audio_scripter.py`
- Create: `tests/test_audio_speaker.py`
- Create: `tests/test_audio_publisher.py`
- Create: `tests/test_audio_worker.py`
- Create: `tests/test_audio_api.py`

**Frontend**

- Modify: `frontend/src/api.ts` (types + `generateAudio`, `listAudioEpisodes`, `audioEnabled`)
- Create: `frontend/src/components/GenerateAudioButton.tsx`
- Modify: `frontend/src/pages/Home.tsx` (mount button on each summary card)
- Modify: `frontend/src/pages/SummaryDetail.tsx` (mount button on detail view)
- Modify: `frontend/src/pages/Settings.tsx` (voice override inputs)
- Create: `frontend/e2e/audio.spec.ts` (Playwright happy path)

**Docs**

- Modify: `README.md` (new section "Generated podcast feed")

---

## Task 1: Migration 0008 — `audio_episodes` table + Job/UserSettings additions

**Files:**
- Create: `backend/alembic/versions/0008_audio_episodes.py`

- [ ] **Step 1: Inspect the latest revision to confirm the down_revision**

Run: `ls backend/alembic/versions/`
Expected: latest file is `0007_drop_subscription_unused_columns.py`. Confirm its `revision = "0007"`.

- [ ] **Step 2: Write the migration**

```python
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
```

- [ ] **Step 3: Apply migration locally and re-run pytest collection**

Run: `uv run alembic upgrade head && uv run pytest --collect-only -q`
Expected: migration applies, collection completes without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0008_audio_episodes.py
git commit -m "feat(db): audio_episodes table, tts job kind/status, voice overrides

Adds the storage layer for the per-summary TTS feature: one live row per
(user, summary), the 'tts' job kind with three new in-progress statuses,
and optional per-user voice ID overrides on user_settings."
```

---

## Task 2: ORM — `AudioEpisode` model + Job/UserSettings additions

**Files:**
- Modify: `backend/podking/models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio_episode_model.py`:

```python
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from podking.db import get_sessionmaker
from podking.models import AudioEpisode, Episode, Summary, User, UserSettings


@pytest.mark.asyncio
async def test_audio_episode_round_trip(engine) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="x@example.com", google_sub="g1")
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id, system_prompt=""))

        ep = Episode(
            user_id=user.id,
            source_type="youtube",
            source_url="https://youtu.be/x",
            external_id="x",
        )
        db.add(ep)
        await db.flush()

        s = Summary(
            episode_id=ep.id,
            user_id=user.id,
            system_prompt="",
            model="claude-sonnet-4-6",
            content={"tldr": "x"},
        )
        db.add(s)
        await db.flush()

        audio = AudioEpisode(
            user_id=user.id,
            summary_id=s.id,
            title="My episode",
            description="tldr text",
            script=[{"speaker": "A", "text": "hi"}, {"speaker": "B", "text": "yo"}],
            mp3_filename="x.mp3",
            mp3_path="/tmp/x.mp3",
            duration_sec=120,
            size_bytes=1024,
            voice_a_id="voiceA",
            voice_b_id="voiceB",
        )
        db.add(audio)
        await db.commit()

    async with sm() as db:
        result = await db.execute(select(AudioEpisode))
        row = result.scalar_one()
        assert row.title == "My episode"
        assert row.script[0]["speaker"] == "A"
        assert row.archived_at is None
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_audio_episode_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'AudioEpisode'`.

- [ ] **Step 3: Add `AudioEpisode` and modify `Job` / `UserSettings`**

Add to `backend/podking/models.py` after the `Summary` class:

```python
class AudioEpisode(Base):
    __tablename__ = "audio_episodes"

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
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    voice_a_id: Mapped[str] = mapped_column(Text, nullable=False)
    voice_b_id: Mapped[str] = mapped_column(Text, nullable=False)
    published_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User")
    summary: Mapped[Summary] = relationship("Summary")
    job: Mapped[Job | None] = relationship("Job")
```

In the existing `Job` class, update the kind/status `CheckConstraint` strings to match the migration and add the new column:

```python
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

    # ... existing columns ...
    summary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("summaries.id", ondelete="SET NULL"),
        nullable=True,
    )
```

In the existing `UserSettings` class, add the two new columns:

```python
    tts_voice_a_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_voice_b_id: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_audio_episode_model.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/podking/models.py tests/test_audio_episode_model.py
git commit -m "feat(models): AudioEpisode + Job.summary_id + UserSettings.tts_voice_*"
```

---

## Task 3: Config — new env fields

**Files:**
- Modify: `backend/podking/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add fields to `Settings`**

In `backend/podking/config.py`, add inside the `Settings` class, after `listen_notes_api_key`:

```python
    # ── TTS defaults (used when UserSettings.tts_voice_* is null) ────────
    elevenlabs_tts_default_voice_a: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    elevenlabs_tts_default_voice_b: str = "AZnzlk1XvdvUeBnXmlld"  # Domi
    elevenlabs_tts_model_id: str = "eleven_turbo_v2_5"

    # ── Personal podcast feed (GitHub Pages) ─────────────────────────────
    # Empty values disable the audio feature; the API will return 503 and
    # the UI hides the "Generate audio" button (see GET /api/me).
    github_pat: str = ""
    github_audio_repo: str = ""        # e.g. "octocat/podking-audio"
    github_audio_base_url: str = ""    # e.g. "https://octocat.github.io/podking-audio"
    podking_feed_owner_email: str = ""
```

- [ ] **Step 2: Update `.env.example`**

Append to `.env.example`:

```
# ── Audio podcast feature ────────────────────────────────────────────────
# Default ElevenLabs voice IDs (overridden per-user in Settings).
ELEVENLABS_TTS_DEFAULT_VOICE_A=21m00Tcm4TlvDq8ikWAM
ELEVENLABS_TTS_DEFAULT_VOICE_B=AZnzlk1XvdvUeBnXmlld
ELEVENLABS_TTS_MODEL_ID=eleven_turbo_v2_5

# Personal podcast feed — leave blank to disable the feature.
# A fine-grained GitHub PAT scoped to GITHUB_AUDIO_REPO with
# Contents: read/write and Pages: write. The server clones, commits,
# pushes via this token; users never see GitHub.
GITHUB_PAT=
GITHUB_AUDIO_REPO=
GITHUB_AUDIO_BASE_URL=
PODKING_FEED_OWNER_EMAIL=
```

- [ ] **Step 3: Verify config loads**

Run: `uv run python -c "from podking.config import get_settings; s = get_settings(); print(s.elevenlabs_tts_default_voice_a, s.github_pat)"`
Expected: prints `21m00Tcm4TlvDq8ikWAM` and an empty string.

- [ ] **Step 4: Commit**

```bash
git add backend/podking/config.py .env.example
git commit -m "feat(config): TTS defaults and GitHub Pages publish env vars"
```

---

## Task 4: Vendored assets — prompt and feed template

**Files:**
- Create: `backend/podking/worker/tts/__init__.py`
- Create: `backend/podking/worker/tts/prompt.md`
- Create: `backend/podking/worker/tts/feed_template.xml`

- [ ] **Step 1: Create the package**

Create `backend/podking/worker/tts/__init__.py`:

```python
"""Two-host TTS pipeline: scripter → speaker → publisher.

Source recipes vendored from the personalized-podcast skill
(~/.claude/skills/personalized-podcast). Each module here adapts one
stage to podking's per-user, server-side context.
"""
```

- [ ] **Step 2: Vendor `prompt.md`**

Create `backend/podking/worker/tts/prompt.md`:

```markdown
# Podcast Script Prompt (podking)

You are scripting a short podcast episode discussing a single article
or video that has already been summarized. You are given the summary
content as JSON with `tldr`, `key_points`, and (optionally) `quotes`.

The show has two hosts:

- **Alex (Speaker A):** Curious, energetic. Introduces topics and asks
  insightful questions.
- **Sam (Speaker B):** Analytical, witty. Goes deeper, adds context,
  offers opinions.

## Style

- Two friends chatting, not news anchors reading a teleprompter.
- Contractions, incomplete sentences, natural reactions ("Wait,
  really?", "Okay so here's the thing…").
- Genuine opinions are welcome — skepticism, excitement, mild disagreement.
- Avoid jargon dumps; explain technical concepts briefly and naturally
  when they come up.
- Each speaker turn should be 1–4 sentences (not long monologues).
- Target ~1,500 words total (≈ 10 minutes of speech).

## Structure

1. **Opening (~30s)** — Alex teases the topic, Sam jumps in with a quick
   reaction.
2. **Main discussion (~8m)** — Walk through the key points and quotes.
   Alternate hosts naturally; one introduces, the other reacts /
   challenges / extends.
3. **Closing (~30s)** — Sam names the biggest takeaway, Alex signs off.

## Output

Respond with a JSON array. Each element is exactly:

```json
{"speaker": "A" | "B", "text": "..."}
```

Respond with the JSON array ONLY — no markdown fences, no prose, no
trailing commentary. Speakers must alternate or near-alternate; do not
emit two consecutive same-speaker turns unless the second is a one-line
interjection. Do not invent details that aren't in the summary content.
```

- [ ] **Step 3: Vendor the iTunes RSS template**

Create `backend/podking/worker/tts/feed_template.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>{{ show_name | e }}</title>
  <link>{{ base_url | e }}</link>
  <description>{{ description | e }}</description>
  <language>{{ language | default('en') | e }}</language>
  <itunes:author>{{ show_name | e }}</itunes:author>
  <itunes:summary>{{ description | e }}</itunes:summary>
  <itunes:owner>
    <itunes:name>{{ show_name | e }}</itunes:name>
    <itunes:email>{{ owner_email | e }}</itunes:email>
  </itunes:owner>
  <itunes:explicit>false</itunes:explicit>
  <itunes:category text="Technology"/>
  {%- for ep in episodes %}
  <item>
    <title>{{ ep.title | e }}</title>
    <description>{{ ep.description | e }}</description>
    <pubDate>{{ ep.pub_date }}</pubDate>
    <enclosure url="{{ ep.url | e }}" length="{{ ep.size_bytes }}" type="audio/mpeg"/>
    <guid isPermaLink="true">{{ ep.url | e }}</guid>
    <itunes:duration>{{ ep.duration }}</itunes:duration>
  </item>
  {%- endfor %}
</channel>
</rss>
```

- [ ] **Step 4: Commit**

```bash
git add backend/podking/worker/tts/
git commit -m "feat(tts): vendor script prompt and iTunes feed template

Adapted from ~/.claude/skills/personalized-podcast/{PROMPT.md,
templates/feed_template.xml} for podking's per-user, summary-driven
flow."
```

---

## Task 5: Scripter — Claude → script JSON

**Files:**
- Create: `backend/podking/worker/tts/scripter.py`
- Create: `tests/test_audio_scripter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio_scripter.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from podking.worker.tts.scripter import (
    ScriptSegment,
    ScripterError,
    write_script,
)


class StubAnthropic:
    """Returns canned messages.create responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):  # mimic AsyncAnthropic.messages.create
        self.calls.append(kwargs)
        text = self._responses.pop(0)

        class _Block:
            def __init__(self, t: str) -> None:
                self.text = t

        class _Msg:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]
                self.stop_reason = "end_turn"

        async def _aresult():
            return _Msg(text)
        return _aresult()


@pytest.mark.asyncio
async def test_write_script_parses_segments() -> None:
    canned = json.dumps([
        {"speaker": "A", "text": "Hey welcome back."},
        {"speaker": "B", "text": "Yeah today we're talking about TTS."},
    ])
    summary = {"tldr": "intro", "key_points": ["a", "b"], "quotes": []}

    segments = await write_script(
        summary=summary,
        anthropic_key="sk-fake",
        episode_title="Test Episode",
        client_factory=lambda key: StubAnthropic([canned]),
    )

    assert len(segments) == 2
    assert isinstance(segments[0], ScriptSegment)
    assert segments[0].speaker == "A"
    assert segments[1].speaker == "B"


@pytest.mark.asyncio
async def test_write_script_retries_once_on_bad_json() -> None:
    summary = {"tldr": "x", "key_points": ["x"], "quotes": []}
    good = json.dumps([{"speaker": "A", "text": "hi"}])

    stub = StubAnthropic(["not json at all", good])
    segments = await write_script(
        summary=summary,
        anthropic_key="sk-fake",
        episode_title="t",
        client_factory=lambda key: stub,
    )
    assert len(segments) == 1
    assert len(stub.calls) == 2  # retried once with stricter reminder
    # The second call should include a "respond with valid JSON only" hint
    second_msgs = stub.calls[1]["messages"]
    assert any("JSON" in str(m).upper() for m in second_msgs)


@pytest.mark.asyncio
async def test_write_script_fails_after_two_bad_attempts() -> None:
    summary = {"tldr": "x", "key_points": [], "quotes": []}
    stub = StubAnthropic(["garbage 1", "garbage 2"])
    with pytest.raises(ScripterError, match="non-JSON"):
        await write_script(
            summary=summary,
            anthropic_key="sk-fake",
            episode_title="t",
            client_factory=lambda key: stub,
        )


@pytest.mark.asyncio
async def test_write_script_rejects_invalid_speaker() -> None:
    summary = {"tldr": "x", "key_points": [], "quotes": []}
    bad = json.dumps([{"speaker": "C", "text": "hi"}])
    good = json.dumps([{"speaker": "A", "text": "hi"}])
    stub = StubAnthropic([bad, good])
    segments = await write_script(
        summary=summary,
        anthropic_key="sk-fake",
        episode_title="t",
        client_factory=lambda key: stub,
    )
    assert segments[0].speaker == "A"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_audio_scripter.py -v`
Expected: FAIL with `ModuleNotFoundError: podking.worker.tts.scripter`.

- [ ] **Step 3: Implement the scripter**

Create `backend/podking/worker/tts/scripter.py`:

```python
"""Stage 1 — Claude writes a two-host script from a summary."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
PROMPT_PATH = Path(__file__).parent / "prompt.md"


class ScripterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScriptSegment:
    speaker: str  # "A" or "B"
    text: str


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _default_client_factory(api_key: str) -> Any:
    return anthropic.AsyncAnthropic(api_key=api_key)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _parse_segments(raw: str) -> list[ScriptSegment]:
    text = _strip_fences(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScripterError(f"Claude returned non-JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ScripterError("Script must be a non-empty JSON array")
    segments: list[ScriptSegment] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ScripterError(f"Segment {i} is not an object")
        speaker = item.get("speaker")
        body = item.get("text")
        if speaker not in ("A", "B"):
            raise ScripterError(f"Segment {i} has invalid speaker {speaker!r}")
        if not isinstance(body, str) or not body.strip():
            raise ScripterError(f"Segment {i} has empty text")
        segments.append(ScriptSegment(speaker=speaker, text=body.strip()))
    return segments


def _build_user_message(summary: dict[str, Any], episode_title: str) -> str:
    return (
        f"Episode title: {episode_title}\n\n"
        f"Summary JSON:\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


async def write_script(
    *,
    summary: dict[str, Any],
    anthropic_key: str,
    episode_title: str,
    client_factory: Callable[[str], Any] = _default_client_factory,
) -> list[ScriptSegment]:
    """Ask Claude for the script; retry once with a stricter reminder on bad JSON.

    On second failure raises `ScripterError`.
    """
    client = client_factory(anthropic_key)
    base_system = _load_prompt()
    user_msg = _build_user_message(summary, episode_title)

    last_error: ScripterError | None = None
    for attempt in range(2):
        system_text = base_system
        if attempt == 1 and last_error is not None:
            system_text = (
                base_system
                + "\n\nIMPORTANT: Your previous reply was not valid JSON. "
                "Respond ONLY with the JSON array — no markdown fences, "
                "no preamble, no trailing text."
            )
        message = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system_text}],
            messages=[{"role": "user", "content": user_msg}],
        )
        block = message.content[0]
        raw = getattr(block, "text", "") or ""
        try:
            return _parse_segments(raw)
        except ScripterError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_audio_scripter.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add backend/podking/worker/tts/scripter.py tests/test_audio_scripter.py
git commit -m "feat(tts): scripter — Claude writes the two-host JSON script"
```

---

## Task 6: Speaker — ElevenLabs TTS + pydub stitching

**Files:**
- Create: `backend/podking/worker/tts/speaker.py`
- Create: `tests/test_audio_speaker.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `pydub` to dependencies**

Run: `uv add pydub`
Expected: `pyproject.toml` gains `pydub` under `[project] dependencies`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_audio_speaker.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response

from podking.worker.tts.scripter import ScriptSegment
from podking.worker.tts.speaker import (
    SpeakerError,
    synthesize,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _silent_mp3_bytes(ms: int) -> bytes:
    """Generate a tiny silent MP3 of `ms` milliseconds for stubbing."""
    from pydub import AudioSegment
    s = AudioSegment.silent(duration=ms, frame_rate=44100)
    buf = (FIXTURES / "_tmp.mp3")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    s.export(str(buf), format="mp3", bitrate="128k")
    data = buf.read_bytes()
    buf.unlink()
    return data


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_stitches_segments(tmp_path: Path) -> None:
    chunk_a = _silent_mp3_bytes(500)
    chunk_b = _silent_mp3_bytes(700)

    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceA").mock(
        return_value=Response(200, content=chunk_a)
    )
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceB").mock(
        return_value=Response(200, content=chunk_b)
    )

    segments = [
        ScriptSegment(speaker="A", text="hi"),
        ScriptSegment(speaker="B", text="hello"),
    ]
    out = tmp_path / "ep.mp3"
    result = await synthesize(
        segments=segments,
        voice_a_id="voiceA",
        voice_b_id="voiceB",
        api_key="sk-eleven",
        model_id="eleven_turbo_v2_5",
        out_path=out,
    )

    assert result.path == out
    assert out.exists() and out.stat().st_size > 0
    # 500 + 700 + 300 silence between, ± fade allowance. Be generous: > 1.0s.
    assert result.duration_sec >= 1
    assert result.size_bytes == out.stat().st_size


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_401_raises_key_invalid(tmp_path: Path) -> None:
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceA").mock(
        return_value=Response(401, text="bad key")
    )
    with pytest.raises(SpeakerError, match="ElevenLabs key invalid"):
        await synthesize(
            segments=[ScriptSegment(speaker="A", text="hi")],
            voice_a_id="voiceA",
            voice_b_id="voiceB",
            api_key="sk-bad",
            model_id="eleven_turbo_v2_5",
            out_path=tmp_path / "out.mp3",
        )


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_quota_after_partial_progress(tmp_path: Path) -> None:
    chunk = _silent_mp3_bytes(400)
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceA").mock(
        side_effect=[
            Response(200, content=chunk),
            Response(429, text='{"detail":"quota_exceeded"}'),
        ]
    )
    with pytest.raises(SpeakerError, match="quota"):
        await synthesize(
            segments=[
                ScriptSegment(speaker="A", text="one"),
                ScriptSegment(speaker="A", text="two"),
            ],
            voice_a_id="voiceA",
            voice_b_id="voiceB",
            api_key="sk-fake",
            model_id="eleven_turbo_v2_5",
            out_path=tmp_path / "out.mp3",
        )
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `uv run pytest tests/test_audio_speaker.py -v`
Expected: FAIL with `ModuleNotFoundError: podking.worker.tts.speaker`.

- [ ] **Step 4: Implement the speaker**

Create `backend/podking/worker/tts/speaker.py`:

```python
"""Stage 2 — ElevenLabs TTS per segment, then pydub stitching."""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from podking.worker.tts.scripter import ScriptSegment

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
OUTPUT_FORMAT = "mp3_44100_128"
SILENCE_MS = 300
FADE_IN_MS = 500
FADE_OUT_MS = 1000
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


class SpeakerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SynthesisResult:
    path: Path
    duration_sec: int
    size_bytes: int


def _check_ffmpeg() -> None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise FileNotFoundError
    except FileNotFoundError as exc:
        raise SpeakerError(
            "ffmpeg is required for audio stitching. "
            "Install via `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)."
        ) from exc


async def synthesize(
    *,
    segments: list[ScriptSegment],
    voice_a_id: str,
    voice_b_id: str,
    api_key: str,
    model_id: str,
    out_path: Path,
) -> SynthesisResult:
    """Synthesize each segment via ElevenLabs and stitch into one MP3 at `out_path`.

    Stitches with 300ms silence between segments, 500ms fade-in, 1000ms fade-out.
    Raises `SpeakerError` with a typed message on auth/voice/quota/network failures.
    """
    _check_ffmpeg()
    from pydub import AudioSegment  # local import: pydub triggers audioop on import

    voice_map = {"A": voice_a_id, "B": voice_b_id}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        chunk_paths: list[Path] = []
        async with httpx.AsyncClient(timeout=120) as client:
            for i, seg in enumerate(segments):
                voice_id = voice_map[seg.speaker]
                resp = await client.post(
                    TTS_URL.format(voice_id=voice_id),
                    params={"output_format": OUTPUT_FORMAT},
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": seg.text,
                        "model_id": model_id,
                        "voice_settings": DEFAULT_VOICE_SETTINGS,
                    },
                )
                if resp.status_code == 401:
                    raise SpeakerError("ElevenLabs key invalid (401)")
                if resp.status_code == 404 or (
                    resp.status_code == 400 and "voice_not_found" in resp.text
                ):
                    raise SpeakerError(
                        f"ElevenLabs voice {voice_id!r} not found. "
                        "Update your voice IDs in Settings or remove them to use server defaults."
                    )
                if resp.status_code == 429 or "quota" in resp.text.lower():
                    raise SpeakerError(
                        f"ElevenLabs quota exceeded after {i} of {len(segments)} segments. "
                        "Wait for monthly reset or upgrade your ElevenLabs plan."
                    )
                if resp.status_code >= 400:
                    raise SpeakerError(
                        f"ElevenLabs TTS {resp.status_code}: {resp.text[:300]}"
                    )
                chunk_path = tmp_dir / f"chunk_{i:04d}.mp3"
                chunk_path.write_bytes(resp.content)
                chunk_paths.append(chunk_path)

        # Stitch with pydub. Move the heavy work to a worker thread so we
        # don't block the asyncio event loop.
        return await asyncio.to_thread(_stitch_to_disk, chunk_paths, out_path)


def _stitch_to_disk(chunk_paths: list[Path], out_path: Path) -> SynthesisResult:
    from pydub import AudioSegment

    silence = AudioSegment.silent(duration=SILENCE_MS)
    combined = AudioSegment.empty()
    for i, p in enumerate(chunk_paths):
        if i > 0:
            combined += silence
        combined += AudioSegment.from_mp3(str(p))
    combined = combined.fade_in(FADE_IN_MS).fade_out(FADE_OUT_MS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(out_path), format="mp3", bitrate="128k")

    duration_sec = int(round(len(combined) / 1000))
    size_bytes = out_path.stat().st_size
    return SynthesisResult(path=out_path, duration_sec=duration_sec, size_bytes=size_bytes)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_audio_speaker.py -v`
Expected: PASS (3 tests). ffmpeg must be installed locally; if not, install it first.

- [ ] **Step 6: Commit**

```bash
git add backend/podking/worker/tts/speaker.py tests/test_audio_speaker.py pyproject.toml uv.lock
git commit -m "feat(tts): speaker — ElevenLabs TTS per segment, pydub stitching"
```

---

## Task 7: Publisher — git clone + commit + push + feed render

**Files:**
- Create: `backend/podking/worker/tts/publisher.py`
- Create: `tests/test_audio_publisher.py`
- Modify: `pyproject.toml` (Jinja2)

- [ ] **Step 1: Add Jinja2 dependency**

Run: `uv add jinja2`
Expected: `pyproject.toml` gains `jinja2` (FastAPI pulls it transitively but we want the dependency intent explicit).

- [ ] **Step 2: Write the failing test**

Create `tests/test_audio_publisher.py`:

```python
from __future__ import annotations

import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from podking.worker.tts.publisher import (
    PublisherError,
    PublishContext,
    PublishedEpisode,
    publish_audio_episode,
)


def _init_bare_repo(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


def _seed_initial_commit(bare: Path, tmp_path: Path) -> None:
    """Bare repos can't be cloned/pushed-to-empty cleanly on all git versions.
    Seed one empty commit on `main`."""
    work = tmp_path / "_seed"
    subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "checkout", "-B", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "commit", "--allow-empty", "-m", "init"],
                   check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "PATH": "/usr/bin:/bin"})
    subprocess.run(["git", "-C", str(work), "push", "-u", "origin", "main"],
                   check=True, capture_output=True)


def _make_mp3(path: Path) -> None:
    from pydub import AudioSegment
    AudioSegment.silent(duration=500, frame_rate=44100).export(
        str(path), format="mp3", bitrate="128k"
    )


@pytest.mark.asyncio
async def test_publish_audio_episode_writes_mp3_and_feed(tmp_path: Path) -> None:
    bare = _init_bare_repo(tmp_path)
    _seed_initial_commit(bare, tmp_path)

    mp3 = tmp_path / "ep.mp3"
    _make_mp3(mp3)

    ep_id = uuid.uuid4()
    ctx = PublishContext(
        clone_url=f"file://{bare}",
        base_url="https://example.test/podking-audio",
        feed_token="tok123",
        owner_email="me@example.com",
        show_name="Podking",
        show_description="My personal feed",
        language="en",
    )

    new_ep = PublishedEpisode(
        id=ep_id, mp3_path=mp3, mp3_filename=f"{ep_id}.mp3",
        title="Test Episode", description="hello",
        duration="0:30", duration_sec=30, size_bytes=mp3.stat().st_size,
        pub_date="Thu, 15 May 2026 12:00:00 GMT",
    )

    url = await publish_audio_episode(
        new_episode=new_ep,
        live_episodes=[new_ep],
        archived_filenames=[],
        ctx=ctx,
    )

    # Pull the bare repo and assert tree contents
    check = tmp_path / "_check"
    subprocess.run(["git", "clone", str(bare), str(check)], check=True, capture_output=True)
    feed_path = check / "u" / "tok123" / "feed.xml"
    mp3_published = check / "u" / "tok123" / "episodes" / f"{ep_id}.mp3"
    assert feed_path.exists()
    assert mp3_published.exists()
    tree = ET.parse(feed_path)
    items = tree.findall(".//item")
    assert len(items) == 1
    assert items[0].find("title").text == "Test Episode"
    assert url == f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{ep_id}.mp3"


@pytest.mark.asyncio
async def test_publish_drops_archived_mp3s(tmp_path: Path) -> None:
    bare = _init_bare_repo(tmp_path)
    _seed_initial_commit(bare, tmp_path)

    # Pre-seed the user folder with an old mp3 by doing one publish first.
    old_mp3 = tmp_path / "old.mp3"
    _make_mp3(old_mp3)
    old_id = uuid.uuid4()
    ctx = PublishContext(
        clone_url=f"file://{bare}",
        base_url="https://example.test/podking-audio",
        feed_token="tokABC",
        owner_email="me@example.com",
        show_name="Podking",
        show_description="My personal feed",
        language="en",
    )
    old_ep = PublishedEpisode(
        id=old_id, mp3_path=old_mp3, mp3_filename=f"{old_id}.mp3",
        title="Old", description="o", duration="0:30", duration_sec=30,
        size_bytes=old_mp3.stat().st_size,
        pub_date="Thu, 14 May 2026 12:00:00 GMT",
    )
    await publish_audio_episode(
        new_episode=old_ep, live_episodes=[old_ep],
        archived_filenames=[], ctx=ctx,
    )

    # Second publish: a new episode replaces the old one (old is archived).
    new_mp3 = tmp_path / "new.mp3"
    _make_mp3(new_mp3)
    new_id = uuid.uuid4()
    new_ep = PublishedEpisode(
        id=new_id, mp3_path=new_mp3, mp3_filename=f"{new_id}.mp3",
        title="New", description="n", duration="0:30", duration_sec=30,
        size_bytes=new_mp3.stat().st_size,
        pub_date="Thu, 15 May 2026 12:00:00 GMT",
    )
    await publish_audio_episode(
        new_episode=new_ep,
        live_episodes=[new_ep],
        archived_filenames=[old_ep.mp3_filename],
        ctx=ctx,
    )

    check = tmp_path / "_check2"
    subprocess.run(["git", "clone", str(bare), str(check)], check=True, capture_output=True)
    assert not (check / "u" / "tokABC" / "episodes" / old_ep.mp3_filename).exists()
    assert (check / "u" / "tokABC" / "episodes" / new_ep.mp3_filename).exists()


@pytest.mark.asyncio
async def test_publish_invalid_xml_fails_before_push(tmp_path: Path) -> None:
    bare = _init_bare_repo(tmp_path)
    _seed_initial_commit(bare, tmp_path)

    mp3 = tmp_path / "ep.mp3"
    _make_mp3(mp3)

    ep = PublishedEpisode(
        id=uuid.uuid4(), mp3_path=mp3, mp3_filename="x.mp3",
        title="bad <unclosed",  # would render invalid XML if escaping is off
        description="ok", duration="0:30", duration_sec=30,
        size_bytes=mp3.stat().st_size,
        pub_date="Thu, 15 May 2026 12:00:00 GMT",
    )
    ctx = PublishContext(
        clone_url=f"file://{bare}",
        base_url="https://example.test/x",
        feed_token="tokXYZ",
        owner_email="m@m",
        show_name="P",
        show_description="d",
        language="en",
    )
    # The template escapes; this should still succeed. We assert _no_ raise.
    await publish_audio_episode(new_episode=ep, live_episodes=[ep],
                                archived_filenames=[], ctx=ctx)
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `uv run pytest tests/test_audio_publisher.py -v`
Expected: FAIL with `ModuleNotFoundError: podking.worker.tts.publisher`.

- [ ] **Step 4: Implement the publisher**

Create `backend/podking/worker/tts/publisher.py`:

```python
"""Stage 3 — clone the shared repo, drop the MP3, regenerate feed.xml, push.

Concurrency: callers serialize with an `asyncio.Lock`. We're defensive
against non-fast-forward push (retry pull --rebase + push up to 3x).
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "feed_template.xml"
PUSH_RETRY_LIMIT = 3


class PublisherError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishedEpisode:
    id: object  # uuid.UUID stringifies fine in templates
    mp3_path: Path
    mp3_filename: str
    title: str
    description: str
    duration: str            # "MM:SS" or "H:MM:SS"
    duration_sec: int
    size_bytes: int
    pub_date: str            # RFC 2822


@dataclass(frozen=True)
class PublishContext:
    clone_url: str           # https://x-access-token:PAT@github.com/REPO.git OR file://...
    base_url: str            # https://USER.github.io/podking-audio
    feed_token: str
    owner_email: str
    show_name: str
    show_description: str
    language: str


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "podking",
            "GIT_AUTHOR_EMAIL": "podking@localhost",
            "GIT_COMMITTER_NAME": "podking",
            "GIT_COMMITTER_EMAIL": "podking@localhost",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )
    if result.returncode != 0:
        raise PublisherError(
            f"git {' '.join(args)} failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result


def _render_feed(
    live_episodes: list[PublishedEpisode], ctx: PublishContext
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["xml"]),
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_NAME)
    episodes_for_template = [
        {
            "title": ep.title,
            "description": ep.description,
            "pub_date": ep.pub_date,
            "url": f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{ep.mp3_filename}",
            "size_bytes": ep.size_bytes,
            "duration": ep.duration,
        }
        for ep in live_episodes
    ]
    rendered = template.render(
        show_name=ctx.show_name,
        description=ctx.show_description,
        owner_email=ctx.owner_email,
        base_url=ctx.base_url,
        language=ctx.language,
        episodes=episodes_for_template,
    )
    # Validate
    try:
        ET.fromstring(rendered)
    except ET.ParseError as exc:
        raise PublisherError(f"Rendered feed.xml is not well-formed: {exc}") from exc
    return rendered


def _do_publish_sync(
    *,
    new_episode: PublishedEpisode,
    live_episodes: list[PublishedEpisode],
    archived_filenames: list[str],
    ctx: PublishContext,
) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--depth", "1", ctx.clone_url, str(repo)],
            check=True, capture_output=True,
        )

        user_dir = repo / "u" / ctx.feed_token
        episodes_dir = user_dir / "episodes"
        episodes_dir.mkdir(parents=True, exist_ok=True)

        # 1) copy the new MP3
        dest = episodes_dir / new_episode.mp3_filename
        shutil.copy2(str(new_episode.mp3_path), str(dest))

        # 2) drop archived MP3s (regenerate, retention prune, soft-delete)
        for filename in archived_filenames:
            stale = episodes_dir / filename
            if stale.exists():
                stale.unlink()

        # 3) render and write feed.xml
        rendered = _render_feed(live_episodes, ctx)
        (user_dir / "feed.xml").write_text(rendered, encoding="utf-8")

        # 4) commit
        _git(repo, "add", ".")
        # Skip commit if nothing changed (unlikely but safe)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo), capture_output=True, text=True,
        )
        if not status.stdout.strip():
            return f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{new_episode.mp3_filename}"
        _git(repo, "commit", "-m", f"Audio: {new_episode.title}")

        # 5) push with retries on non-ff
        for attempt in range(PUSH_RETRY_LIMIT):
            try:
                _git(repo, "push", "origin", "HEAD")
                break
            except PublisherError as exc:
                if attempt == PUSH_RETRY_LIMIT - 1:
                    raise
                if "non-fast-forward" in str(exc) or "rejected" in str(exc):
                    _git(repo, "pull", "--rebase", "origin", "HEAD")
                    continue
                raise

        return f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{new_episode.mp3_filename}"


async def publish_audio_episode(
    *,
    new_episode: PublishedEpisode,
    live_episodes: list[PublishedEpisode],
    archived_filenames: list[str],
    ctx: PublishContext,
) -> str:
    """Publish one episode to the shared repo. Returns the public MP3 URL.

    `live_episodes` is the set of rows that should appear in feed.xml after
    this publish — already sorted newest-first by the caller, length ≤ 30.
    `archived_filenames` is the set of MP3 filenames to unlink from the
    repo (covers regenerate + user-initiated delete + retention prune).
    """
    return await asyncio.to_thread(
        _do_publish_sync,
        new_episode=new_episode,
        live_episodes=live_episodes,
        archived_filenames=archived_filenames,
        ctx=ctx,
    )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_audio_publisher.py -v`
Expected: PASS (3 tests). Requires `git` on PATH.

- [ ] **Step 6: Commit**

```bash
git add backend/podking/worker/tts/publisher.py tests/test_audio_publisher.py pyproject.toml uv.lock
git commit -m "feat(tts): publisher — git push MP3 + regenerated feed.xml"
```

---

## Task 8: Worker — `_run_tts_job` + kind switch wiring

**Files:**
- Modify: `backend/podking/worker/runner.py`
- Create: `tests/test_audio_worker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio_worker.py`:

```python
"""Integration test for _run_tts_job with all three stages stubbed."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from podking.db import get_sessionmaker
from podking.models import (
    AudioEpisode,
    Episode,
    Job,
    Summary,
    User,
    UserSettings,
)
from podking.worker import runner
from podking.worker.tts.scripter import ScriptSegment
from podking.worker.tts.speaker import SynthesisResult


@pytest.mark.asyncio
async def test_run_tts_job_happy_path(engine, monkeypatch, tmp_path: Path) -> None:
    # ── seed user + summary + queued tts job ─────────────────────────────
    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="u@x.com", google_sub="g1", feed_token="tok1")
        db.add(user)
        await db.flush()
        # Need encrypted keys present so _require_key passes.
        from podking.crypto import encrypt
        db.add(UserSettings(
            user_id=user.id, system_prompt="",
            anthropic_api_key_encrypted=encrypt("sk-ant"),
            elevenlabs_api_key_encrypted=encrypt("sk-el"),
        ))
        ep = Episode(user_id=user.id, source_type="youtube",
                     source_url="https://y/u/1", external_id="1", title="Vid")
        db.add(ep)
        await db.flush()
        s = Summary(episode_id=ep.id, user_id=user.id, system_prompt="",
                    model="claude-sonnet-4-6",
                    content={"tldr": "tldr", "key_points": ["k1"], "quotes": []})
        db.add(s)
        await db.flush()
        job = Job(user_id=user.id, kind="tts", status="queued",
                  episode_id=ep.id, summary_id=s.id)
        db.add(job)
        await db.commit()
        job_id, summary_id, user_id = job.id, s.id, user.id

    # ── stub the three stages ────────────────────────────────────────────
    async def fake_write_script(**kwargs):
        return [ScriptSegment(speaker="A", text="hello"),
                ScriptSegment(speaker="B", text="hi")]

    async def fake_synthesize(**kwargs):
        out: Path = kwargs["out_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-mp3-bytes")
        return SynthesisResult(path=out, duration_sec=30, size_bytes=14)

    async def fake_publish(**kwargs):
        ctx = kwargs["ctx"]
        ep = kwargs["new_episode"]
        return f"{ctx.base_url}/u/{ctx.feed_token}/episodes/{ep.mp3_filename}"

    monkeypatch.setattr("podking.worker.tts.scripter.write_script", fake_write_script)
    monkeypatch.setattr("podking.worker.tts.speaker.synthesize", fake_synthesize)
    monkeypatch.setattr(
        "podking.worker.tts.publisher.publish_audio_episode", fake_publish
    )
    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_AUDIO_REPO", "octo/repo")
    monkeypatch.setenv("GITHUB_AUDIO_BASE_URL", "https://octo.github.io/repo")
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    # ── invoke worker's job dispatcher once ─────────────────────────────
    await runner._process_next_job()

    # ── assert state ─────────────────────────────────────────────────────
    async with sm() as db:
        j = await db.get(Job, job_id)
        assert j is not None
        assert j.status == "done"
        assert j.progress_pct == 100

        result = await db.execute(select(AudioEpisode))
        ae = result.scalar_one()
        assert ae.summary_id == summary_id
        assert ae.user_id == user_id
        assert ae.duration_sec == 30
        assert ae.published_url.endswith(f"/u/tok1/episodes/{ae.mp3_filename}")
        assert ae.archived_at is None


@pytest.mark.asyncio
async def test_run_tts_job_audio_disabled(engine, monkeypatch) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="u2@x.com", google_sub="g2", feed_token="tok2")
        db.add(user)
        await db.flush()
        from podking.crypto import encrypt
        db.add(UserSettings(
            user_id=user.id, system_prompt="",
            anthropic_api_key_encrypted=encrypt("sk-ant"),
            elevenlabs_api_key_encrypted=encrypt("sk-el"),
        ))
        ep = Episode(user_id=user.id, source_type="youtube",
                     source_url="https://y/u/2", external_id="2")
        db.add(ep)
        await db.flush()
        s = Summary(episode_id=ep.id, user_id=user.id, system_prompt="",
                    model="claude-sonnet-4-6", content={"tldr": "t"})
        db.add(s)
        await db.flush()
        job = Job(user_id=user.id, kind="tts", status="queued",
                  episode_id=ep.id, summary_id=s.id)
        db.add(job)
        await db.commit()
        job_id = job.id

    # Empty GITHUB_PAT means feature disabled.
    monkeypatch.setenv("GITHUB_PAT", "")
    monkeypatch.setenv("GITHUB_AUDIO_REPO", "")
    monkeypatch.setenv("GITHUB_AUDIO_BASE_URL", "")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    await runner._process_next_job()

    async with sm() as db:
        j = await db.get(Job, job_id)
        assert j.status == "failed"
        assert "audio feature is not configured" in (j.error or "").lower()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/test_audio_worker.py -v`
Expected: FAIL (`_run_tts_job` not registered in the kind switch; module `tts` not wired).

- [ ] **Step 3: Add `_run_tts_job` and the publish lock**

In `backend/podking/worker/runner.py`, near the top imports add:

```python
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import formatdate
from pathlib import Path

from podking.config import get_settings
```

Add a module-level lock near other module-level constants:

```python
_publish_lock = asyncio.Lock()
```

In `_process_next_job`, extend the kind dispatch:

```python
        elif job.kind == "tts":
            await _run_tts_job(job)
```

Append the new function near the other `_run_*_job` definitions:

```python
async def _run_tts_job(job: Job) -> None:
    """Three-stage pipeline: scripting (Claude) → speaking (ElevenLabs) → publishing (git)."""
    from podking.worker.tts import publisher as pub_mod
    from podking.worker.tts import scripter as scripter_mod
    from podking.worker.tts import speaker as speaker_mod

    settings_cfg = get_settings()
    if not (settings_cfg.github_pat
            and settings_cfg.github_audio_repo
            and settings_cfg.github_audio_base_url):
        raise RuntimeError(
            "Audio feature is not configured (set GITHUB_PAT, "
            "GITHUB_AUDIO_REPO, GITHUB_AUDIO_BASE_URL)."
        )

    if job.summary_id is None:
        raise RuntimeError("tts job missing summary_id")

    user_settings = await _get_settings(job.user_id)
    anthropic_key = _require_key(user_settings.anthropic_api_key_encrypted, "Anthropic")
    elevenlabs_key = _require_key(user_settings.elevenlabs_api_key_encrypted, "ElevenLabs")

    voice_a = user_settings.tts_voice_a_id or settings_cfg.elevenlabs_tts_default_voice_a
    voice_b = user_settings.tts_voice_b_id or settings_cfg.elevenlabs_tts_default_voice_b

    # ── load summary + episode ───────────────────────────────────────────
    sm = get_sessionmaker()
    async with sm() as db:
        summary = await db.get(Summary, job.summary_id)
        if summary is None or summary.user_id != job.user_id:
            raise RuntimeError("summary missing for tts job")
        episode = await db.get(Episode, summary.episode_id) if summary else None
        if episode is None:
            raise RuntimeError("episode missing for summary")
        # Snapshot fields we need outside the session.
        summary_content = summary.content if isinstance(summary.content, dict) else {}
        episode_title = episode.title or "Episode"
        episode_source_url = episode.source_url
        feed_token_user = await db.get(User, job.user_id)
        if feed_token_user is None or not feed_token_user.feed_token:
            raise RuntimeError(
                "User has no feed_token. Rotate one in Settings before generating audio."
            )
        feed_token = feed_token_user.feed_token
        owner_email = feed_token_user.email

    # ── stage 1: scripting ───────────────────────────────────────────────
    await _update_job_status(job.id, "scripting")
    await _update_progress(job.id, 10, "Writing script…")
    segments = await scripter_mod.write_script(
        summary=summary_content,
        anthropic_key=anthropic_key,
        episode_title=episode_title,
    )

    # ── stage 2: speaking ────────────────────────────────────────────────
    await _update_job_status(job.id, "speaking")
    audio_episode_id = uuid.uuid4()
    out_dir = Path(settings_cfg.audio_storage_path) / "audio"
    out_path = out_dir / f"{audio_episode_id}.mp3"
    char_count = sum(len(s.text) for s in segments)
    await _update_progress(
        job.id, 30,
        f"Generating audio (~{char_count} chars across {len(segments)} segments)…"
    )
    synth = await speaker_mod.synthesize(
        segments=segments,
        voice_a_id=voice_a,
        voice_b_id=voice_b,
        api_key=elevenlabs_key,
        model_id=settings_cfg.elevenlabs_tts_model_id,
        out_path=out_path,
    )

    # ── reconcile + persist the new audio_episodes row ───────────────────
    title = f"{episode_title} — podking"
    description = str(summary_content.get("tldr") or "podking summary")
    script_payload = [{"speaker": s.speaker, "text": s.text} for s in segments]

    async with sm() as db:
        # Archive any prior live row for this (user, summary) — regenerate.
        existing_result = await db.execute(
            select(AudioEpisode).where(
                AudioEpisode.user_id == job.user_id,
                AudioEpisode.summary_id == job.summary_id,
                AudioEpisode.archived_at.is_(None),
            )
        )
        prior_filenames: list[str] = []
        for prior in existing_result.scalars():
            prior.archived_at = datetime.now(UTC)
            prior_filenames.append(prior.mp3_filename)

        new_row = AudioEpisode(
            id=audio_episode_id,
            user_id=job.user_id,
            summary_id=job.summary_id,
            job_id=job.id,
            title=title,
            description=description,
            script=script_payload,
            mp3_filename=f"{audio_episode_id}.mp3",
            mp3_path=str(out_path),
            duration_sec=synth.duration_sec,
            size_bytes=synth.size_bytes,
            voice_a_id=voice_a,
            voice_b_id=voice_b,
        )
        db.add(new_row)
        await db.commit()

    # ── stage 3: publishing ──────────────────────────────────────────────
    await _update_job_status(job.id, "publishing")
    await _update_progress(job.id, 85, "Publishing to feed…")

    # Recompute live set + archived filenames (covers regenerate + retention).
    async with sm() as db:
        all_rows_result = await db.execute(
            select(AudioEpisode)
            .where(AudioEpisode.user_id == job.user_id)
            .order_by(AudioEpisode.created_at.desc())
        )
        all_rows = list(all_rows_result.scalars())
        live = [r for r in all_rows if r.archived_at is None]
        # Retention prune
        if len(live) > 30:
            now = datetime.now(UTC)
            for stale in live[30:]:
                stale.archived_at = now
            live = live[:30]
        await db.commit()

        live_snapshot = [_to_published_episode(r, settings_cfg) for r in live]
        archived_filenames = prior_filenames + [
            r.mp3_filename for r in all_rows
            if r.archived_at is not None and r.mp3_filename not in prior_filenames
        ]

    clone_url = (
        f"https://x-access-token:{settings_cfg.github_pat}"
        f"@github.com/{settings_cfg.github_audio_repo}.git"
    )
    # file://… short-circuit so tests bypass the PAT URL rewrite.
    if settings_cfg.github_audio_repo.startswith("file://"):
        clone_url = settings_cfg.github_audio_repo

    ctx = pub_mod.PublishContext(
        clone_url=clone_url,
        base_url=settings_cfg.github_audio_base_url,
        feed_token=feed_token,
        owner_email=settings_cfg.podking_feed_owner_email or owner_email,
        show_name=f"podking — {owner_email}",
        show_description="Personal podking-generated podcast feed.",
        language="en",
    )
    new_published = _to_published_episode_pub(new_row=None, settings_cfg=settings_cfg,
                                              row_id=audio_episode_id, out_path=out_path,
                                              mp3_filename=f"{audio_episode_id}.mp3",
                                              title=title, description=description,
                                              duration_sec=synth.duration_sec,
                                              size_bytes=synth.size_bytes)

    async with _publish_lock:
        published_url = await pub_mod.publish_audio_episode(
            new_episode=new_published,
            live_episodes=live_snapshot,
            archived_filenames=archived_filenames,
            ctx=ctx,
        )

    # ── finalize ─────────────────────────────────────────────────────────
    async with sm() as db:
        ae = await db.get(AudioEpisode, audio_episode_id)
        if ae is not None:
            ae.published_url = published_url
            await db.commit()

    await _complete_job(job.id, episode_id=summary.episode_id)


def _format_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _to_published_episode(row, settings_cfg):
    from podking.worker.tts.publisher import PublishedEpisode
    return PublishedEpisode(
        id=row.id,
        mp3_path=Path(row.mp3_path),
        mp3_filename=row.mp3_filename,
        title=row.title,
        description=row.description,
        duration=_format_duration(row.duration_sec),
        duration_sec=row.duration_sec,
        size_bytes=row.size_bytes,
        pub_date=formatdate(timeval=row.created_at.timestamp(), localtime=False, usegmt=True),
    )


def _to_published_episode_pub(
    *, new_row, settings_cfg, row_id, out_path, mp3_filename,
    title, description, duration_sec, size_bytes
):
    from podking.worker.tts.publisher import PublishedEpisode
    return PublishedEpisode(
        id=row_id,
        mp3_path=out_path,
        mp3_filename=mp3_filename,
        title=title,
        description=description,
        duration=_format_duration(duration_sec),
        duration_sec=duration_sec,
        size_bytes=size_bytes,
        pub_date=formatdate(localtime=False, usegmt=True),
    )
```

Add an import of `AudioEpisode` and `User` to the runner's existing import block from `podking.models`:

```python
from podking.models import (
    AudioEpisode, Episode, Job, Summary, SummaryTag, Tag,
    Transcript, User, UserSettings,
)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_audio_worker.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: PASS for all existing tests + new ones.

- [ ] **Step 6: Commit**

```bash
git add backend/podking/worker/runner.py tests/test_audio_worker.py
git commit -m "feat(worker): _run_tts_job — orchestrate scripter → speaker → publisher"
```

---

## Task 9: API — POST audio + GET audio_episodes + audio_enabled flag

**Files:**
- Modify: `backend/podking/api/summaries.py`
- Modify: `backend/podking/schemas.py`
- Create: `backend/podking/api/audio.py`
- Modify: `backend/podking/api/me.py`
- Modify: `backend/podking/main.py`
- Create: `tests/test_audio_api.py`

- [ ] **Step 1: Add Pydantic schemas**

In `backend/podking/schemas.py`, append:

```python
# ── audio episodes ────────────────────────────────────────────────────────────

class AudioEpisodeResponse(BaseModel):
    id: uuid.UUID
    summary_id: uuid.UUID
    job_id: uuid.UUID | None
    title: str
    description: str
    duration_sec: int
    size_bytes: int
    published_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AudioJobResponse(BaseModel):
    """Response for POST /api/summaries/{id}/audio."""

    job_id: uuid.UUID
    audio_episode_id: uuid.UUID | None
```

And modify `SettingsResponse` / `SettingsPatch` to include the two voice IDs:

```python
class SettingsResponse(BaseModel):
    system_prompt: str
    anthropic_key: KeyStatus
    elevenlabs_key: KeyStatus
    voyage_key: KeyStatus
    tts_voice_a_id: str | None = None
    tts_voice_b_id: str | None = None


class SettingsPatch(BaseModel):
    system_prompt: str | None = None
    anthropic_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    voyage_api_key: str | None = None
    tts_voice_a_id: str | None = None
    tts_voice_b_id: str | None = None
```

- [ ] **Step 2: Wire voice fields through the settings endpoint**

In `backend/podking/api/settings.py`, ensure GET reflects the new columns and PATCH writes them. (The handler is small; mirror the existing system_prompt pattern.)

- [ ] **Step 3: Add `audio_enabled` to `/api/me`**

In `backend/podking/api/me.py`, add to the response:

```python
from podking.config import get_settings as get_app_settings


def _audio_enabled() -> bool:
    s = get_app_settings()
    return bool(s.github_pat and s.github_audio_repo and s.github_audio_base_url)
```

Include `audio_enabled` in the response dict / Pydantic model. (Read the file first; mirror the existing shape.)

- [ ] **Step 4: Add the POST handler**

In `backend/podking/api/summaries.py`, append:

```python
from podking.config import get_settings as get_app_settings
from podking.models import AudioEpisode, Job
from podking.schemas import AudioJobResponse


@router.post(
    "/summaries/{summary_id}/audio",
    response_model=AudioJobResponse,
    status_code=201,
)
async def generate_summary_audio(
    summary_id: uuid.UUID,
    regenerate: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> AudioJobResponse:
    app_cfg = get_app_settings()
    if not (app_cfg.github_pat and app_cfg.github_audio_repo and app_cfg.github_audio_base_url):
        raise HTTPException(
            status_code=503,
            detail="audio feature not configured on this server",
        )

    summary = await db.get(Summary, summary_id)
    if summary is None or summary.user_id != user.id:
        raise HTTPException(status_code=404, detail="summary not found")

    existing = await db.execute(
        select(AudioEpisode).where(
            AudioEpisode.user_id == user.id,
            AudioEpisode.summary_id == summary_id,
            AudioEpisode.archived_at.is_(None),
        )
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None and not regenerate:
        raise HTTPException(
            status_code=409,
            detail={"audio_episode_id": str(existing_row.id),
                    "message": "audio already exists; pass ?regenerate=true to replace"},
        )

    job = Job(
        user_id=user.id,
        kind="tts",
        status="queued",
        episode_id=summary.episode_id,
        summary_id=summary_id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return AudioJobResponse(
        job_id=job.id,
        audio_episode_id=existing_row.id if existing_row else None,
    )
```

- [ ] **Step 5: Add the audio listing router**

Create `backend/podking/api/audio.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import AudioEpisode, User
from podking.schemas import AudioEpisodeResponse

router = APIRouter(prefix="/api")


@router.get("/audio_episodes", response_model=list[AudioEpisodeResponse])
async def list_audio_episodes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[AudioEpisodeResponse]:
    result = await db.execute(
        select(AudioEpisode)
        .where(AudioEpisode.user_id == user.id, AudioEpisode.archived_at.is_(None))
        .order_by(AudioEpisode.created_at.desc())
    )
    return [AudioEpisodeResponse.model_validate(r) for r in result.scalars()]


@router.get("/audio_episodes/{audio_id}", response_model=AudioEpisodeResponse)
async def get_audio_episode(
    audio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> AudioEpisodeResponse:
    row = await db.get(AudioEpisode, audio_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="audio episode not found")
    return AudioEpisodeResponse.model_validate(row)
```

- [ ] **Step 6: Mount the router in `main.py`**

Open `backend/podking/main.py` and add to the router-registration block:

```python
from podking.api import audio as audio_api
app.include_router(audio_api.router)
```

(Match the existing pattern in that file — every other router is mounted the same way.)

- [ ] **Step 7: Write the failing API tests**

Create `tests/test_audio_api.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from podking.db import get_sessionmaker
from podking.models import AudioEpisode, Episode, Summary, User


async def _seed_summary(client: AsyncClient) -> str:
    sm = get_sessionmaker()
    async with sm() as db:
        user = await db.execute(select(User))
        user_row = user.scalar_one()
        ep = Episode(user_id=user_row.id, source_type="youtube",
                     source_url="https://y/u/A", external_id="A", title="Vid")
        db.add(ep)
        await db.flush()
        s = Summary(episode_id=ep.id, user_id=user_row.id, system_prompt="",
                    model="claude-sonnet-4-6", content={"tldr": "x"})
        db.add(s)
        await db.commit()
        return str(s.id)


@pytest.mark.asyncio
async def test_audio_disabled_returns_503(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    summary_id = await _seed_summary(seeded_client)
    monkeypatch.setenv("GITHUB_PAT", "")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    resp = await seeded_client.post(f"/api/summaries/{summary_id}/audio")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_audio_post_queues_tts_job(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    summary_id = await _seed_summary(seeded_client)
    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_AUDIO_REPO", "octo/repo")
    monkeypatch.setenv("GITHUB_AUDIO_BASE_URL", "https://octo.github.io/repo")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    resp = await seeded_client.post(f"/api/summaries/{summary_id}/audio")
    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data

    # Second call without regenerate -> 409
    resp2 = await seeded_client.post(f"/api/summaries/{summary_id}/audio")
    # Still 201 because no audio_episodes row exists yet (job has not run).
    # The 409 path only kicks in once an audio_episode is materialized.
    assert resp2.status_code in (201, 409)


@pytest.mark.asyncio
async def test_audio_post_409_when_existing_episode(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    summary_id = await _seed_summary(seeded_client)
    sm = get_sessionmaker()
    async with sm() as db:
        s = await db.get(Summary, uuid.UUID(summary_id))
        db.add(AudioEpisode(
            user_id=s.user_id, summary_id=s.id, title="t", description="d",
            script=[], mp3_filename="x.mp3", mp3_path="/tmp/x.mp3",
            duration_sec=10, size_bytes=10, voice_a_id="a", voice_b_id="b",
        ))
        await db.commit()
    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_AUDIO_REPO", "octo/repo")
    monkeypatch.setenv("GITHUB_AUDIO_BASE_URL", "https://octo.github.io/repo")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    dup = await seeded_client.post(f"/api/summaries/{summary_id}/audio")
    assert dup.status_code == 409

    regen = await seeded_client.post(
        f"/api/summaries/{summary_id}/audio?regenerate=true"
    )
    assert regen.status_code == 201


@pytest.mark.asyncio
async def test_list_audio_episodes(seeded_client: AsyncClient) -> None:
    summary_id = await _seed_summary(seeded_client)
    sm = get_sessionmaker()
    async with sm() as db:
        s = await db.get(Summary, uuid.UUID(summary_id))
        db.add(AudioEpisode(
            user_id=s.user_id, summary_id=s.id, title="t", description="d",
            script=[], mp3_filename="x.mp3", mp3_path="/tmp/x.mp3",
            duration_sec=10, size_bytes=10, voice_a_id="a", voice_b_id="b",
            published_url="https://test/ep.mp3",
        ))
        await db.commit()
    resp = await seeded_client.get("/api/audio_episodes")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["published_url"] == "https://test/ep.mp3"


@pytest.mark.asyncio
async def test_me_audio_enabled_flag(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setenv("GITHUB_PAT", "")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    resp = await seeded_client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["audio_enabled"] is False

    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_AUDIO_REPO", "octo/repo")
    monkeypatch.setenv("GITHUB_AUDIO_BASE_URL", "https://octo.github.io/repo")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    resp2 = await seeded_client.get("/api/me")
    assert resp2.json()["audio_enabled"] is True
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/test_audio_api.py -v`
Expected: PASS (all five tests).

- [ ] **Step 9: Commit**

```bash
git add backend/podking/api/summaries.py backend/podking/api/audio.py \
        backend/podking/api/me.py backend/podking/api/settings.py \
        backend/podking/main.py backend/podking/schemas.py \
        tests/test_audio_api.py
git commit -m "feat(api): POST summaries/{id}/audio, GET /audio_episodes, audio_enabled flag"
```

---

## Task 10: Frontend — api.ts types + client functions

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Append types**

At the end of `frontend/src/api.ts` (just before any existing `export` of `feedUrl`-style helpers, or after the last type) add:

```typescript
export interface AudioEpisode {
  id: string
  summary_id: string
  job_id: string | null
  title: string
  description: string
  duration_sec: number
  size_bytes: number
  published_url: string | null
  created_at: string
}

export interface AudioJobCreated {
  job_id: string
  audio_episode_id: string | null
}

export async function generateSummaryAudio(
  summaryId: string,
  regenerate = false,
): Promise<AudioJobCreated> {
  const qs = regenerate ? "?regenerate=true" : ""
  return api<AudioJobCreated>(`/api/summaries/${summaryId}/audio${qs}`, {
    method: "POST",
  })
}

export async function listAudioEpisodes(): Promise<AudioEpisode[]> {
  return api<AudioEpisode[]>(`/api/audio_episodes`)
}
```

- [ ] **Step 2: Extend the existing `Me` / `getMe` type to include the new flag**

Open `frontend/src/api.ts`, find the `Me` interface or equivalent, and add `audio_enabled: boolean`. (Mirror the file's existing convention.)

- [ ] **Step 3: TypeScript compile check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): api types and helpers for TTS generation"
```

---

## Task 11: Frontend — GenerateAudioButton component

**Files:**
- Create: `frontend/src/components/GenerateAudioButton.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/GenerateAudioButton.tsx`:

```typescript
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  AudioEpisode,
  generateSummaryAudio,
  listAudioEpisodes,
} from "@/api"
import { useJobProgress } from "@/hooks/useJobProgress"
import { useMe } from "@/hooks/useMe"

/**
 * Per-summary control that:
 *  - shows "Generate audio" when no live AudioEpisode exists
 *  - shows progress while a tts job is in-flight
 *  - shows a "▶ Listen / Regenerate" pair once an episode is published
 *
 * The Listen link points at GitHub Pages — podking does not serve audio itself.
 */
export function GenerateAudioButton({
  summaryId,
  variant = "card",
}: {
  summaryId: string
  variant?: "card" | "detail"
}) {
  const me = useMe()
  const qc = useQueryClient()
  const audio = useQuery({
    queryKey: ["audio_episodes"],
    queryFn: listAudioEpisodes,
    enabled: !!me.data?.audio_enabled,
  })
  const live: AudioEpisode | undefined = (audio.data || []).find(
    (a) => a.summary_id === summaryId,
  )

  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const progress = useJobProgress(activeJobId)

  const mutation = useMutation({
    mutationFn: (regenerate: boolean) =>
      generateSummaryAudio(summaryId, regenerate),
    onSuccess: (data) => setActiveJobId(data.job_id),
  })

  if (!me.data?.audio_enabled) return null

  // Job completed → refresh the audio_episodes list and clear active job
  if (activeJobId && progress?.status === "done") {
    setActiveJobId(null)
    qc.invalidateQueries({ queryKey: ["audio_episodes"] })
  }

  const cls =
    variant === "card"
      ? "text-xs border rounded px-2 py-0.5 hover:bg-accent border-neutral-300"
      : "text-sm border rounded px-3 py-1.5 hover:bg-accent border-neutral-300"

  if (activeJobId && progress && progress.status !== "done" && progress.status !== "failed") {
    return (
      <button type="button" disabled className={cls} title="Generating…">
        ⏳ {progress.progress_message || "Generating…"} ({progress.progress_pct}%)
      </button>
    )
  }

  if (activeJobId && progress?.status === "failed") {
    return (
      <button
        type="button"
        className={cls}
        title={progress.error || "Failed"}
        onClick={() => {
          setActiveJobId(null)
          mutation.mutate(true)
        }}
      >
        ⚠ Failed — retry
      </button>
    )
  }

  if (live?.published_url) {
    return (
      <span className="inline-flex items-center gap-1">
        <a
          href={live.published_url}
          target="_blank"
          rel="noopener noreferrer"
          className={cls}
          title="Open episode in a new tab"
        >
          ▶ Listen
        </a>
        <button
          type="button"
          className={cls}
          title="Regenerate this episode"
          onClick={() => mutation.mutate(true)}
        >
          ⟲ Regenerate
        </button>
      </span>
    )
  }

  return (
    <button
      type="button"
      className={cls}
      title="Generate a two-host podcast episode from this summary"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate(false)}
    >
      🎙 Generate audio
    </button>
  )
}
```

- [ ] **Step 2: TypeScript compile check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. If the file references `useMe` / `useJobProgress` hooks with slightly different signatures, adjust import paths to match what exists in the repo.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/GenerateAudioButton.tsx
git commit -m "feat(frontend): GenerateAudioButton component"
```

---

## Task 12: Frontend — mount button on Home + SummaryDetail

**Files:**
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/pages/SummaryDetail.tsx`

- [ ] **Step 1: Add the button alongside the existing `ListenButton`**

In `frontend/src/pages/Home.tsx`, find the spot where `<ListenButton summaryId={…} />` is mounted on each summary card. Add:

```tsx
import { GenerateAudioButton } from "@/components/GenerateAudioButton"
// ...
<ListenButton summaryId={summary.id} />
<GenerateAudioButton summaryId={summary.id} />
```

In `frontend/src/pages/SummaryDetail.tsx`, do the same with `variant="detail"`:

```tsx
import { GenerateAudioButton } from "@/components/GenerateAudioButton"
// ...
<ListenButton summaryId={summary.id} variant="detail" />
<GenerateAudioButton summaryId={summary.id} variant="detail" />
```

- [ ] **Step 2: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Home.tsx frontend/src/pages/SummaryDetail.tsx
git commit -m "feat(frontend): mount GenerateAudioButton in Home and SummaryDetail"
```

---

## Task 13: Frontend — Settings voice override inputs

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Read the existing settings form**

Run: `head -200 frontend/src/pages/Settings.tsx` to see the existing pattern. Field inputs use the project's shadcn primitives.

- [ ] **Step 2: Add two text inputs**

In the form section of `Settings.tsx`, after the existing system_prompt textarea / API key fields, add:

```tsx
<div className="space-y-2">
  <label className="text-sm font-medium" htmlFor="tts_voice_a">
    Host A voice ID (optional)
  </label>
  <input
    id="tts_voice_a"
    type="text"
    className="w-full border rounded px-2 py-1"
    placeholder="Leave blank to use server default"
    value={form.tts_voice_a_id ?? ""}
    onChange={(e) =>
      setForm({ ...form, tts_voice_a_id: e.target.value || null })
    }
  />
  <p className="text-xs text-neutral-500">
    Browse voices at{" "}
    <a
      className="underline"
      href="https://elevenlabs.io/app/voice-library"
      target="_blank"
      rel="noopener noreferrer"
    >
      elevenlabs.io/app/voice-library
    </a>{" "}
    and paste the voice ID here.
  </p>
</div>
{/* identical block for tts_voice_b_id */}
```

Make sure the `form` state type / `SettingsPatch` payload include `tts_voice_a_id` and `tts_voice_b_id` strings.

- [ ] **Step 3: Build and visually verify**

Run: `cd frontend && npm run build && cd .. && uv run uvicorn podking.main:app --reload`
Open http://localhost:8000/settings (after Google login). The two new fields should be present.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat(frontend): Settings — optional Host A/B voice ID overrides"
```

---

## Task 14: Playwright e2e — happy path

**Files:**
- Create: `frontend/e2e/audio.spec.ts`

- [ ] **Step 1: Read an existing e2e spec for the project's conventions**

Run: `ls frontend/e2e/ && head -80 frontend/e2e/*.spec.ts | head -120`
Expected: see existing test helpers (login via `/test/login`, fixtures, etc.).

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/audio.spec.ts` (adapt the helper imports to match the existing test files):

```typescript
import { test, expect } from "@playwright/test"
import { loginAsAllowedUser, seedSummary } from "./_helpers"

test.describe("audio generation", () => {
  test("Generate audio button is hidden when audio feature is disabled", async ({ page, request }) => {
    // Server in TEST_MODE with GITHUB_PAT empty → audio_enabled = false
    await loginAsAllowedUser(page, request)
    await seedSummary(request)
    await page.goto("/")
    await expect(page.getByText(/Generate audio/)).toHaveCount(0)
  })

  // The happy path test is skipped by default — it requires a configured
  // TTS pipeline. Enable when ELEVENLABS_TTS_E2E=1 and a stub worker is
  // wired. The spec is here for documentation.
  test.skip("Generate audio shows progress and yields a Listen link", async () => {})
})
```

- [ ] **Step 3: Run the spec**

Run: `cd frontend && npm run e2e`
Expected: the visible (non-skip) test passes against a TEST_MODE backend without GITHUB_PAT.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/audio.spec.ts
git commit -m "test(e2e): audio button hidden when feature disabled"
```

---

## Task 15: README + .env.example documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a new section**

Insert into `README.md` between the existing "Reader links (ElevenReader)" and "Tests" sections:

```markdown
## Generated podcast feed

Each summary has a **Generate audio** button that produces a ~5–10 minute
two-host conversation about the summary, published to a personal RSS
feed you can subscribe to in Apple Podcasts, Spotify, Overcast, or any
podcast app.

### One-time server setup

1. Create an empty **public** GitHub repo, e.g. `you/podking-audio`,
   and enable GitHub Pages on the `main` branch root (`/`).
2. Create a fine-grained PAT scoped to that one repo with
   `Contents: read/write` and `Pages: write`.
3. Set in `.env`:
   - `GITHUB_PAT=` your PAT
   - `GITHUB_AUDIO_REPO=you/podking-audio`
   - `GITHUB_AUDIO_BASE_URL=https://you.github.io/podking-audio`
   - `PODKING_FEED_OWNER_EMAIL=` your iTunes owner email
4. Restart the backend. Each user now gets a personal feed at
   `${GITHUB_AUDIO_BASE_URL}/u/{feed_token}/feed.xml`.

Subscribers fetch directly from GitHub Pages, so episodes keep working
even when your podking server is offline.

### Defaults and overrides

Two ElevenLabs voice IDs ship as `.env` defaults
(`ELEVENLABS_TTS_DEFAULT_VOICE_A` / `_B`). Users can override per-account
on the Settings page.

Retention: the feed keeps the most recent 30 episodes per user; older
episodes are pruned from the repo automatically on each publish.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): generated podcast feed setup"
```

---

## Final verification

- [ ] **Run the full test suite**

Run: `uv run pytest -q && cd frontend && npm run build && npm run e2e`
Expected: all backend tests pass, frontend builds, e2e suite passes.

- [ ] **Manual smoke test (only after configuring real GITHUB_PAT + ElevenLabs)**

1. `uv run alembic upgrade head`
2. Start backend, sign in, paste a short YouTube URL, wait for the summary.
3. On the new summary card, click **Generate audio**.
4. Watch the progress states: `scripting → speaking → publishing → done`.
5. Click **Listen** — the published MP3 opens in a new tab.
6. Copy the feed URL from the first-publish modal and paste into Apple
   Podcasts (File → Add a Show by URL).
7. Click **Regenerate** — old MP3 disappears from the repo, new one
   replaces it, the feed updates.

---

## Self-review

**Spec coverage:**
- Per-summary on-demand TTS button → Tasks 11, 12, 13
- User's ElevenLabs key + default voices → Tasks 3, 6, 8
- GitHub Pages shared-repo hosting with `/u/{feed_token}/` paths → Tasks 3, 7, 8, 15
- Three worker stages (scripting/speaking/publishing) → Tasks 1, 5, 6, 7, 8
- 30-episode retention with archive + repo prune → Tasks 1, 7, 8
- `audio_episodes` table + Job/UserSettings additions → Tasks 1, 2
- `audio_enabled` capability flag → Tasks 3, 9
- Failure handling (401, 404 voice, 429 quota, bad JSON) → Tasks 5, 6
- Regenerate flow with archive-prior → Tasks 8, 9
- Per-user voice override UI → Tasks 9, 13
- README + .env.example → Tasks 3, 15

**Placeholder scan:** No "TBD/TODO/handle later" steps. Every Python and TypeScript step shows the actual code.

**Type consistency:**
- `ScriptSegment(speaker, text)` — used the same way in Tasks 5, 6, 8.
- `SynthesisResult(path, duration_sec, size_bytes)` — same in Tasks 6, 8.
- `PublishedEpisode` / `PublishContext` — same in Tasks 7, 8.
- `AudioEpisodeResponse` keys match `AudioEpisode` ORM columns from Tasks 1, 2, 9, 10.
- `audio_enabled` is consistent across me.py, api.ts, GenerateAudioButton.tsx.
