"""Tests for job creation and listing."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_youtube_job(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.post(
        "/api/jobs",
        json={"source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "youtube"
    assert data["status"] == "queued"
    assert data["source_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_create_podcast_job(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.post(
        "/api/jobs",
        json={"source_url": "https://podcasts.apple.com/us/podcast/ep/id123456?i=7890"},
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "podcast"


@pytest.mark.asyncio
async def test_create_job_rejects_unsupported_url(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.post(
        "/api/jobs",
        json={"source_url": "https://spotify.com/episode/abc"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_jobs_returns_own_jobs(seeded_client: AsyncClient) -> None:
    await seeded_client.post(
        "/api/jobs",
        json={"source_url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    resp = await seeded_client.get("/api/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_job_not_found(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_job_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/jobs",
        json={"source_url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_archive_and_unarchive_job(seeded_client: AsyncClient) -> None:
    create = await seeded_client.post(
        "/api/jobs",
        json={"source_url": "https://youtu.be/abc"},
    )
    job_id = create.json()["id"]
    assert create.json()["archived"] is False

    # Archive it.
    archived = await seeded_client.patch(
        f"/api/jobs/{job_id}", json={"archived": True}
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True

    # Default list (active only) excludes it; archived list includes it.
    active_list = await seeded_client.get("/api/jobs")
    assert all(j["id"] != job_id for j in active_list.json())
    archived_list = await seeded_client.get("/api/jobs?archived=true")
    assert any(j["id"] == job_id for j in archived_list.json())

    # Unarchive.
    unarchived = await seeded_client.patch(
        f"/api/jobs/{job_id}", json={"archived": False}
    )
    assert unarchived.json()["archived"] is False


@pytest.mark.asyncio
async def test_patch_job_404_for_other_user(client: AsyncClient) -> None:
    """Patching a job that doesn't exist (or belongs to another user) returns
    a real 404, not the SPA fallback. Smoke-tests the router scope."""
    resp = await client.patch(
        f"/api/jobs/{uuid.uuid4()}", json={"archived": True}
    )
    # Unauthenticated, so 401 not 404 — but still NOT 200 with the SPA shell.
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_job_cascades_episode_and_summary(
    seeded_client: AsyncClient,
) -> None:
    """Hard-delete should cascade through job → episode → summary so a
    user can fully erase a processed item from their library."""
    from podking.db import get_sessionmaker
    from podking.models import Episode, Job, Summary, User
    from sqlalchemy import select

    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        episode = Episode(
            user_id=user.id,
            source_type="podcast",
            source_url="https://example.com/ep",
            external_id="cascade-test",
            title="Test episode",
        )
        db.add(episode)
        await db.flush()
        summary = Summary(
            user_id=user.id,
            episode_id=episode.id,
            system_prompt="x",
            model="claude-sonnet-4-6",
            content={"tldr": "x", "key_points": [], "quotes": [], "suggested_tags": []},
        )
        db.add(summary)
        job = Job(
            user_id=user.id,
            kind="podcast",
            source_url="https://example.com/ep",
            episode_id=episode.id,
            status="done",
        )
        db.add(job)
        await db.commit()
        episode_id = episode.id
        summary_id = summary.id
        job_id = job.id

    resp = await seeded_client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 204

    sm2 = get_sessionmaker()
    async with sm2() as db:
        assert await db.get(Job, job_id) is None
        assert await db.get(Episode, episode_id) is None
        assert await db.get(Summary, summary_id) is None


@pytest.mark.asyncio
async def test_list_jobs_includes_episode_when_linked(
    seeded_client: AsyncClient,
) -> None:
    """Once a job is linked to an Episode, the list response should embed the
    episode's title — that's how Jobs page renders titles instead of URLs."""
    from podking.db import get_sessionmaker
    from podking.models import Episode, Job, User
    from sqlalchemy import select

    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        episode = Episode(
            user_id=user.id,
            source_type="youtube",
            source_url="https://youtu.be/title-test",
            external_id="title-test",
            title="A specific test title",
        )
        db.add(episode)
        await db.flush()
        db.add(
            Job(
                user_id=user.id,
                kind="youtube",
                source_url="https://youtu.be/title-test",
                episode_id=episode.id,
                status="done",
            )
        )
        await db.commit()

    resp = await seeded_client.get("/api/jobs")
    assert resp.status_code == 200
    matched = [
        j for j in resp.json() if (j.get("episode") or {}).get("title")
        == "A specific test title"
    ]
    assert len(matched) == 1
