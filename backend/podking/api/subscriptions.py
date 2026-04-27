from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.config import get_settings
from podking.deps import current_user, get_db
from podking.models import Episode, Job, Subscription, User
from podking.schemas import (
    JobResponse,
    SubscriptionCreate,
    SubscriptionResponse,
)
from podking.worker import feed as feed_helpers
from podking.worker import listennotes_client
from podking.worker import podcast as podcast_helpers

router = APIRouter(prefix="/api")


async def _resolve_subscription(url: str) -> tuple[str, str]:
    """Return (kind, feed_url) for a YouTube channel, Apple podcast, or RSS URL."""
    lower = url.lower()

    if "youtube.com" in lower or "youtu.be" in lower:
        channel_id = _extract_youtube_channel_id(url)
        if channel_id is None:
            raise HTTPException(
                status_code=400,
                detail="Could not extract YouTube channel ID from URL. "
                "Use a URL like youtube.com/channel/UC... or youtube.com/@handle",
            )
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        return "youtube_channel", feed_url

    if "podcasts.apple.com" in lower or "apple.com/podcast" in lower:
        m = re.search(r"/id(\d+)", url)
        if not m:
            raise HTTPException(
                status_code=400,
                detail="Could not extract Apple Podcast ID from URL.",
            )
        try:
            feed_url = await podcast_helpers.resolve_feed_url(m.group(1))
        except podcast_helpers.PodcastError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return "podcast_feed", feed_url

    # Anything else: assume direct RSS feed URL
    return "podcast_feed", url


def _extract_youtube_channel_id(url: str) -> str | None:
    """Extract channel id from common YouTube channel URL forms."""
    import re
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    # /channel/UCxxxxxx
    m = re.match(r"^/channel/(UC[\w-]+)$", path)
    if m:
        return m.group(1)

    # @handle or /c/name forms: we need yt-dlp to resolve these
    if path.startswith("/@") or path.startswith("/c/") or path.startswith("/user/"):
        return _resolve_via_ytdlp(url)

    return None


def _resolve_via_ytdlp(url: str) -> str | None:
    """Use yt-dlp to resolve a channel handle/name to a channel id."""
    import subprocess

    cookies_file = get_settings().yt_dlp_cookies_file
    auth_args = ["--cookies", cookies_file] if cookies_file else []

    try:
        result = subprocess.run(
            ["yt-dlp", *auth_args, "--no-warnings", "--print", "%(channel_id)s",
             "--playlist-items", "0", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        channel_id = result.stdout.strip()
        if channel_id and channel_id.startswith("UC"):
            return channel_id
    except Exception:
        pass
    return None


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[SubscriptionResponse]:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    return [SubscriptionResponse.model_validate(s) for s in result.scalars()]


@router.post(
    "/subscriptions", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED
)
async def create_subscription(
    body: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SubscriptionResponse:
    kind, feed_url = await _resolve_subscription(body.url)

    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.feed_url == feed_url,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="already subscribed to this feed")

    # Best-effort fetch of feed metadata so the UI has something nicer than
    # the raw RSS URL. Failures here shouldn't block the subscription —
    # the poller will refresh title/image on the next poll.
    title: str | None = None
    image_url: str | None = None
    try:
        meta = await asyncio.to_thread(feed_helpers.fetch_feed_metadata, feed_url)
        title = meta.get("title")
        image_url = meta.get("image_url")
    except Exception:  # noqa: BLE001
        pass

    sub = Subscription(
        user_id=user.id,
        kind=kind,
        feed_url=feed_url,
        title=title,
        image_url=image_url,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return SubscriptionResponse.model_validate(sub)


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(
    sub_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    sub = await db.get(Subscription, sub_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="subscription not found")
    await db.delete(sub)
    await db.commit()


# ── podcast search via Listen Notes ───────────────────────────────────────────


@router.get("/podcast-search")
async def search_podcasts(
    q: str = Query(..., min_length=1, max_length=200),
    user: User = Depends(current_user),
) -> list[dict[str, object]]:
    """Search Listen Notes for podcasts. Returns lean result dicts the
    Subscriptions UI uses to populate the search results list."""
    api_key = get_settings().listen_notes_api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Listen Notes search is not configured (missing LISTEN_NOTES_API_KEY).",
        )
    try:
        raw = await listennotes_client.search_podcasts(api_key, q, limit=10)
    except listennotes_client.ListenNotesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [
        {
            "id": r.get("id"),
            "title": r.get("title_original"),
            "publisher": r.get("publisher_original"),
            "description": r.get("description_original"),
            "image": r.get("thumbnail") or r.get("image"),
            "itunes_id": r.get("itunes_id"),
            "total_episodes": r.get("total_episodes"),
            "listennotes_url": r.get("listennotes_url"),
        }
        for r in raw
        if r.get("itunes_id")
    ]


# ── subscription episode listing + per-episode summarize ──────────────────────


class ProcessEpisodeBody(BaseModel):
    external_id: str


def _serialize_episode(
    ep: dict[str, object], processed_external_ids: set[str]
) -> dict[str, object]:
    return {
        "external_id": ep["external_id"],
        "title": ep.get("title"),
        "author": ep.get("author"),
        "published_at_ms": ep.get("published_at_ms"),
        "duration_seconds": ep.get("duration_seconds"),
        "thumbnail": ep.get("thumbnail"),
        "source_url": ep.get("source_url"),
        "audio_url": ep.get("audio_url"),
        "description": ep.get("description"),
        "processed": ep["external_id"] in processed_external_ids,
    }


@router.get("/subscriptions/{sub_id}/episodes")
async def list_subscription_episodes(
    sub_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    """Return recent episodes for a subscription's feed plus subscription
    metadata. The `processed` flag tells the UI whether we already have
    a summary for that episode."""
    sub = await db.get(Subscription, sub_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="subscription not found")

    episodes = await asyncio.to_thread(
        feed_helpers.parse_feed_episodes, sub.feed_url, sub.kind, limit
    )

    source_type = "youtube" if sub.kind == "youtube_channel" else "podcast"
    external_ids = [e["external_id"] for e in episodes]
    processed_external_ids: set[str] = set()
    if external_ids:
        result = await db.execute(
            select(Episode.external_id).where(
                Episode.user_id == user.id,
                Episode.source_type == source_type,
                Episode.external_id.in_(external_ids),
            )
        )
        processed_external_ids = {row[0] for row in result.all()}

    return {
        "subscription": SubscriptionResponse.model_validate(sub).model_dump(mode="json"),
        "episodes": [_serialize_episode(e, processed_external_ids) for e in episodes],
    }


@router.post(
    "/subscriptions/{sub_id}/episodes/process",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def process_subscription_episode(
    sub_id: uuid.UUID,
    body: ProcessEpisodeBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    """Find the requested episode in the subscription's feed and enqueue a
    summarization job for it. For YouTube channels this is a normal
    `youtube` job with the watch URL; for podcasts a `feed_episode` job
    that uses the enclosure URL we just resolved."""
    sub = await db.get(Subscription, sub_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="subscription not found")

    episodes = await asyncio.to_thread(
        feed_helpers.parse_feed_episodes, sub.feed_url, sub.kind, 100
    )
    match = next((e for e in episodes if e["external_id"] == body.external_id), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail="Episode not found in feed (it may have rolled off the recent window).",
        )

    if sub.kind == "youtube_channel":
        job = Job(
            user_id=user.id,
            kind="youtube",
            source_url=str(match["source_url"]),
            status="queued",
        )
    else:
        # Podcast feed-episode: persist Episode row with audio_url so the
        # worker can download directly without re-resolving an Apple URL.
        external_id = str(match["external_id"])
        existing = await db.execute(
            select(Episode).where(
                Episode.user_id == user.id,
                Episode.source_type == "podcast",
                Episode.external_id == external_id,
            )
        )
        episode = existing.scalar_one_or_none()
        published_at: datetime | None = None
        pub_ms = match.get("published_at_ms")
        if isinstance(pub_ms, int):
            published_at = datetime.fromtimestamp(pub_ms / 1000, tz=UTC)
        if episode is None:
            ep_title = match.get("title")
            ep_author = match.get("author")
            ep_duration = match.get("duration_seconds")
            ep_thumb = match.get("thumbnail")
            episode = Episode(
                user_id=user.id,
                source_type="podcast",
                source_url=str(
                    match.get("source_url") or match.get("audio_url") or sub.feed_url
                ),
                external_id=external_id,
                title=str(ep_title) if isinstance(ep_title, str) else None,
                author=str(ep_author) if isinstance(ep_author, str) else None,
                duration_seconds=ep_duration if isinstance(ep_duration, int) else None,
                thumbnail_url=str(ep_thumb) if isinstance(ep_thumb, str) else None,
                audio_url=str(match["audio_url"]),
                published_at=published_at,
            )
            db.add(episode)
            await db.flush()
        else:
            episode.audio_url = str(match["audio_url"])

        job = Job(
            user_id=user.id,
            kind="feed_episode",
            source_url=str(match.get("source_url") or match["audio_url"]),
            episode_id=episode.id,
            status="queued",
        )

    db.add(job)
    await db.commit()
    await db.refresh(job)
    return JobResponse(
        id=job.id,
        kind=job.kind,
        source_url=job.source_url,
        episode_id=job.episode_id,
        episode=None,
        status=job.status,
        progress_pct=job.progress_pct,
        progress_message=job.progress_message,
        error=job.error,
        archived=job.archived_at is not None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
