"""Background schedulers: feed poller + audio retention cleanup."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import feedparser
from sqlalchemy import select

from podking.db import get_sessionmaker
from podking.models import Episode, Job, Subscription

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30 * 60  # 30 minutes between per-subscription checks
CLEANUP_INTERVAL_SECONDS = 24 * 3600


async def run_feed_poller() -> None:
    while True:
        try:
            await _poll_due_subscriptions()
        except Exception:
            log.exception("Feed poller error")
        await asyncio.sleep(60)  # check every minute which subs are due


async def run_retention_cleanup() -> None:
    while True:
        try:
            await _cleanup_audio()
            await _cleanup_old_jobs()
        except Exception:
            log.exception("Retention cleanup error")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


async def _poll_due_subscriptions() -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        cutoff = datetime.now(UTC) - timedelta(seconds=POLL_INTERVAL_SECONDS)
        result = await db.execute(
            select(Subscription).where(
                Subscription.active.is_(True),
                (Subscription.last_checked_at.is_(None))
                | (Subscription.last_checked_at < cutoff),
            )
        )
        subs = result.scalars().all()

    for sub in subs:
        try:
            await _check_subscription(sub)
        except Exception:
            log.exception("Error checking subscription %s", sub.id)


async def _check_subscription(sub: Subscription) -> None:
    feed = feedparser.parse(sub.feed_url)
    new_ids: list[tuple[str, str]] = []  # (external_id, entry_link)

    for entry in feed.entries:
        if sub.kind == "youtube_channel":
            eid = getattr(entry, "yt_videoid", None) or getattr(entry, "id", "")
        else:
            eid = getattr(entry, "id", "") or getattr(entry, "guid", "")

        if not eid:
            continue
        if sub.last_seen_external_id and eid <= sub.last_seen_external_id:
            continue
        link = getattr(entry, "link", "") or getattr(entry, "feedburner_origlink", "")
        new_ids.append((eid, link))

    sm = get_sessionmaker()
    async with sm() as db:
        # Reload sub in this session for update
        s = await db.get(Subscription, sub.id)
        if s is None:
            return

        for _eid, link in new_ids:
            if link:
                job = Job(
                    user_id=s.user_id,
                    kind="youtube" if s.kind == "youtube_channel" else "podcast",
                    source_url=link,
                    status="queued",
                )
                db.add(job)

        if new_ids:
            s.last_seen_external_id = new_ids[0][0]  # most recent first

        s.last_checked_at = datetime.now(UTC)
        await db.commit()


async def _cleanup_audio() -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        result = await db.execute(
            select(Episode).where(
                Episode.audio_expires_at.isnot(None),
                Episode.audio_expires_at < datetime.now(UTC),
                Episode.audio_path.isnot(None),
            )
        )
        episodes = result.scalars().all()

    for episode in episodes:
        try:
            if episode.audio_path and os.path.exists(episode.audio_path):
                os.unlink(episode.audio_path)
        except OSError:
            log.warning("Could not delete audio file %s", episode.audio_path)

        sm2 = get_sessionmaker()
        async with sm2() as db2:
            ep = await db2.get(Episode, episode.id)
            if ep:
                ep.audio_path = None
                await db2.commit()


async def _cleanup_old_jobs() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    sm = get_sessionmaker()
    async with sm() as db:
        result = await db.execute(
            select(Job).where(Job.created_at < cutoff)
        )
        for job in result.scalars():
            await db.delete(job)
        await db.commit()
