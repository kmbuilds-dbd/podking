"""Job worker: asyncio loop that processes queued jobs one at a time."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import formatdate
from pathlib import Path

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from podking.config import get_settings
from podking.crypto import decrypt
from podking.db import get_sessionmaker
from podking.models import (
    AudioEpisode,
    Episode,
    Job,
    Summary,
    SummaryTag,
    Tag,
    Transcript,
    User,
    UserSettings,
)
from podking.pubsub import publish

log = logging.getLogger(__name__)

POLL_INTERVAL = 2  # seconds

_publish_lock = asyncio.Lock()


async def run_worker() -> None:
    """Run forever, picking up one job at a time."""
    while True:
        try:
            await _process_next_job()
        except Exception:
            log.exception("Unhandled error in worker loop")
        await asyncio.sleep(POLL_INTERVAL)


async def _process_next_job() -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        # Atomic pickup: UPDATE ... WHERE status='queued' ORDER BY created_at LIMIT 1
        result = await db.execute(
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
            .options(selectinload(Job.user))
        )
        job = result.scalar_one_or_none()
        if job is None:
            return

        job.status = "fetching"
        job.started_at = datetime.now(UTC)
        await db.commit()
        _emit(job.id, job)

    try:
        if job.kind == "youtube":
            await _run_youtube_job(job)
        elif job.kind == "podcast":
            await _run_podcast_job(job)
        elif job.kind == "resummarize":
            await _run_resummarize_job(job)
        elif job.kind == "feed_episode":
            await _run_feed_episode_job(job)
        elif job.kind == "tts":
            await _run_tts_job(job)
    except Exception as exc:
        await _fail_job(job.id, str(exc))
        log.exception("Job %s failed", job.id)


# ── progress helpers ──────────────────────────────────────────────────────────

def _emit(job_id: uuid.UUID, job: Job) -> None:
    publish(job_id, {
        "status": job.status,
        "progress_pct": job.progress_pct,
        "progress_message": job.progress_message,
        "error": job.error,
    })


async def _update_progress(job_id: uuid.UUID, pct: int, message: str) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.progress_pct = pct
        job.progress_message = message
        await db.commit()
        publish(job_id, {
            "status": job.status,
            "progress_pct": pct,
            "progress_message": message,
            "error": None,
        })


async def _complete_job(job_id: uuid.UUID, episode_id: uuid.UUID) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.status = "done"
        job.progress_pct = 100
        job.progress_message = "Done"
        job.episode_id = episode_id
        job.finished_at = datetime.now(UTC)
        await db.commit()
        publish(job_id, {"status": "done", "progress_pct": 100, "progress_message": "Done",
                         "error": None})


async def _fail_job(job_id: uuid.UUID, error: str) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = error[:1000]
        now = datetime.now(UTC)
        job.finished_at = now
        # Auto-archive failed jobs so they don't clutter the active list.
        if job.archived_at is None:
            job.archived_at = now
        await db.commit()
        publish(job_id, {"status": "failed", "progress_pct": job.progress_pct,
                         "progress_message": None, "error": error[:1000]})


async def _update_job_status(job_id: uuid.UUID, status: str) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        job = await db.get(Job, job_id)
        if job:
            job.status = status
            await db.commit()
            _emit(job_id, job)


# ── API key helpers ───────────────────────────────────────────────────────────

async def _get_settings(user_id: uuid.UUID) -> UserSettings:
    sm = get_sessionmaker()
    async with sm() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            raise RuntimeError("User settings not found")
        return settings


def _require_key(encrypted: bytes | None, name: str) -> str:
    if encrypted is None:
        raise RuntimeError(f"{name} API key is not configured in settings")
    return decrypt(encrypted)


# ── shared pipeline steps ─────────────────────────────────────────────────────

async def _summarize_and_embed(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    episode_id: uuid.UUID,
    transcript_text: str,
) -> None:
    settings = await _get_settings(user_id)
    anthropic_key = _require_key(settings.anthropic_api_key_encrypted, "Anthropic")

    await _update_progress(job_id, 80, "Summarizing…")
    await _update_job_status(job_id, "summarizing")

    from podking.worker.claude_client import summarize
    content: dict[str, object] = await summarize(
        transcript_text, settings.system_prompt, anthropic_key
    )

    await _update_progress(job_id, 95, "Embedding…")
    await _update_job_status(job_id, "embedding")

    embedding: list[float] | None = None
    if settings.voyage_api_key_encrypted:
        voyage_key = decrypt(settings.voyage_api_key_encrypted)
        try:
            from podking.worker.voyage_client import embed
            tldr = str(content.get("tldr") or "")
            key_points = list(content.get("key_points") or [])  # type: ignore[call-overload]
            points_str = " ".join(str(p) for p in key_points)
            embedding = await embed(f"{tldr} {points_str}", voyage_key)
        except Exception:
            log.warning("Voyage embedding failed for job %s; saving without embedding", job_id)

    # Persist summary + tags
    sm = get_sessionmaker()
    async with sm() as db:
        summary = Summary(
            episode_id=episode_id,
            user_id=user_id,
            system_prompt=settings.system_prompt,
            model="claude-sonnet-4-6",
            content=content,
            embedding=embedding,
        )
        db.add(summary)
        await db.flush()

        # Cap LLM-suggested tags at 3 even if Claude returns more — the prompt
        # asks for exactly 3, but enforcing in code keeps the library clean
        # if Claude ever drifts.
        suggested_tags = list(content.get("suggested_tags") or [])[:3]  # type: ignore[call-overload]
        for tag_name in suggested_tags:
            tag_result = await db.execute(
                select(Tag).where(Tag.user_id == user_id, Tag.name == str(tag_name))
            )
            tag = tag_result.scalar_one_or_none()
            if tag is None:
                tag = Tag(user_id=user_id, name=str(tag_name))
                db.add(tag)
                await db.flush()
            db.add(SummaryTag(summary_id=summary.id, tag_id=tag.id, source="llm"))

        await db.commit()


# ── YouTube job ───────────────────────────────────────────────────────────────

async def _run_youtube_job(job: Job) -> None:
    from podking.worker import youtube

    settings_cfg = get_settings()
    audio_dir = Path(settings_cfg.audio_storage_path)
    audio_dir.mkdir(parents=True, exist_ok=True)

    source_url = job.source_url or ""
    video_id = youtube.extract_video_id(source_url)

    await _update_progress(job.id, 5, "Fetching metadata…")

    meta = await youtube.fetch_metadata(source_url)
    duration = int(float(str(meta.get("duration") or 0)))
    if duration > settings_cfg.max_duration_seconds:
        raise RuntimeError(
            f"Video exceeds configured max duration ({settings_cfg.max_duration_seconds}s)"
        )

    # Upsert episode
    episode_id = await _upsert_episode(
        user_id=job.user_id,
        source_type="youtube",
        source_url=source_url,
        external_id=video_id,
        title=str(meta.get("title") or ""),
        author=str(meta.get("uploader") or ""),
        duration_seconds=duration,
        thumbnail_url=str(meta.get("thumbnail") or ""),
    )
    await _link_job_episode(job.id, episode_id)

    # Check for captions
    await _update_progress(job.id, 10, "Checking for captions…")
    langs = await youtube.probe_captions(source_url)

    transcript_text: str
    transcript_source: str

    if langs:
        lang = "en" if "en" in langs else langs[0]
        await _update_progress(job.id, 20, f"Downloading captions ({lang})…")
        transcript_text = await youtube.download_captions(source_url, lang)
        transcript_source = "youtube_captions"
    else:
        await _update_progress(job.id, 15, "No captions — downloading audio…")
        audio_path = audio_dir / f"{episode_id}.m4a"
        await youtube.download_audio(source_url, audio_path)

        await _upsert_audio_path(episode_id, str(audio_path))

        settings = await _get_settings(job.user_id)
        el_key = _require_key(settings.elevenlabs_api_key_encrypted, "ElevenLabs")

        await _update_progress(job.id, 40, "Transcribing audio…")
        await _update_job_status(job.id, "transcribing")

        from podking.worker.elevenlabs_client import transcribe
        result = await transcribe(audio_path, el_key)
        transcript_text = str(result["text"])
        transcript_source = "elevenlabs"

    await _upsert_transcript(episode_id, transcript_source, transcript_text)
    await _summarize_and_embed(job.id, job.user_id, episode_id, transcript_text)
    await _complete_job(job.id, episode_id)


# ── Podcast job ───────────────────────────────────────────────────────────────

async def _run_podcast_job(job: Job) -> None:
    from podking.worker import podcast

    settings_cfg = get_settings()
    audio_dir = Path(settings_cfg.audio_storage_path)
    audio_dir.mkdir(parents=True, exist_ok=True)

    source_url = job.source_url or ""

    await _update_progress(job.id, 5, "Resolving podcast feed…")
    podcast_id, episode_id_str = podcast.parse_apple_podcast_ids(source_url)
    feed_url = await podcast.resolve_feed_url(podcast_id)

    await _update_progress(job.id, 10, "Parsing feed…")
    # feedparser uses blocking urllib — keep it off the event loop.
    feed = await asyncio.to_thread(feedparser.parse, feed_url)
    entry = podcast.find_episode_in_feed(feed, episode_id_str)
    if entry is None:
        # Apple's `?i=` is an iTunes track ID, not the RSS feed's guid; for
        # most feeds those don't line up. Fall back to scraping Apple's page
        # for the episode title and matching that into the feed.
        await _update_progress(job.id, 12, "Resolving episode via Apple page…")
        meta = await podcast.fetch_apple_episode_metadata(source_url)
        if meta.get("title"):
            entry = podcast.find_episode_by_title(feed, str(meta["title"]))
        if entry is None:
            raise RuntimeError(
                "Episode not found in feed (matched neither guid nor title). "
                "Try subscribing to the podcast and summarizing from the "
                "subscription page instead."
            )

    duration_str = getattr(entry, "itunes_duration", None) or "0"
    duration = _parse_duration(str(duration_str))
    if duration > settings_cfg.max_duration_seconds:
        raise RuntimeError(
            f"Episode exceeds configured max duration ({settings_cfg.max_duration_seconds}s)"
        )

    enclosure_url = ""
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("audio"):
            enclosure_url = enc.get("href", "")
            break
    if not enclosure_url:
        raise RuntimeError("No audio enclosure found in feed entry")

    guid = getattr(entry, "id", episode_id_str)
    episode_id = await _upsert_episode(
        user_id=job.user_id,
        source_type="podcast",
        source_url=source_url,
        external_id=guid,
        title=getattr(entry, "title", None),
        author=getattr(feed.feed, "title", None),
        duration_seconds=duration,
        thumbnail_url=None,
    )
    await _link_job_episode(job.id, episode_id)

    await _update_progress(job.id, 15, "Downloading audio…")
    suffix = ".mp3" if "mp3" in enclosure_url.lower() else ".audio"
    audio_path = audio_dir / f"{episode_id}{suffix}"
    await podcast.download_audio(enclosure_url, audio_path)
    await _upsert_audio_path(episode_id, str(audio_path))

    settings = await _get_settings(job.user_id)
    el_key = _require_key(settings.elevenlabs_api_key_encrypted, "ElevenLabs")

    await _update_progress(job.id, 40, "Transcribing audio…")
    await _update_job_status(job.id, "transcribing")

    from podking.worker.elevenlabs_client import transcribe
    result = await transcribe(audio_path, el_key)
    transcript_text = str(result["text"])

    await _upsert_transcript(episode_id, "elevenlabs", transcript_text)
    await _summarize_and_embed(job.id, job.user_id, episode_id, transcript_text)
    await _complete_job(job.id, episode_id)


# ── Feed episode job (subscription-driven podcast) ────────────────────────────

async def _run_feed_episode_job(job: Job) -> None:
    """Process a podcast episode using a pre-resolved audio_url stored on
    the episode row by the subscription episode-process endpoint."""
    from podking.worker import podcast as podcast_helpers

    if job.episode_id is None:
        raise RuntimeError("feed_episode job missing episode_id")

    settings_cfg = get_settings()
    audio_dir = Path(settings_cfg.audio_storage_path)
    audio_dir.mkdir(parents=True, exist_ok=True)

    sm = get_sessionmaker()
    async with sm() as db:
        episode = await db.get(Episode, job.episode_id)
        if episode is None:
            raise RuntimeError("episode row missing for feed_episode job")
        if episode.user_id != job.user_id:
            raise RuntimeError("episode does not belong to job user")
        audio_url = episode.audio_url
        if not audio_url:
            raise RuntimeError("episode missing audio_url")
        episode_id = episode.id
        duration = episode.duration_seconds or 0

    if duration and duration > settings_cfg.max_duration_seconds:
        raise RuntimeError(
            f"Episode exceeds configured max duration ({settings_cfg.max_duration_seconds}s)"
        )

    await _link_job_episode(job.id, episode_id)

    await _update_progress(job.id, 15, "Downloading audio…")
    suffix = ".mp3" if "mp3" in audio_url.lower() else ".audio"
    audio_path = audio_dir / f"{episode_id}{suffix}"
    await podcast_helpers.download_audio(audio_url, audio_path)
    await _upsert_audio_path(episode_id, str(audio_path))

    settings = await _get_settings(job.user_id)
    el_key = _require_key(settings.elevenlabs_api_key_encrypted, "ElevenLabs")

    await _update_progress(job.id, 40, "Transcribing audio…")
    await _update_job_status(job.id, "transcribing")

    from podking.worker.elevenlabs_client import transcribe
    result = await transcribe(audio_path, el_key)
    transcript_text = str(result["text"])

    await _upsert_transcript(episode_id, "elevenlabs", transcript_text)
    await _summarize_and_embed(job.id, job.user_id, episode_id, transcript_text)
    await _complete_job(job.id, episode_id)


# ── Resummarize job ───────────────────────────────────────────────────────────

async def _run_resummarize_job(job: Job) -> None:
    if job.episode_id is None:
        raise RuntimeError("resummarize job missing episode_id")

    sm = get_sessionmaker()
    async with sm() as db:
        result = await db.execute(
            select(Transcript).where(Transcript.episode_id == job.episode_id)
        )
        transcript = result.scalar_one_or_none()
        if transcript is None:
            raise RuntimeError("No transcript available for this episode")
        transcript_text = transcript.text

    await _summarize_and_embed(job.id, job.user_id, job.episode_id, transcript_text)
    await _complete_job(job.id, job.episode_id)


# ── TTS job ───────────────────────────────────────────────────────────────────

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

    sm = get_sessionmaker()
    async with sm() as db:
        summary = await db.get(Summary, job.summary_id)
        if summary is None or summary.user_id != job.user_id:
            raise RuntimeError("summary missing for tts job")
        episode = await db.get(Episode, summary.episode_id)
        if episode is None:
            raise RuntimeError("episode missing for summary")
        summary_content = summary.content if isinstance(summary.content, dict) else {}
        episode_title = episode.title or "Episode"
        summary_episode_id = summary.episode_id
        user_row = await db.get(User, job.user_id)
        if user_row is None or not user_row.feed_token:
            raise RuntimeError(
                "User has no feed_token. Rotate one in Settings before generating audio."
            )
        feed_token = user_row.feed_token
        owner_email = user_row.email

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

    title = f"{episode_title} — podking"
    description = str(summary_content.get("tldr") or "podking summary")
    script_payload = [{"speaker": s.speaker, "text": s.text} for s in segments]

    # ── archive any prior live row + insert new ──────────────────────────
    prior_filenames: list[str] = []
    async with sm() as db:
        existing_result = await db.execute(
            select(AudioEpisode).where(
                AudioEpisode.user_id == job.user_id,
                AudioEpisode.summary_id == job.summary_id,
                AudioEpisode.archived_at.is_(None),
            )
        )
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

    async with sm() as db:
        all_rows_result = await db.execute(
            select(AudioEpisode)
            .where(AudioEpisode.user_id == job.user_id)
            .order_by(AudioEpisode.created_at.desc())
        )
        all_rows = list(all_rows_result.scalars())
        live_rows = [r for r in all_rows if r.archived_at is None]
        if len(live_rows) > 30:
            now = datetime.now(UTC)
            for stale in live_rows[30:]:
                stale.archived_at = now
            live_rows = live_rows[:30]
        await db.commit()

        # Snapshot the rows we need outside the session for the publisher.
        live_snapshot = [_to_published_episode(r) for r in live_rows]
        archived_filenames = list(dict.fromkeys(
            prior_filenames + [
                r.mp3_filename for r in all_rows if r.archived_at is not None
            ]
        ))
        # We don't want to ask the publisher to delete the very file we just
        # wrote. (If a regenerate raced a same-summary archive we already
        # excluded that by ordering above, but be defensive.)
        archived_filenames = [
            fn for fn in archived_filenames if fn != f"{audio_episode_id}.mp3"
        ]

    if settings_cfg.github_audio_repo.startswith("file://"):
        clone_url = settings_cfg.github_audio_repo
    else:
        clone_url = (
            f"https://x-access-token:{settings_cfg.github_pat}"
            f"@github.com/{settings_cfg.github_audio_repo}.git"
        )

    ctx = pub_mod.PublishContext(
        clone_url=clone_url,
        base_url=settings_cfg.github_audio_base_url,
        feed_token=feed_token,
        owner_email=settings_cfg.podking_feed_owner_email or owner_email,
        show_name=f"podking — {owner_email}",
        show_description="Personal podking-generated podcast feed.",
        language="en",
    )
    new_published = pub_mod.PublishedEpisode(
        id=audio_episode_id,
        mp3_path=out_path,
        mp3_filename=f"{audio_episode_id}.mp3",
        title=title,
        description=description,
        duration=_format_duration(synth.duration_sec),
        duration_sec=synth.duration_sec,
        size_bytes=synth.size_bytes,
        pub_date=formatdate(localtime=False, usegmt=True),
    )

    async with _publish_lock:
        published_url = await pub_mod.publish_audio_episode(
            new_episode=new_published,
            live_episodes=live_snapshot,
            archived_filenames=archived_filenames,
            ctx=ctx,
        )

    async with sm() as db:
        ae = await db.get(AudioEpisode, audio_episode_id)
        if ae is not None:
            ae.published_url = published_url
            await db.commit()

    await _complete_job(job.id, episode_id=summary_episode_id)


def _format_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _to_published_episode(row: AudioEpisode):
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


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _upsert_episode(
    user_id: uuid.UUID,
    source_type: str,
    source_url: str,
    external_id: str,
    title: str | None,
    author: str | None,
    duration_seconds: int | None,
    thumbnail_url: str | None,
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as db:
        result = await db.execute(
            select(Episode).where(
                Episode.user_id == user_id,
                Episode.source_type == source_type,
                Episode.external_id == external_id,
            )
        )
        episode = result.scalar_one_or_none()
        if episode is None:
            episode = Episode(
                user_id=user_id,
                source_type=source_type,
                source_url=source_url,
                external_id=external_id,
                title=title,
                author=author,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                audio_expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            db.add(episode)
            await db.commit()
            await db.refresh(episode)
        return episode.id


async def _link_job_episode(job_id: uuid.UUID, episode_id: uuid.UUID) -> None:
    """Set jobs.episode_id as soon as episode metadata is available, so the UI
    can render the title while the rest of the pipeline runs."""
    sm = get_sessionmaker()
    async with sm() as db:
        job = await db.get(Job, job_id)
        if job is not None and job.episode_id is None:
            job.episode_id = episode_id
            await db.commit()


async def _upsert_audio_path(episode_id: uuid.UUID, audio_path: str) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        episode = await db.get(Episode, episode_id)
        if episode:
            episode.audio_path = audio_path
            episode.audio_expires_at = datetime.now(UTC) + timedelta(days=7)
            await db.commit()


async def _upsert_transcript(
    episode_id: uuid.UUID, source: str, text: str
) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        result = await db.execute(
            select(Transcript).where(Transcript.episode_id == episode_id)
        )
        transcript = result.scalar_one_or_none()
        if transcript is None:
            transcript = Transcript(episode_id=episode_id, source=source, text=text)
            db.add(transcript)
        else:
            transcript.source = source
            transcript.text = text
        await db.commit()


def _parse_duration(s: str) -> int:
    """Parse HH:MM:SS or MM:SS or plain seconds string."""
    try:
        parts = [int(x) for x in s.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return int(s)
    except (ValueError, AttributeError):
        return 0
