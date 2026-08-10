from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_job_events_releases_db_transaction_before_streaming(engine) -> None:
    from podking.api.events import job_events
    from podking.db import get_sessionmaker
    from podking.models import Job, User, UserSettings

    sm = get_sessionmaker()
    async with sm() as setup_db:
        user = User(email="events@x.com", google_sub="events-google")
        setup_db.add(user)
        await setup_db.flush()
        setup_db.add(UserSettings(user_id=user.id, system_prompt=""))
        job = Job(user_id=user.id, kind="youtube", status="queued")
        setup_db.add(job)
        await setup_db.commit()
        user_id = user.id
        job_id = job.id

    async with sm() as db:
        user = await db.get(User, user_id)
        assert user is not None

        response = await job_events(job_id, db=db, user=user)

        assert not db.in_transaction()
        first_event = await anext(response.body_iterator)
        assert '"status": "queued"' in first_event
        assert not db.in_transaction()
        await response.body_iterator.aclose()
