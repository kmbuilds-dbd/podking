from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from podking.deps import current_user, get_db
from podking.models import SummaryTag, Tag, User
from podking.schemas import TagResponse

router = APIRouter(prefix="/api")


@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[TagResponse]:
    cnt = func.count(SummaryTag.tag_id).label("cnt")
    result = await db.execute(
        select(Tag, cnt)
        .outerjoin(SummaryTag, SummaryTag.tag_id == Tag.id)
        .where(Tag.user_id == user.id)
        .group_by(Tag.id)
        .order_by(cnt.desc(), Tag.name)
    )
    return [
        TagResponse(id=tag.id, name=tag.name, count=count)
        for tag, count in result.tuples()
    ]
