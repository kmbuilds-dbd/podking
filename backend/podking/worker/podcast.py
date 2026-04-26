"""Podcast helpers: Apple Podcast URL resolution + audio download."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import feedparser
import httpx


class PodcastError(RuntimeError):
    pass


def parse_apple_podcast_ids(url: str) -> tuple[str, str]:
    """Return (podcast_id, episode_id) from an Apple Podcasts URL.

    URL forms:
      https://podcasts.apple.com/{country}/podcast/{slug}/id{id}?i={episode_id}
    """
    podcast_m = re.search(r"/id(\d+)", url)
    episode_m = re.search(r"[?&]i=(\d+)", url)
    if not podcast_m or not episode_m:
        raise PodcastError(
            "Cannot parse Apple Podcast URL — expected /id{podcast_id}?i={episode_id}"
        )
    return podcast_m.group(1), episode_m.group(1)


async def resolve_feed_url(podcast_id: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://itunes.apple.com/lookup?id={podcast_id}",
            timeout=15,
        )
    if resp.status_code == 404:
        raise PodcastError(f"Apple Podcast ID {podcast_id} not found")
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise PodcastError(f"No results for Apple Podcast ID {podcast_id}")
    feed_url = results[0].get("feedUrl")
    if not feed_url:
        raise PodcastError(f"No feedUrl for Apple Podcast ID {podcast_id}")
    return str(feed_url)


def find_episode_in_feed(
    feed: feedparser.FeedParserDict, episode_id: str
) -> feedparser.FeedParserDict | None:
    for entry in feed.entries:
        guid = getattr(entry, "id", None) or getattr(entry, "guid", None) or ""
        itunes_guid = getattr(entry, "itunes_episodeguid", None) or ""
        if episode_id in (guid, itunes_guid, guid.split("/")[-1], itunes_guid.split("/")[-1]):
            return entry
    return None


def _normalize_title(s: str) -> str:
    """Lowercase, strip non-alphanumerics. For fuzzy title matching across
    Apple's display title and RSS feed titles which sometimes differ in
    smart-quotes, em-dashes, or trailing prefixes/suffixes."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def find_episode_by_title(
    feed: feedparser.FeedParserDict, title: str
) -> feedparser.FeedParserDict | None:
    """Fall back to title matching when guids don't line up between the iTunes
    track ID and the RSS feed's guid (very common — Apple's `?i=` is a track
    ID, not a feed guid)."""
    target = _normalize_title(title)
    if not target:
        return None
    # Exact normalized match wins.
    for entry in feed.entries:
        if _normalize_title(getattr(entry, "title", "") or "") == target:
            return entry
    # Otherwise: substring match (RSS title may have a "Episode N — " prefix).
    for entry in feed.entries:
        ent = _normalize_title(getattr(entry, "title", "") or "")
        if ent and (target in ent or ent in target):
            return entry
    return None


async def fetch_apple_episode_metadata(url: str) -> dict[str, Any]:
    """Scrape an Apple Podcasts episode page for the structured metadata
    Apple injects as JSON-LD. Returns {title, date_published, duration_iso,
    description, thumbnail}. Raises PodcastError on failure."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise PodcastError(f"Apple page fetch failed ({resp.status_code})")
    html = resp.text

    # JSON-LD block of @type=PodcastEpisode
    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    ):
        body = m.group(1).strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "PodcastEpisode":
            return {
                "title": data.get("name"),
                "date_published": data.get("datePublished"),
                "duration_iso": data.get("duration"),
                "description": data.get("description"),
                "thumbnail": data.get("thumbnailUrl"),
            }

    # Fallback: og:title
    og = re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html
    )
    if og:
        return {
            "title": og.group(1),
            "date_published": None,
            "duration_iso": None,
            "description": None,
            "thumbnail": None,
        }
    raise PodcastError("Could not extract episode metadata from Apple page")


async def download_audio(enclosure_url: str, output_path: Path) -> None:
    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        async with client.stream("GET", enclosure_url) as resp:
            resp.raise_for_status()
            with output_path.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise PodcastError(f"Audio download failed from {enclosure_url}")
