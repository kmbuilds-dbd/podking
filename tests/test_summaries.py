"""Tests for the summaries library (dedupe, listing)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from podking.db import get_sessionmaker
from podking.models import Episode, Summary, User
from sqlalchemy import select


@pytest.mark.asyncio
async def test_library_shows_newest_summary_per_episode(
    seeded_client: AsyncClient,
) -> None:
    """Re-summarizing creates a new row; the library must list only the
    newest summary per episode, not every historical copy."""
    from datetime import UTC, datetime, timedelta

    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        ep = Episode(
            user_id=user.id,
            source_type="podcast",
            source_url="https://example.com/dedupe",
            external_id="dedupe",
            title="Dedupe ep",
        )
        db.add(ep)
        await db.flush()
        old = Summary(
            user_id=user.id,
            episode_id=ep.id,
            system_prompt="old",
            model="claude-sonnet-4-6",
            content={"tldr": "OLD TLDR", "key_points": [], "quotes": [], "suggested_tags": []},
            created_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        db.add(old)
        await db.flush()
        new = Summary(
            user_id=user.id,
            episode_id=ep.id,
            system_prompt="new",
            model="claude-sonnet-4-6",
            content={"tldr": "NEW TLDR", "key_points": [], "quotes": [], "suggested_tags": []},
            created_at=datetime.now(UTC),
        )
        db.add(new)
        await db.commit()
        episode_id = ep.id

    resp = await seeded_client.get("/api/summaries?limit=100")
    assert resp.status_code == 200
    cards = resp.json()
    matches = [c for c in cards if c["episode"]["id"] == str(episode_id)]
    assert len(matches) == 1
    assert matches[0]["content"]["tldr"] == "NEW TLDR"
