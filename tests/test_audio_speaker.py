from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response

from podking.worker.tts.scripter import ScriptSegment
from podking.worker.tts.speaker import (
    SpeakerError,
    synthesize,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _silent_mp3_bytes(ms: int) -> bytes:
    """Generate a tiny silent MP3 of `ms` milliseconds for stubbing."""
    from pydub import AudioSegment
    s = AudioSegment.silent(duration=ms, frame_rate=44100)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    buf = FIXTURES / "_tmp.mp3"
    s.export(str(buf), format="mp3", bitrate="128k")
    data = buf.read_bytes()
    buf.unlink()
    return data


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_stitches_segments(tmp_path: Path) -> None:
    chunk_a = _silent_mp3_bytes(500)
    chunk_b = _silent_mp3_bytes(700)

    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceA").mock(
        return_value=Response(200, content=chunk_a)
    )
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceB").mock(
        return_value=Response(200, content=chunk_b)
    )

    segments = [
        ScriptSegment(speaker="A", text="hi"),
        ScriptSegment(speaker="B", text="hello"),
    ]
    out = tmp_path / "ep.mp3"
    result = await synthesize(
        segments=segments,
        voice_a_id="voiceA",
        voice_b_id="voiceB",
        api_key="sk-eleven",
        model_id="eleven_turbo_v2_5",
        out_path=out,
    )

    assert result.path == out
    assert out.exists() and out.stat().st_size > 0
    assert result.duration_sec >= 1
    assert result.size_bytes == out.stat().st_size


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_401_raises_key_invalid(tmp_path: Path) -> None:
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceA").mock(
        return_value=Response(401, text="bad key")
    )
    with pytest.raises(SpeakerError, match="ElevenLabs key invalid"):
        await synthesize(
            segments=[ScriptSegment(speaker="A", text="hi")],
            voice_a_id="voiceA",
            voice_b_id="voiceB",
            api_key="sk-bad",
            model_id="eleven_turbo_v2_5",
            out_path=tmp_path / "out.mp3",
        )


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_quota_after_partial_progress(tmp_path: Path) -> None:
    chunk = _silent_mp3_bytes(400)
    respx.post("https://api.elevenlabs.io/v1/text-to-speech/voiceA").mock(
        side_effect=[
            Response(200, content=chunk),
            Response(429, text='{"detail":"quota_exceeded"}'),
        ]
    )
    with pytest.raises(SpeakerError, match="quota"):
        await synthesize(
            segments=[
                ScriptSegment(speaker="A", text="one"),
                ScriptSegment(speaker="A", text="two"),
            ],
            voice_a_id="voiceA",
            voice_b_id="voiceB",
            api_key="sk-fake",
            model_id="eleven_turbo_v2_5",
            out_path=tmp_path / "out.mp3",
        )
