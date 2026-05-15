from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from podking.db import get_sessionmaker
from podking.models import AudioEpisode, Episode, Summary, User


async def _seed_summary() -> str:
    sm = get_sessionmaker()
    async with sm() as db:
        user_row = (await db.execute(select(User))).scalar_one()
        ep = Episode(
            user_id=user_row.id, source_type="youtube",
            source_url="https://y/u/A", external_id="A", title="Vid",
        )
        db.add(ep)
        await db.flush()
        s = Summary(
            episode_id=ep.id, user_id=user_row.id, system_prompt="",
            model="claude-sonnet-4-6", content={"tldr": "x"},
        )
        db.add(s)
        await db.commit()
        return str(s.id)


@pytest.mark.asyncio
async def test_audio_disabled_returns_503(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    summary_id = await _seed_summary()
    monkeypatch.setenv("GITHUB_PAT", "")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    resp = await seeded_client.post(f"/api/summaries/{summary_id}/audio")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_audio_post_queues_tts_job(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    summary_id = await _seed_summary()
    monkeypatch.setenv("GITHUB_PAT", "ghp_x")
    monkeypatch.setenv("GITHUB_AUDIO_REPO", "octo/repo")
    monkeypatch.setenv("GITHUB_AUDIO_BASE_URL", "https://octo.github.io/repo")
    from podking.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    resp = await seeded_client.post(f"/api/summaries/{summary_id}/audio")
    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data
    assert data["audio_episode_id"] is None


@pytest.mark.asyncio
async def test_audio_post_409_when_existing_episode(
    seeded_client: AsyncClient, monkeypatch
) -> None:
    summary_id = await _seed_summary()
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
    summary_id = await _seed_summary()
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


@pytest.mark.asyncio
async def test_settings_voice_fields(seeded_client: AsyncClient) -> None:
    # PATCH sets them
    resp = await seeded_client.patch(
        "/api/settings",
        json={"tts_voice_a_id": "voiceA", "tts_voice_b_id": "voiceB"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tts_voice_a_id"] == "voiceA"
    assert body["tts_voice_b_id"] == "voiceB"

    # GET returns them
    get = await seeded_client.get("/api/settings")
    assert get.json()["tts_voice_a_id"] == "voiceA"

    # PATCH clears with empty string
    clear = await seeded_client.patch(
        "/api/settings", json={"tts_voice_a_id": ""}
    )
    assert clear.json()["tts_voice_a_id"] is None
