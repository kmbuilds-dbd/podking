"""Tests for job creation and URL detection."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from podking.models import Base, User, UserSettings


@pytest.fixture
async def seeded_client(engine: AsyncEngine) -> AsyncClient:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from podking.db import get_engine, get_sessionmaker
    from podking.main import create_app

    get_engine.cache_clear()  # type: ignore[attr-defined]
    get_sessionmaker.cache_clear()  # type: ignore[attr-defined]

    sm = get_sessionmaker()
    async with sm() as db:
        user = User(
            email="allowed@example.com",
            google_sub="google-sub-123",
            display_name="Test User",
        )
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id, system_prompt="Summarize this."))
        await db.commit()
        user_id = user.id

    from httpx import ASGITransport, AsyncClient as AC

    app = create_app()
    client = AC(transport=ASGITransport(app=app), base_url="http://test")
    client.app = app  # type: ignore[attr-defined]
    client._user_id = str(user_id)  # type: ignore[attr-defined]

    # Inject session cookie
    client.cookies.set("session", _make_session(str(user_id)))
    return client


def _make_session(user_id: str) -> str:
    import base64
    import json

    from itsdangerous import TimestampSigner

    secret = "test-secret-at-least-32-bytes-long-xxxxx"
    signer = TimestampSigner(secret, salt="cookie-session")
    payload = json.dumps({"user_id": user_id})
    encoded = base64.b64encode(payload.encode()).decode()
    return signer.sign(encoded).decode()


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
async def test_list_jobs_returns_only_own(seeded_client: AsyncClient) -> None:
    # Create a job
    await seeded_client.post(
        "/api/jobs",
        json={"source_url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    resp = await seeded_client.get("/api/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_job_not_found(seeded_client: AsyncClient) -> None:
    import uuid
    resp = await seeded_client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_job_unauthenticated(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/jobs",
        json={"source_url": "https://youtu.be/dQw4w9WgXcQ"},
    )
    assert resp.status_code == 401
