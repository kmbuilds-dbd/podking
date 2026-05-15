from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import AudioEpisode, User
from podking.schemas import AudioEpisodeResponse

router = APIRouter(prefix="/api")


@router.get("/audio_episodes", response_model=list[AudioEpisodeResponse])
async def list_audio_episodes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[AudioEpisodeResponse]:
    result = await db.execute(
        select(AudioEpisode)
        .where(AudioEpisode.user_id == user.id, AudioEpisode.archived_at.is_(None))
        .order_by(AudioEpisode.created_at.desc())
    )
    return [AudioEpisodeResponse.model_validate(r) for r in result.scalars()]


@router.get("/audio_episodes/{audio_id}", response_model=AudioEpisodeResponse)
async def get_audio_episode(
    audio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> AudioEpisodeResponse:
    row = await db.get(AudioEpisode, audio_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="audio episode not found")
    return AudioEpisodeResponse.model_validate(row)
