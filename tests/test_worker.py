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


@pytest.mark.asyncio
async def test_resummarize_replaces_llm_tags(engine, monkeypatch) -> None:
    """Re-summarizing an episode must replace its previous LLM-suggested
    tags (no accumulation of stale tags like "drake maye") while keeping
    tags the user added themselves."""
    import uuid

    from podking.models import SummaryTag, Tag
    from sqlalchemy import func
    from sqlalchemy import select as sel

    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="worker-tags@x.com", google_sub="worker-tags")
        db.add(user)
        await db.flush()
        db.add(
            UserSettings(
                user_id=user.id,
                system_prompt="g",
                anthropic_api_key_encrypted=encrypt("sk-ant"),
            )
        )
        episode = Episode(
            user_id=user.id,
            source_type="youtube",
            source_url="https://youtu.be/tags",
            external_id="tags",
            title="Tags test",
        )
        db.add(episode)
        await db.flush()
        old = Summary(
            user_id=user.id,
            episode_id=episode.id,
            system_prompt="g",
            model="claude-sonnet-4-6",
            content={"tldr": "old", "key_points": [], "quotes": [], "suggested_tags": []},
        )
        db.add(old)
        await db.flush()
        for name, source in [
            ("drake maye", "llm"),
            ("new england patriots", "llm"),
            ("favorite", "user"),
        ]:
            tag = Tag(user_id=user.id, name=name)
            db.add(tag)
            await db.flush()
            db.add(SummaryTag(summary_id=old.id, tag_id=tag.id, source=source))
        await db.commit()
        episode_id, user_id, old_id = episode.id, user.id, old.id

    async def fake_summarize(transcript: str, system_prompt: str, api_key: str):
        return {
            "tldr": "t",
            "key_points": [],
            "quotes": [],
            "suggested_tags": ["ai", "football", "product management"],
        }

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr("podking.worker.claude_client.summarize", fake_summarize)
    monkeypatch.setattr(runner, "_update_progress", noop)
    monkeypatch.setattr(runner, "_update_job_status", noop)

    await runner._summarize_and_embed(
        uuid.uuid4(), user_id, episode_id, "transcript body", "custom prompt"
    )

    async with sm() as db:
        from sqlalchemy.orm import selectinload

        # Old LLM tags are gone, the user tag survives, and the new summary
        # carries exactly the three freshly suggested tags.
        old_llm_left = await db.scalar(
            sel(func.count())
            .select_from(SummaryTag)
            .where(SummaryTag.summary_id == old_id, SummaryTag.source == "llm")
        )
        assert old_llm_left == 0
        user_tags = (
            await db.execute(
                sel(SummaryTag)
                .where(
                    SummaryTag.summary_id == old_id, SummaryTag.source == "user"
                )
                .options(selectinload(SummaryTag.tag))
            )
        ).scalars().all()
        assert [st.tag.name for st in user_tags] == ["favorite"]
        new = (
            await db.execute(
                sel(Summary)
                .where(Summary.id != old_id)
                .options(selectinload(Summary.summary_tags).selectinload(SummaryTag.tag))
            )
        ).scalar_one()
        new_tag_names = {
            st.tag.name for st in new.summary_tags if st.source == "llm"
        }
        assert new_tag_names == {"ai", "football", "product management"}
