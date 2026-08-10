"""Tests for summarization worker prompt selection."""
from __future__ import annotations

import pytest
from podking.crypto import encrypt
from podking.db import get_sessionmaker
from podking.models import Episode, Job, Summary, User, UserSettings
from podking.worker import runner
from sqlalchemy import select


@pytest.mark.asyncio
async def test_summarize_worker_uses_job_prompt_snapshot(engine, monkeypatch) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="worker@x.com", google_sub="worker-google")
        db.add(user)
        await db.flush()
        db.add(
            UserSettings(
                user_id=user.id,
                system_prompt="general fallback",
                anthropic_api_key_encrypted=encrypt("sk-ant"),
            )
        )
        episode = Episode(
            user_id=user.id,
            source_type="youtube",
            source_url="https://youtu.be/worker",
            external_id="worker",
            title="Worker test",
        )
        db.add(episode)
        await db.flush()
        job = Job(
            user_id=user.id,
            kind="youtube",
            status="queued",
            episode_id=episode.id,
            analysis_prompt="custom queue-time guidance",
        )
        db.add(job)
        await db.commit()
        job_id, episode_id, user_id = job.id, episode.id, user.id

    seen: dict[str, str] = {}

    async def fake_summarize(transcript: str, system_prompt: str, api_key: str):
        seen["prompt"] = system_prompt
        return {
            "tldr": transcript,
            "key_points": [],
            "quotes": [],
            "suggested_tags": [],
        }

    async def noop_progress(*args, **kwargs):
        return None

    monkeypatch.setattr("podking.worker.claude_client.summarize", fake_summarize)
    monkeypatch.setattr(runner, "_update_progress", noop_progress)
    monkeypatch.setattr(runner, "_update_job_status", noop_progress)

    await runner._summarize_and_embed(
        job_id,
        user_id,
        episode_id,
        "transcript body",
        "custom queue-time guidance",
    )

    assert seen["prompt"] == "custom queue-time guidance"
    async with sm() as db:
        summary = (await db.execute(select(Summary))).scalar_one()
        assert summary.system_prompt == "custom queue-time guidance"
