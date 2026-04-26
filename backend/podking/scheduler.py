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
    """Refresh feed display metadata. Does NOT auto-enqueue jobs — the user
    explicitly picks which episodes to summarize from the subscription
    detail page."""
    feed = feedparser.parse(sub.feed_url)

    feed_title = getattr(feed.feed, "title", None) or None
    feed_image: str | None = None
    image_attr = getattr(feed.feed, "image", None)
    if isinstance(image_attr, dict):
        feed_image = image_attr.get("href") or image_attr.get("url")
    if not feed_image:
        itunes_image = getattr(feed.feed, "itunes_image", None)
        if isinstance(itunes_image, dict):
            feed_image = itunes_image.get("href")

    sm = get_sessionmaker()
    async with sm() as db:
        s = await db.get(Subscription, sub.id)
        if s is None:
            return

        if feed_title:
            s.title = feed_title
        if feed_image:
            s.image_url = feed_image

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
