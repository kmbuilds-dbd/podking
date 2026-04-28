"""Probe youtube-transcript-api against a YouTube video.

Hits a different YouTube endpoint than yt-dlp's player config, so it may
or may not be blocked on Railway's IPs. Run this from BOTH your local
machine and the Railway environment to compare.

Usage:
    uv run --with youtube-transcript-api python scripts/probe_transcript_api.py
    uv run --with youtube-transcript-api python scripts/probe_transcript_api.py <video_id_or_url>

If it succeeds where yt-dlp fails, this could replace the captions path
(probe_captions + download_captions in worker/youtube.py) and skip the
bot-check entirely for caption-bearing videos. It would NOT replace the
metadata fetch, the audio fallback, or anything for videos without
captions.
"""
from __future__ import annotations

import re
import sys
import traceback

DEFAULT_VIDEO = "yZ7VVrFGdSk"  # the video that's been failing


def extract_id(s: str) -> str:
    for pat in (
        r"youtube\.com/watch\?v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"youtube\.com/shorts/([\w-]{11})",
    ):
        m = re.search(pat, s)
        if m:
            return m.group(1)
    if re.fullmatch(r"[\w-]{11}", s):
        return s
    raise ValueError(f"Cannot extract video id from {s!r}")


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO
    video_id = extract_id(arg)
    print(f"video_id: {video_id}")

    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()

    # 1) List available transcripts (manual vs auto-generated, languages).
    try:
        listing = api.list(video_id)
    except Exception:
        print("\nlist() failed:")
        traceback.print_exc()
        return 1

    print("\nAvailable transcripts:")
    for t in listing:
        kind = "auto" if t.is_generated else "manual"
        translatable = "translatable" if t.is_translatable else "fixed"
        print(f"  - {t.language_code:8s} ({kind}, {translatable})")

    # 2) Fetch the preferred English transcript (or first available).
    try:
        fetched = api.fetch(video_id, languages=["en"])
    except Exception:
        print("\nfetch() failed:")
        traceback.print_exc()
        return 1

    snippets = list(fetched)
    full_text = " ".join(s.text for s in snippets)

    print(f"\nFetched: {len(snippets)} segments, {len(full_text)} chars")
    print(f"First 300 chars: {full_text[:300]!r}")
    print(f"Last 100 chars:  {full_text[-100:]!r}")
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
