from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from podking.db import get_sessionmaker
from podking.models import AudioEpisode, Episode, Summary, User, UserSettings


@pytest.mark.asyncio
async def test_audio_episode_round_trip(engine) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="x@example.com", google_sub="g1")
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id, system_prompt=""))

        ep = Episode(
            user_id=user.id,
            source_type="youtube",
            source_url="https://youtu.be/x",
            external_id="x",
        )
        db.add(ep)
        await db.flush()

        s = Summary(
            episode_id=ep.id,
            user_id=user.id,
            system_prompt="",
            model="claude-sonnet-4-6",
            content={"tldr": "x"},
        )
        db.add(s)
        await db.flush()

        audio = AudioEpisode(
            user_id=user.id,
            summary_id=s.id,
            title="My episode",
            description="tldr text",
            script=[{"speaker": "A", "text": "hi"}, {"speaker": "B", "text": "yo"}],
            mp3_filename="x.mp3",
            mp3_path="/tmp/x.mp3",
            duration_sec=120,
            size_bytes=1024,
            voice_a_id="voiceA",
            voice_b_id="voiceB",
        )
        db.add(audio)
        await db.commit()

    async with sm() as db:
        result = await db.execute(select(AudioEpisode))
        row = result.scalar_one()
        assert row.title == "My episode"
        assert row.script[0]["speaker"] == "A"
        assert row.archived_at is None
