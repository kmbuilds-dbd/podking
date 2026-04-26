"""Feed parsing helpers shared between subscription episode listing and the
worker pipeline. Consumes both YouTube channel feeds (Atom) and podcast RSS."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import feedparser


def _parse_itunes_duration(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    while len(nums) < 3:
        nums.insert(0, 0)
    h, m, sec = nums[-3:]
    return h * 3600 + m * 60 + sec


def _episode_audio(entry: feedparser.FeedParserDict) -> str | None:
    for enc in getattr(entry, "enclosures", []) or []:
        href = enc.get("href")
        type_ = (enc.get("type") or "").lower()
        if href and (type_.startswith("audio") or _looks_like_audio_url(href)):
            return str(href)
    return None


def _looks_like_audio_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in (".mp3", ".m4a", ".aac", ".ogg", ".wav"))


def _episode_thumbnail(entry: feedparser.FeedParserDict) -> str | None:
    image = getattr(entry, "image", None)
    if isinstance(image, dict) and image.get("href"):
        return str(image["href"])
    media_thumbnail = getattr(entry, "media_thumbnail", None)
    if isinstance(media_thumbnail, list) and media_thumbnail:
        href = media_thumbnail[0].get("url")
        if href:
            return str(href)
    return None


def parse_feed_episodes(
    feed_url: str, kind: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Parse a podcast or YouTube channel feed and return a list of episodes.

    Each episode dict contains: external_id, title, author, published_at_ms,
    duration_seconds, thumbnail, source_url (web link), audio_url (None for
    YouTube — the source_url IS the watch URL), description.
    """
    feed = feedparser.parse(feed_url)

    out: list[dict[str, Any]] = []
    for entry in feed.entries[:limit]:
        if kind == "youtube_channel":
            video_id = getattr(entry, "yt_videoid", None)
            if not video_id:
                # Fall back to extracting from link
                link = getattr(entry, "link", "") or ""
                m = re.search(r"v=([\w-]+)", link)
                video_id = m.group(1) if m else None
            if not video_id:
                continue
            out.append(
                {
                    "external_id": video_id,
                    "title": getattr(entry, "title", None),
                    "author": getattr(entry, "author", None) or getattr(feed.feed, "title", None),
                    "published_at_ms": _published_at_ms(entry),
                    "duration_seconds": None,
                    "thumbnail": _episode_thumbnail(entry),
                    "source_url": f"https://www.youtube.com/watch?v={video_id}",
                    "audio_url": None,
                    "description": getattr(entry, "summary", None),
                }
            )
        else:  # podcast_feed
            audio_url = _episode_audio(entry)
            if not audio_url:
                continue
            guid = getattr(entry, "id", None) or getattr(entry, "guid", None) or audio_url
            duration = _parse_itunes_duration(getattr(entry, "itunes_duration", "") or "")
            out.append(
                {
                    "external_id": str(guid),
                    "title": getattr(entry, "title", None),
                    "author": getattr(feed.feed, "title", None),
                    "published_at_ms": _published_at_ms(entry),
                    "duration_seconds": duration,
                    "thumbnail": _episode_thumbnail(entry),
                    "source_url": getattr(entry, "link", None) or audio_url,
                    "audio_url": audio_url,
                    "description": getattr(entry, "summary", None),
                }
            )
    return out


def fetch_feed_metadata(feed_url: str) -> dict[str, str | None]:
    """Return {'title', 'image_url'} for a feed. Used at subscription
    creation time so we have something nicer than the raw RSS URL to
    display."""
    feed = feedparser.parse(feed_url)
    title = getattr(feed.feed, "title", None) or None
    image_url: str | None = None
    image_attr = getattr(feed.feed, "image", None)
    if isinstance(image_attr, dict):
        image_url = image_attr.get("href") or image_attr.get("url")
    if not image_url:
        itunes_image = getattr(feed.feed, "itunes_image", None)
        if isinstance(itunes_image, dict):
            image_url = itunes_image.get("href")
    return {"title": title, "image_url": image_url}


def _published_at_ms(entry: feedparser.FeedParserDict) -> int | None:
    pub_parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if pub_parsed is None:
        return None
    import calendar

    return calendar.timegm(pub_parsed) * 1000
