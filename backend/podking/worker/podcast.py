"""Podcast helpers: Apple Podcast URL resolution + audio download."""
from __future__ import annotations

import re
from pathlib import Path

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


async def download_audio(enclosure_url: str, output_path: Path) -> None:
    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        async with client.stream("GET", enclosure_url) as resp:
            resp.raise_for_status()
            with output_path.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise PodcastError(f"Audio download failed from {enclosure_url}")
