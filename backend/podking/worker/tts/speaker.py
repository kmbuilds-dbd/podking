"""Stage 2 — ElevenLabs TTS per segment, then pydub stitching."""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from podking.worker.tts.scripter import ScriptSegment

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
OUTPUT_FORMAT = "mp3_44100_128"
SILENCE_MS = 300
FADE_IN_MS = 500
FADE_OUT_MS = 1000
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


class SpeakerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SynthesisResult:
    path: Path
    duration_sec: int
    size_bytes: int


def _check_ffmpeg() -> None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise FileNotFoundError
    except FileNotFoundError as exc:
        raise SpeakerError(
            "ffmpeg is required for audio stitching. "
            "Install via `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)."
        ) from exc


async def synthesize(
    *,
    segments: list[ScriptSegment],
    voice_a_id: str,
    voice_b_id: str,
    api_key: str,
    model_id: str,
    out_path: Path,
) -> SynthesisResult:
    """Synthesize each segment via ElevenLabs and stitch into one MP3 at `out_path`.

    Stitches with 300ms silence between segments, 500ms fade-in, 1000ms fade-out.
    Raises `SpeakerError` with a typed message on auth/voice/quota/network failures.
    """
    await asyncio.to_thread(_check_ffmpeg)

    voice_map = {"A": voice_a_id, "B": voice_b_id}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        chunk_paths: list[Path] = []
        async with httpx.AsyncClient(timeout=120) as client:
            for i, seg in enumerate(segments):
                voice_id = voice_map[seg.speaker]
                try:
                    resp = await client.post(
                        TTS_URL.format(voice_id=voice_id),
                        params={"output_format": OUTPUT_FORMAT},
                        headers={
                            "xi-api-key": api_key,
                            "Content-Type": "application/json",
                            "Accept": "audio/mpeg",
                        },
                        json={
                            "text": seg.text,
                            "model_id": model_id,
                            "voice_settings": DEFAULT_VOICE_SETTINGS,
                        },
                    )
                except httpx.RequestError as exc:
                    raise SpeakerError(
                        f"ElevenLabs request failed at segment {i+1}/{len(segments)}: {exc}"
                    ) from exc
                if resp.status_code == 401:
                    raise SpeakerError("ElevenLabs key invalid (401)")
                if resp.status_code == 404 or (
                    resp.status_code == 400 and "voice_not_found" in resp.text
                ):
                    raise SpeakerError(
                        f"ElevenLabs voice {voice_id!r} not found. "
                        "Update your voice IDs in Settings or remove them to use server defaults."
                    )
                if resp.status_code == 429 or (
                    resp.status_code >= 400 and "quota" in resp.text.lower()
                ):
                    raise SpeakerError(
                        f"ElevenLabs quota exceeded after {i} of {len(segments)} segments. "
                        "Wait for monthly reset or upgrade your ElevenLabs plan."
                    )
                if resp.status_code >= 400:
                    raise SpeakerError(
                        f"ElevenLabs TTS {resp.status_code}: {resp.text[:300]}"
                    )
                chunk_path = tmp_dir / f"chunk_{i:04d}.mp3"
                chunk_path.write_bytes(resp.content)
                chunk_paths.append(chunk_path)

        return await asyncio.to_thread(_stitch_to_disk, chunk_paths, out_path)


def _stitch_to_disk(chunk_paths: list[Path], out_path: Path) -> SynthesisResult:
    from pydub import AudioSegment

    silence = AudioSegment.silent(duration=SILENCE_MS)
    combined = AudioSegment.empty()
    for i, p in enumerate(chunk_paths):
        if i > 0:
            combined += silence
        combined += AudioSegment.from_mp3(str(p))
    combined = combined.fade_in(FADE_IN_MS).fade_out(FADE_OUT_MS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(out_path), format="mp3", bitrate="128k")

    duration_sec = int(round(len(combined) / 1000))
    size_bytes = out_path.stat().st_size
    return SynthesisResult(path=out_path, duration_sec=duration_sec, size_bytes=size_bytes)
