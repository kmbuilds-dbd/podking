"""Listen Notes API client.

Wraps the subset of https://listen-api.listennotes.com/api/v2 that we need:
podcast search and podcast detail (for episode resolution).

Free-tier note: the `rss` and `email` fields are gated to PRO/ENTERPRISE.
We never depend on `rss` from this client; subscriptions still resolve
RSS via iTunes Search elsewhere.
"""
from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://listen-api.listennotes.com/api/v2"


class ListenNotesError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise ListenNotesError("LISTEN_NOTES_API_KEY is not configured")
    return {"X-ListenAPI-Key": api_key}


async def search_podcasts(
    api_key: str, q: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Search podcasts by keyword. Returns a list of result dicts with at
    least: id, title_original, publisher_original, description_original,
    image, thumbnail, itunes_id, total_episodes, listennotes_url."""
    if not q.strip():
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/search",
            headers=_headers(api_key),
            params={"q": q, "type": "podcast", "page_size": limit},
        )
    if resp.status_code != 200:
        raise ListenNotesError(
            f"Listen Notes search failed ({resp.status_code}): {resp.text[:200]}"
        )
    data = resp.json()
    return list(data.get("results", []))[:limit]


async def get_podcast_by_id(
    api_key: str, listen_notes_id: str, sort: str = "recent_first"
) -> dict[str, Any]:
    """Fetch full podcast metadata (with up to 10 recent episodes) by Listen
    Notes podcast ID. Each episode dict includes `audio` (direct URL),
    `audio_length_sec`, `guid_from_rss`, `pub_date_ms`, `title`, `description`."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/podcasts/{listen_notes_id}",
            headers=_headers(api_key),
            params={"sort": sort},
        )
    if resp.status_code == 404:
        raise ListenNotesError(f"Listen Notes podcast not found: {listen_notes_id}")
    if resp.status_code != 200:
        raise ListenNotesError(
            f"Listen Notes podcast lookup failed ({resp.status_code}): {resp.text[:200]}"
        )
    return resp.json()  # type: ignore[no-any-return]


async def find_podcast_by_itunes_id(
    api_key: str, itunes_id: int
) -> dict[str, Any] | None:
    """Look up a Listen Notes podcast by its Apple/iTunes ID. Returns the
    podcast dict (with episodes) or None if not indexed."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{BASE_URL}/podcasts",
            headers=_headers(api_key),
            params={"itunes_ids": str(itunes_id)},
        )
    if resp.status_code != 200:
        raise ListenNotesError(
            f"Listen Notes itunes-id lookup failed ({resp.status_code}): "
            f"{resp.text[:200]}"
        )
    podcasts = resp.json().get("podcasts") or []
    if not podcasts:
        return None
    listen_notes_id = podcasts[0].get("id")
    if not listen_notes_id:
        return None
    return await get_podcast_by_id(api_key, listen_notes_id)
