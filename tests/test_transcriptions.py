from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from httpx import AsyncClient
from podking.crypto import encrypt
from podking.db import get_sessionmaker
from podking.models import Job, Transcription, User, UserSettings
from podking.worker import elevenlabs_client, runner
from sqlalchemy import select


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("meeting.mp3", "audio/mpeg"), ("meeting.mp4", "video/mp4"), ("meeting.wav", "audio/wav")],
)
async def test_upload_creates_queued_transcription_and_job(
    seeded_client: AsyncClient,
    filename: str,
    content_type: str,
) -> None:
    response = await seeded_client.post(
        "/api/transcriptions",
        files={"file": (filename, b"audio", content_type)},
        data={"description": "A meeting recording"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == filename
    assert body["mime_type"] == content_type
    assert body["description"] == "A meeting recording"
    assert body["status"] == "queued"
    assert body["transcript_text"] is None
    assert body["job_id"]


async def test_upload_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/transcriptions",
        files={"file": ("meeting.mp3", b"audio", "audio/mpeg")},
    )
    assert response.status_code == 401


async def test_upload_requires_supported_nonempty_file(
    seeded_client: AsyncClient,
) -> None:
    unsupported = await seeded_client.post(
        "/api/transcriptions",
        files={"file": ("notes.txt", b"text", "text/plain")},
    )
    assert unsupported.status_code == 400

    empty = await seeded_client.post(
        "/api/transcriptions",
        files={"file": ("empty.mp3", b"", "audio/mpeg")},
    )
    assert empty.status_code == 400


async def test_transcription_download_returns_text_attachment(
    seeded_client: AsyncClient,
    tmp_path: Path,
) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        user = (await db.execute(select(User))).scalar_one()
        transcription = Transcription(
            user_id=user.id,
            original_filename="../../interview.mp4",
            description="Customer interview",
            mime_type="video/mp4",
            audio_path=str(tmp_path / "interview.mp4"),
            transcript_text="Hello from the recording.",
        )
        db.add(transcription)
        await db.flush()
        db.add(Job(
            user_id=user.id,
            kind="transcription",
            transcription_id=transcription.id,
            status="done",
            progress_pct=100,
            progress_message="Done",
        ))
        await db.commit()
        transcription_id = transcription.id

    response = await seeded_client.get(f"/api/transcriptions/{transcription_id}/download")

    assert response.status_code == 200
    assert response.text == "Hello from the recording."
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"].endswith(
        f'{transcription_id}-interview.txt"'
    )


async def test_transcription_download_is_scoped_to_owner(
    seeded_client: AsyncClient,
) -> None:
    sm = get_sessionmaker()
    async with sm() as db:
        owner = (await db.execute(select(User))).scalar_one()
        other = User(email="other@example.com", google_sub="other")
        db.add(other)
        await db.flush()
        transcription = Transcription(
            user_id=other.id,
            original_filename="private.mp3",
            description=None,
            mime_type="audio/mpeg",
            audio_path="/tmp/private.mp3",
            transcript_text="Private text",
        )
        db.add(transcription)
        await db.flush()
        db.add(Job(
            user_id=other.id,
            kind="transcription",
            transcription_id=transcription.id,
            status="done",
            progress_pct=100,
        ))
        await db.commit()
        transcription_id = transcription.id
        assert owner.id != other.id

    response = await seeded_client.get(f"/api/transcriptions/{transcription_id}/download")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_transcription_worker_persists_scribe_result(
    engine,
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "recording.wav"
    audio_path.write_bytes(b"RIFF test")

    sm = get_sessionmaker()
    async with sm() as db:
        user = User(email="worker@example.com", google_sub="worker")
        db.add(user)
        await db.flush()
        db.add(UserSettings(
            user_id=user.id,
            system_prompt="",
            elevenlabs_api_key_encrypted=encrypt("sk-eleven"),
        ))
        transcription = Transcription(
            user_id=user.id,
            original_filename="recording.wav",
            description="Interview",
            mime_type="audio/wav",
            audio_path=str(audio_path),
        )
        db.add(transcription)
        await db.flush()
        job = Job(
            user_id=user.id,
            kind="transcription",
            transcription_id=transcription.id,
            status="queued",
        )
        db.add(job)
        await db.commit()
        job_id = job.id
        transcription_id = transcription.id

    async def fake_transcribe(
        path: Path,
        api_key: str,
        content_type: str = "audio/mpeg",
    ) -> dict[str, object]:
        assert path == audio_path
        assert api_key == "sk-eleven"
        assert content_type == "audio/wav"
        return {"text": "A real transcript.", "segments": [{"text": "A real transcript."}]}

    monkeypatch.setattr(elevenlabs_client, "transcribe", fake_transcribe)
    await runner._process_next_job()

    async with sm() as db:
        job = await db.get(Job, job_id)
        transcription = await db.get(Transcription, transcription_id)
        assert job is not None and job.status == "done"
        assert transcription is not None
        assert transcription.transcript_text == "A real transcript."
        assert transcription.segments == [{"text": "A real transcript."}]


@pytest.mark.asyncio
async def test_elevenlabs_client_sends_uploaded_mime_type(tmp_path: Path) -> None:
    audio_path = tmp_path / "recording.mp4"
    audio_path.write_bytes(b"mp4")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(elevenlabs_client.SCRIBE_URL).mock(
            return_value=httpx.Response(200, json={"text": "Transcript"})
        )
        result = await elevenlabs_client.transcribe(
            audio_path,
            "sk-eleven",
            content_type="video/mp4",
        )

    assert route.called
    assert b"Content-Type: video/mp4" in route.calls[0].request.content
    assert result["text"] == "Transcript"
