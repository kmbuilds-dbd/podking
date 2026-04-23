"""ElevenLabs Scribe transcription."""
from __future__ import annotations

from pathlib import Path

import httpx

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabsError(RuntimeError):
    pass


async def transcribe(audio_path: Path, api_key: str) -> dict[str, object]:
    """Return {'text': str, 'segments': list | None}."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=600) as client:
                with audio_path.open("rb") as f:
                    resp = await client.post(
                        SCRIBE_URL,
                        headers={"xi-api-key": api_key},
                        files={"file": (audio_path.name, f, "audio/mpeg")},
                        data={"model_id": "scribe_v1"},
                    )
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                import asyncio
                await asyncio.sleep(2 ** attempt * 2)
                continue
            if resp.status_code >= 400:
                raise ElevenLabsError(
                    f"ElevenLabs {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            return {
                "text": data.get("text", ""),
                "segments": data.get("words") or data.get("segments"),
            }
        except httpx.TransportError:
            if attempt == 2:
                raise
            import asyncio
            await asyncio.sleep(2 ** attempt * 2)
    raise ElevenLabsError("ElevenLabs transcription failed after retries")
