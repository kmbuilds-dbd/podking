"""Tests for subscription endpoints."""
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
            google_sub="google-sub-sub-123",
            display_name="Test",
        )
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id, system_prompt=""))
        await db.commit()
        user_id = user.id

    from httpx import ASGITransport, AsyncClient as AC

    app = create_app()
    client = AC(transport=ASGITransport(app=app), base_url="http://test")
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
async def test_create_podcast_subscription(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/podcast.xml"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "podcast_feed"
    assert data["feed_url"] == "https://feeds.example.com/podcast.xml"
    assert data["active"] is True


@pytest.mark.asyncio
async def test_list_subscriptions(seeded_client: AsyncClient) -> None:
    await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/another.xml"},
    )
    resp = await seeded_client.get("/api/subscriptions")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_duplicate_subscription_rejected(seeded_client: AsyncClient) -> None:
    await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/dup.xml"},
    )
    resp = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/dup.xml"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_toggle_subscription(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/toggle.xml"},
    )
    sub_id = resp.json()["id"]
    resp2 = await seeded_client.patch(
        f"/api/subscriptions/{sub_id}",
        json={"active": False},
    )
    assert resp2.status_code == 200
    assert resp2.json()["active"] is False


@pytest.mark.asyncio
async def test_delete_subscription(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/delete.xml"},
    )
    sub_id = resp.json()["id"]
    resp2 = await seeded_client.delete(f"/api/subscriptions/{sub_id}")
    assert resp2.status_code == 204
    resp3 = await seeded_client.get("/api/subscriptions")
    assert all(s["id"] != sub_id for s in resp3.json())
