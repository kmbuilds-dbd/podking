from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.deps import current_user, get_db
from podking.models import (
    Episode,
    Job,
    PromptStyle,
    Subscription,
    Summary,
    Transcript,
    Transcription,
    User,
)
from podking.prompt_styles import ensure_general_prompt_style
from podking.schemas import (
    JobCreate,
    JobEpisodeMini,
    JobPatch,
    JobResponse,
    ResumamarizeCreate,
)

router = APIRouter(prefix="/api")


def _detect_kind(url: str) -> str:
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "podcasts.apple.com" in lower or "apple.com/podcast" in lower:
        return "podcast"
    raise ValueError(f"Unsupported URL: {url}")


def _job_response(job: Job) -> JobResponse:
    episode_mini: JobEpisodeMini | None = None
    if job.episode is not None:
        episode_mini = JobEpisodeMini.model_validate(job.episode)
    return JobResponse(
        id=job.id,
        kind=job.kind,
        source_url=job.source_url,
        episode_id=job.episode_id,
        transcription_id=job.transcription_id,
        episode=episode_mini,
        status=job.status,
        progress_pct=job.progress_pct,
        progress_message=job.progress_message,
        error=job.error,
        archived=job.archived_at is not None,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    try:
        kind = _detect_kind(body.source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    general = await ensure_general_prompt_style(db, user.id)
    job = Job(
        user_id=user.id,
        kind=kind,
        source_url=body.source_url,
        analysis_prompt=general.prompt_text,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_response(job)


@router.post("/jobs/resummarize", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_resummarize_job(
    body: ResumamarizeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    episode = await db.get(Episode, body.episode_id)
    if episode is None or episode.user_id != user.id:
        raise HTTPException(status_code=404, detail="episode not found")

    result = await db.execute(
        select(Transcript).where(Transcript.episode_id == body.episode_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="no transcript available for this episode")

    # If the episode came from a subscription, use the subscription's CURRENT
    # analysis style so style edits/assignments apply on re-summarize. Fall
    # back to the previous summary's prompt (or general) for standalone
    # episodes that have no subscription context.
    analysis_prompt: str | None = None
    if episode.subscription_id is not None:
        subscription = await db.get(Subscription, episode.subscription_id)
        if subscription is not None and subscription.user_id == user.id:
            style = await db.get(PromptStyle, subscription.prompt_style_id)
            if style is not None:
                analysis_prompt = style.prompt_text

    if analysis_prompt is None:
        summary = await db.scalar(
            select(Summary)
            .where(
                Summary.episode_id == body.episode_id,
                Summary.user_id == user.id,
            )
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        if summary is not None:
            analysis_prompt = summary.system_prompt
        else:
            general = await ensure_general_prompt_style(db, user.id)
            analysis_prompt = general.prompt_text
    job = Job(
        user_id=user.id,
        kind="resummarize",
        episode_id=body.episode_id,
        analysis_prompt=analysis_prompt,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_response(job)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[JobResponse]:
    archive_filter = (
        Job.archived_at.is_not(None) if archived else Job.archived_at.is_(None)
    )
    result = await db.execute(
        select(Job)
        .where(Job.user_id == user.id, archive_filter)
        .options(selectinload(Job.episode))
        .order_by(Job.created_at.desc())
        .limit(100)
    )
    return [_job_response(j) for j in result.scalars()]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.episode))
    )
    job = result.scalar_one_or_none()
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_response(job)


@router.patch("/jobs/{job_id}", response_model=JobResponse)
async def patch_job(
    job_id: uuid.UUID,
    body: JobPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.episode))
    )
    job = result.scalar_one_or_none()
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    job.archived_at = datetime.now(UTC) if body.archived else None
    await db.commit()
    await db.refresh(job)
    return _job_response(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    job = await db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")

    if job.episode_id is not None:
        episode = await db.get(Episode, job.episode_id)
        if episode is not None and episode.user_id == user.id:
            if episode.audio_path:
                Path(episode.audio_path).unlink(missing_ok=True)
            await db.delete(episode)  # cascades transcript, summaries, summary_tags

    if job.transcription_id is not None:
        transcription = await db.get(Transcription, job.transcription_id)
        if transcription is not None and transcription.user_id == user.id:
            Path(transcription.audio_path).unlink(missing_ok=True)
            await db.delete(transcription)

    await db.delete(job)
    await db.commit()


async def mark_interrupted_jobs_failed(db: AsyncSession) -> None:
    """Called on startup: any non-terminal, non-queued job was interrupted.
    Auto-archive these so they don't clutter the active list."""
    now = datetime.now(UTC)
    await db.execute(
        update(Job)
        .where(
            Job.status.in_([
                "fetching",
                "transcribing",
                "summarizing",
                "embedding",
                "scripting",
                "speaking",
                "publishing",
            ])
        )
        .values(
            status="failed",
            error="interrupted by restart",
            finished_at=now,
            archived_at=now,
        )
    )
    await db.commit()
