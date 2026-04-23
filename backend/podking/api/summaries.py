from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.deps import current_user, get_db
from podking.models import Episode, Summary, SummaryTag, Tag, Transcript, User
from podking.schemas import (
    EpisodeResponse,
    SummaryResponse,
    SummaryTagResponse,
    TagPatch,
    TranscriptResponse,
)

router = APIRouter(prefix="/api")


def _build_summary_response(summary: Summary) -> SummaryResponse:
    tags = [
        SummaryTagResponse(name=st.tag.name, source=st.source)
        for st in summary.summary_tags
    ]
    return SummaryResponse(
        id=summary.id,
        episode=EpisodeResponse.model_validate(summary.episode),
        system_prompt=summary.system_prompt,
        model=summary.model,
        content=summary.content,
        tags=tags,
        created_at=summary.created_at,
    )


def _summary_query(user_id: uuid.UUID) -> Select[tuple[Summary]]:
    return (
        select(Summary)
        .where(Summary.user_id == user_id)
        .options(
            selectinload(Summary.episode),
            selectinload(Summary.summary_tags).selectinload(SummaryTag.tag),
        )
    )


@router.get("/summaries", response_model=list[SummaryResponse])
async def list_summaries(
    limit: int = Query(default=20, le=100),
    cursor: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[SummaryResponse]:
    q = _summary_query(user.id).order_by(Summary.created_at.desc()).limit(limit)

    if cursor:
        try:
            cursor_id = uuid.UUID(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid cursor") from None
        cursor_summary = await db.get(Summary, cursor_id)
        if cursor_summary:
            q = q.where(Summary.created_at < cursor_summary.created_at)

    if tag:
        q = q.join(SummaryTag, SummaryTag.summary_id == Summary.id).join(
            Tag, Tag.id == SummaryTag.tag_id
        ).where(Tag.name == tag, Tag.user_id == user.id)

    result = await db.execute(q)
    return [_build_summary_response(s) for s in result.scalars()]


@router.get("/summaries/{summary_id}", response_model=SummaryResponse)
async def get_summary(
    summary_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SummaryResponse:
    result = await db.execute(
        _summary_query(user.id).where(Summary.id == summary_id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="summary not found")
    return _build_summary_response(summary)


@router.delete("/summaries/{summary_id}", status_code=204)
async def delete_summary(
    summary_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    summary = await db.get(Summary, summary_id)
    if summary is None or summary.user_id != user.id:
        raise HTTPException(status_code=404, detail="summary not found")
    await db.delete(summary)
    await db.commit()


@router.get("/episodes/{episode_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    episode_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> TranscriptResponse:
    episode = await db.get(Episode, episode_id)
    if episode is None or episode.user_id != user.id:
        raise HTTPException(status_code=404, detail="episode not found")
    result = await db.execute(
        select(Transcript).where(Transcript.episode_id == episode_id)
    )
    transcript = result.scalar_one_or_none()
    if transcript is None:
        raise HTTPException(status_code=404, detail="transcript not found")
    return TranscriptResponse.model_validate(transcript)


@router.post("/summaries/{summary_id}/tags", response_model=SummaryResponse)
async def patch_summary_tags(
    summary_id: uuid.UUID,
    body: TagPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> SummaryResponse:
    result = await db.execute(
        _summary_query(user.id).where(Summary.id == summary_id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="summary not found")

    for name in body.remove:
        tag_result = await db.execute(
            select(Tag).where(Tag.user_id == user.id, Tag.name == name)
        )
        tag = tag_result.scalar_one_or_none()
        if tag:
            st_result = await db.execute(
                select(SummaryTag).where(
                    SummaryTag.summary_id == summary_id,
                    SummaryTag.tag_id == tag.id,
                )
            )
            st = st_result.scalar_one_or_none()
            if st:
                await db.delete(st)

    for name in body.add:
        tag_result = await db.execute(
            select(Tag).where(Tag.user_id == user.id, Tag.name == name)
        )
        tag = tag_result.scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=user.id, name=name)
            db.add(tag)
            await db.flush()

        st_result = await db.execute(
            select(SummaryTag).where(
                SummaryTag.summary_id == summary_id,
                SummaryTag.tag_id == tag.id,
            )
        )
        if st_result.scalar_one_or_none() is None:
            db.add(SummaryTag(summary_id=summary_id, tag_id=tag.id, source="user"))

    await db.commit()
    # Reload with fresh data
    result2 = await db.execute(
        _summary_query(user.id).where(Summary.id == summary_id)
    )
    return _build_summary_response(result2.scalar_one())
