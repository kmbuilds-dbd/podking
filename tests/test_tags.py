"""Tests for per-summary tag editing (user add/remove)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from podking.db import get_sessionmaker
from podking.models import Episode, Summary, SummaryTag, Tag, User
from sqlalchemy import select


@pytest.mark.asyncio
async def _seed_summary_with_llm_tag() -> tuple[str, str]:
    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        episode = Episode(
            user_id=user.id,
            source_type="youtube",
            source_url="https://youtu.be/tag-api",
            external_id="tag-api",
            title="Tag API",
        )
        db.add(episode)
        await db.flush()
        summary = Summary(
            user_id=user.id,
            episode_id=episode.id,
            system_prompt="g",
            model="claude-sonnet-4-6",
            content={"tldr": "t", "key_points": [], "quotes": [], "suggested_tags": []},
        )
        db.add(summary)
        await db.flush()
        tag = Tag(user_id=user.id, name="drake maye")
        db.add(tag)
        await db.flush()
        db.add(SummaryTag(summary_id=summary.id, tag_id=tag.id, source="llm"))
        await db.commit()
        return str(summary.id), str(tag.id)


@pytest.mark.asyncio
async def test_remove_tag_from_summary(seeded_client: AsyncClient) -> None:
    summary_id, _ = await _seed_summary_with_llm_tag()

    resp = await seeded_client.post(
        f"/api/summaries/{summary_id}/tags",
        json={"add": [], "remove": ["drake maye"]},
    )
    assert resp.status_code == 200
    assert all(t["name"] != "drake maye" for t in resp.json()["tags"])

    # Removing again is idempotent.
    resp2 = await seeded_client.post(
        f"/api/summaries/{summary_id}/tags",
        json={"add": [], "remove": ["drake maye"]},
    )
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_add_user_tag_to_summary(seeded_client: AsyncClient) -> None:
    summary_id, _ = await _seed_summary_with_llm_tag()

    resp = await seeded_client.post(
        f"/api/summaries/{summary_id}/tags",
        json={"add": ["ai"], "remove": []},
    )
    assert resp.status_code == 200
    assert any(t["name"] == "ai" and t["source"] == "user" for t in resp.json()["tags"])


@pytest.mark.asyncio
async def test_tag_remove_only_affects_own_summary(seeded_client: AsyncClient) -> None:
    summary_id, tag_id = await _seed_summary_with_llm_tag()

    await seeded_client.post(
        f"/api/summaries/{summary_id}/tags",
        json={"add": [], "remove": ["drake maye"]},
    )

    # The Tag row itself is shared metadata and must survive removal; only the
    # per-summary link is deleted.
    sm = get_sessionmaker()
    async with sm() as db:
        tag = await db.get(Tag, tag_id)
        assert tag is not None
        assert (
            await db.scalar(
                select(SummaryTag).where(SummaryTag.summary_id == summary_id)
            )
        ) is None
