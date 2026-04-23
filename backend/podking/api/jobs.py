from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import Episode, Job, Transcript, User
from podking.schemas import JobCreate, JobResponse, ResumamarizeCreate

router = APIRouter(prefix="/api")


def _detect_kind(url: str) -> str:
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "podcasts.apple.com" in lower or "apple.com/podcast" in lower:
        return "podcast"
    raise ValueError(f"Unsupported URL: {url}")


def _job_response(job: Job) -> JobResponse:
    return JobResponse.model_validate(job)


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

    job = Job(
        user_id=user.id,
        kind=kind,
        source_url=body.source_url,
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

    job = Job(
        user_id=user.id,
        kind="resummarize",
        episode_id=body.episode_id,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_response(job)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[JobResponse]:
    result = await db.execute(
        select(Job)
        .where(Job.user_id == user.id)
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
    job = await db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_response(job)


async def mark_interrupted_jobs_failed(db: AsyncSession) -> None:
    """Called on startup: any non-terminal, non-queued job was interrupted."""
    await db.execute(
        update(Job)
        .where(
            Job.status.in_(["fetching", "transcribing", "summarizing", "embedding"])
        )
        .values(
            status="failed",
            error="interrupted by restart",
            finished_at=datetime.now(UTC),
        )
    )
    await db.commit()
