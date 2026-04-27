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


# ── Apple Podcast URL → RSS resolution ────────────────────────────────────

@pytest.mark.asyncio
async def test_apple_podcast_url_resolves_to_rss(
    seeded_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subscribing with a podcasts.apple.com URL should hit the iTunes
    Search lookup and store the resolved RSS feedUrl as feed_url."""
    from podking.worker import podcast as podcast_helpers

    async def fake_resolve(podcast_id: str) -> str:
        assert podcast_id == "1516093381"
        return "https://feeds.example.com/from-apple.xml"

    monkeypatch.setattr(podcast_helpers, "resolve_feed_url", fake_resolve)

    resp = await seeded_client.post(
        "/api/subscriptions",
        json={
            "url": "https://podcasts.apple.com/us/podcast/show/id1516093381"
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["kind"] == "podcast_feed"
    assert data["feed_url"] == "https://feeds.example.com/from-apple.xml"


# ── Episode listing + process ────────────────────────────────────────────

def _stub_feed_helpers(monkeypatch: pytest.MonkeyPatch, episodes: list[dict]) -> None:
    from podking.worker import feed as feed_helpers

    def fake_parse(feed_url: str, kind: str, limit: int) -> list[dict]:  # noqa: ARG001
        return episodes

    def fake_meta(feed_url: str) -> dict:  # noqa: ARG001
        return {"title": None, "image_url": None}

    monkeypatch.setattr(feed_helpers, "parse_feed_episodes", fake_parse)
    monkeypatch.setattr(feed_helpers, "fetch_feed_metadata", fake_meta)


@pytest.mark.asyncio
async def test_list_subscription_episodes(
    seeded_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_feed_helpers(
        monkeypatch,
        [
            {
                "external_id": "ext-1",
                "title": "First episode",
                "author": "The Show",
                "published_at_ms": None,
                "duration_seconds": 1800,
                "thumbnail": None,
                "source_url": "https://example.com/ep-1",
                "audio_url": "https://cdn.example.com/ep-1.mp3",
                "description": "First.",
            },
            {
                "external_id": "ext-2",
                "title": "Second episode",
                "author": "The Show",
                "published_at_ms": None,
                "duration_seconds": None,
                "thumbnail": None,
                "source_url": "https://example.com/ep-2",
                "audio_url": "https://cdn.example.com/ep-2.mp3",
                "description": "Second.",
            },
        ],
    )

    create = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/episodes-test.xml"},
    )
    sub_id = create.json()["id"]

    resp = await seeded_client.get(f"/api/subscriptions/{sub_id}/episodes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subscription"]["id"] == sub_id
    assert [e["external_id"] for e in body["episodes"]] == ["ext-1", "ext-2"]
    assert all(e["processed"] is False for e in body["episodes"])


@pytest.mark.asyncio
async def test_process_subscription_episode_creates_feed_episode_job(
    seeded_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hitting the process endpoint for a podcast subscription should
    create an Episode row with audio_url AND a feed_episode kind job
    referencing it."""
    from podking.db import get_sessionmaker
    from podking.models import Episode, Job
    from sqlalchemy import select

    _stub_feed_helpers(
        monkeypatch,
        [
            {
                "external_id": "ep-process-1",
                "title": "Process me",
                "author": "Show",
                "published_at_ms": 1700000000000,
                "duration_seconds": 1234,
                "thumbnail": "https://img.example.com/x.jpg",
                "source_url": "https://example.com/process",
                "audio_url": "https://cdn.example.com/process.mp3",
                "description": "x",
            }
        ],
    )

    create = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/process-test.xml"},
    )
    sub_id = create.json()["id"]

    resp = await seeded_client.post(
        f"/api/subscriptions/{sub_id}/episodes/process",
        json={"external_id": "ep-process-1"},
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["kind"] == "feed_episode"
    assert job["status"] == "queued"

    # The episode should exist with the audio_url stashed.
    sm = get_sessionmaker()
    async with sm() as db:
        ep = (
            await db.execute(
                select(Episode).where(Episode.external_id == "ep-process-1")
            )
        ).scalar_one()
        assert ep.audio_url == "https://cdn.example.com/process.mp3"
        # Job should reference it.
        j = (
            await db.execute(select(Job).where(Job.episode_id == ep.id))
        ).scalar_one()
        assert j.kind == "feed_episode"
        assert j.status == "queued"


@pytest.mark.asyncio
async def test_process_subscription_episode_unknown_external_id_404(
    seeded_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_feed_helpers(monkeypatch, [])

    create = await seeded_client.post(
        "/api/subscriptions",
        json={"url": "https://feeds.example.com/missing-ep.xml"},
    )
    sub_id = create.json()["id"]

    resp = await seeded_client.post(
        f"/api/subscriptions/{sub_id}/episodes/process",
        json={"external_id": "nonexistent"},
    )
    assert resp.status_code == 404


# ── Listen Notes podcast search ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_podcast_search_503_when_unconfigured(
    seeded_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If LISTEN_NOTES_API_KEY isn't set, the endpoint returns 503 instead
    of attempting the call with an empty key."""
    from podking.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "listen_notes_api_key", "")
    resp = await seeded_client.get("/api/podcast-search?q=anything")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_podcast_search_returns_lean_results(
    seeded_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When configured, the endpoint should return only the lean fields
    we use in the UI — title, publisher, image, itunes_id, etc. — with
    raw Listen Notes blobs filtered out."""
    from podking.config import get_settings
    from podking.worker import listennotes_client

    s = get_settings()
    monkeypatch.setattr(s, "listen_notes_api_key", "test-key")

    async def fake_search(api_key: str, q: str, limit: int) -> list[dict]:  # noqa: ARG001
        return [
            {
                "id": "ln-id-1",
                "title_original": "Real Podcast",
                "publisher_original": "Real Publisher",
                "description_original": "About things",
                "image": "https://i.example.com/big.jpg",
                "thumbnail": "https://i.example.com/small.jpg",
                "itunes_id": 12345,
                "total_episodes": 100,
                "listennotes_url": "https://listennotes.com/c/ln-id-1/",
            },
            {
                # Missing itunes_id → must be filtered out.
                "id": "ln-id-2",
                "title_original": "No iTunes",
                "publisher_original": "x",
            },
        ]

    monkeypatch.setattr(listennotes_client, "search_podcasts", fake_search)

    resp = await seeded_client.get("/api/podcast-search?q=podcast")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    r = body[0]
    assert r["title"] == "Real Podcast"
    assert r["publisher"] == "Real Publisher"
    assert r["image"] == "https://i.example.com/small.jpg"  # thumbnail preferred
    assert r["itunes_id"] == 12345
    # Raw "description_original" should be remapped to "description".
    assert r["description"] == "About things"
    assert "description_original" not in r
