from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from podking.db import get_sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
