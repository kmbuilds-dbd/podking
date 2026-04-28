"""TranscriptAPI client (transcriptapi.com).

Hosted captions/transcript service that fetches YouTube transcripts from
their own residential infrastructure, bypassing YouTube's "Sign in to
confirm you're not a bot" check that blocks datacenter IPs (Railway,
AWS, GCP). Used as the preferred captions path on cloud hosts; left
unconfigured (TRANSCRIPT_API_KEY blank) once running on a residential
IP, in which case the worker falls back to yt-dlp.
"""
from __future__ import annotations

from typing import Any

import httpx

ENDPOINT = "https://transcriptapi.com/api/v2/youtube/transcript"


class TranscriptApiError(RuntimeError):
    pass


async def fetch(video_url_or_id: str, api_key: str) -> dict[str, Any]:
    """Fetch a transcript + minimal metadata in one call.

    Returns:
        {
          "title": str,
          "author": str,
          "duration_seconds": int,
          "thumbnail_url": str,
          "transcript_text": str,
          "segments": list[dict],
        }

    Raises TranscriptApiError on HTTP errors or when the video has no
    captions (empty `segments`).
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            ENDPOINT,
            params={
                "video_url": video_url_or_id,
                "format": "json",
                "include_timestamp": "true",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    if resp.status_code != 200:
        raise TranscriptApiError(
            f"TranscriptAPI {resp.status_code}: {resp.text[:300]}"
        )

    data: dict[str, Any] = resp.json()
    segments = data.get("segments") or []
    if not segments:
        raise TranscriptApiError("No captions available for this video")

    transcript_text = " ".join(
        str(seg.get("text", "")) for seg in segments
    ).strip()

    raw_duration = data.get("duration")
    duration_seconds = int(float(raw_duration)) if raw_duration is not None else 0

    return {
        "title": str(data.get("title") or ""),
        # The exact field name for uploader varies across providers; check
        # the obvious aliases and fall back to empty.
        "author": str(
            data.get("channel")
            or data.get("uploader")
            or data.get("author")
            or ""
        ),
        "duration_seconds": duration_seconds,
        "thumbnail_url": str(
            data.get("thumbnail") or data.get("thumbnail_url") or ""
        ),
        "transcript_text": transcript_text,
        "segments": segments,
    }
