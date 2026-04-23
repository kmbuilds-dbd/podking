"""Tests for subscription endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


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
