from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from podking.models import User, UserSettings


async def upsert_user_from_google(
    session: AsyncSession,
    *,
    google_sub: str,
    email: str,
    display_name: str | None,
) -> User:
    result = await session.execute(
        select(User)
        .options(selectinload(User.settings))
        .where(User.google_sub == google_sub)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            google_sub=google_sub,
            email=email,
            display_name=display_name,
            settings=UserSettings(system_prompt=""),
        )
        session.add(user)
        await session.flush()
        return user
    user.email = email
    user.display_name = display_name
    return user
