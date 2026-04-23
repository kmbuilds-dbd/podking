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
