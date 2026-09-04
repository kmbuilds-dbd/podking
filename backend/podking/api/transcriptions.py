from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.config import get_settings
from podking.deps import current_user, get_db
from podking.models import Job, Transcription, User
from podking.schemas import TranscriptionResponse

router = APIRouter(prefix="/api")

MAX_PREVIEW_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 500
ALLOWED_MIME_TYPES = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".mp4",
    "video/mp4": ".mp4",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}
ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".wav"}


def _upload_format(file: UploadFile) -> tuple[str, str]:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    mime_type = (file.content_type or "").lower().split(";", 1)[0].strip()
    if extension not in ALLOWED_EXTENSIONS and mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="unsupported audio format; use an mp3, mp4, or wav file",
        )
    if mime_type not in ALLOWED_MIME_TYPES:
        mime_type = {
            ".mp3": "audio/mpeg",
            ".mp4": "audio/mp4",
            ".wav": "audio/wav",
        }[extension]
    if extension not in ALLOWED_EXTENSIONS:
        extension = ALLOWED_MIME_TYPES[mime_type]
    return extension, mime_type


async def _save_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"audio file exceeds the {max_bytes} byte size limit",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="audio file cannot be empty")
    return size


def _response(row: Transcription) -> TranscriptionResponse:
    if row.job is None:
        raise RuntimeError("transcription is missing its job")
    text = row.transcript_text
    job_status = {
        "queued": "queued",
        "fetching": "transcribing",
        "transcribing": "transcribing",
        "done": "done",
        "failed": "failed",
    }.get(row.job.status, "queued")
    return TranscriptionResponse(
        id=row.id,
        job_id=row.job.id,
        original_filename=row.original_filename,
        description=row.description,
        mime_type=row.mime_type,
        status=job_status,
        progress_pct=row.job.progress_pct,
        progress_message=row.job.progress_message,
        transcript_text=text,
        transcript_preview=text[:MAX_PREVIEW_LENGTH] if text is not None else None,
        error=row.job.error or row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


@router.post(
    "/transcriptions",
    response_model=TranscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transcription(
    file: UploadFile | None = File(None),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> TranscriptionResponse:
    if file is None:
        raise HTTPException(status_code=400, detail="file is required")
    extension, mime_type = _upload_format(file)
    if description is not None and len(description.strip()) > MAX_DESCRIPTION_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"description must be {MAX_DESCRIPTION_LENGTH} characters or fewer",
        )
    transcription_id = uuid.uuid4()
    audio_path = (
        Path(get_settings().audio_storage_path)
        / "transcriptions"
        / str(user.id)
        / f"{transcription_id}{extension}"
    )
    await _save_upload(file, audio_path, get_settings().max_transcription_size_bytes)
    try:
        transcription = Transcription(
            id=transcription_id,
            user_id=user.id,
            original_filename=file.filename or f"audio{extension}",
            description=description.strip() if description and description.strip() else None,
            mime_type=mime_type,
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
        await db.refresh(transcription)
        await db.refresh(job)
        transcription.job = job
        return _response(transcription)
    except Exception:
        await db.rollback()
        audio_path.unlink(missing_ok=True)
        raise


@router.get("/transcriptions", response_model=list[TranscriptionResponse])
async def list_transcriptions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[TranscriptionResponse]:
    result = await db.execute(
        select(Transcription)
        .where(Transcription.user_id == user.id)
        .options(selectinload(Transcription.job))
        .order_by(Transcription.created_at.desc())
    )
    return [_response(row) for row in result.scalars()]


def _download_filename(row: Transcription) -> str:
    stem = Path(row.original_filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")[:80] or "transcript"
    return f"{row.id}-{safe_stem}.txt"


@router.get("/transcriptions/{transcription_id}/download")
async def download_transcription(
    transcription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> PlainTextResponse:
    row = await db.scalar(
        select(Transcription)
        .where(
            Transcription.id == transcription_id,
            Transcription.user_id == user.id,
        )
        .options(selectinload(Transcription.job))
    )
    if row is None:
        raise HTTPException(status_code=404, detail="transcription not found")
    if row.job is None or row.job.status != "done" or row.transcript_text is None:
        raise HTTPException(status_code=409, detail="transcription is not complete")
    filename = _download_filename(row)
    return PlainTextResponse(
        row.transcript_text,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
