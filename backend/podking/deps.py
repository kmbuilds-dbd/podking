import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.db import get_sessionmaker
from podking.models import User


async def get_db() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session


async def current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    raw = request.session.get("user_id")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    try:
        user_id = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session"
        ) from None
    result = await db.execute(
        select(User).options(selectinload(User.settings)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found"
        )
    return user
