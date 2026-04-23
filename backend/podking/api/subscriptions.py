from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import Subscription, User
from podking.schemas import SubscriptionCreate, SubscriptionPatch, SubscriptionResponse

router = APIRouter(prefix="/api")


async def _resolve_subscription(url: str) -> tuple[str, str]:
    """Return (kind, feed_url) for a YouTube channel or podcast RSS URL."""
    lower = url.lower()

    # Podcast RSS: not a YouTube URL, treat as direct RSS feed
    if "youtube.com" not in lower and "youtu.be" not in lower:
        return "podcast_feed", url

    # YouTube channel URL → extract channel id and build RSS feed URL
    channel_id = _extract_youtube_channel_id(url)
    if channel_id is None:
        raise HTTPException(
            status_code=400,
            detail="Could not extract YouTube channel ID from URL. "
            "Use a URL like youtube.com/channel/UC... or youtube.com/@handle",
        )
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    return "youtube_channel", feed_url


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

    try:
        result = subprocess.run(
            ["yt-dlp", "--no-warnings", "--print", "%(channel_id)s", "--playlist-items", "0", url],
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

    sub = Subscription(user_id=user.id, kind=kind, feed_url=feed_url)
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


@router.patch("/subscriptions/{sub_id}", response_model=SubscriptionResponse)
async def patch_subscription(
    sub_id: uuid.UUID,
    body: SubscriptionPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SubscriptionResponse:
    sub = await db.get(Subscription, sub_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="subscription not found")
    sub.active = body.active
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return SubscriptionResponse.model_validate(sub)
