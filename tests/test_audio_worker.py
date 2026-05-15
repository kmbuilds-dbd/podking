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
    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="u@x.com", google_sub="g1", feed_token="tok1")
        db.add(user)
        await db.flush()
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

    await runner._process_next_job()

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
