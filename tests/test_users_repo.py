import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from podking.models import Base
from podking.repositories.users import upsert_user_from_google


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_upsert_creates_user_with_empty_settings(migrated_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        user = await upsert_user_from_google(
            session, google_sub="sub-1", email="a@b.com", display_name="Alice"
        )
        await session.commit()
        assert isinstance(user.id, uuid.UUID)
        assert user.settings is not None
        assert user.settings.system_prompt == ""


@pytest.mark.asyncio
async def test_upsert_returns_existing_user(migrated_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u1 = await upsert_user_from_google(
            session, google_sub="sub-2", email="a@b.com", display_name="A"
        )
        await session.commit()
        u1_id = u1.id
    async with sm() as session:
        u2 = await upsert_user_from_google(
            session, google_sub="sub-2", email="a@b.com", display_name="A updated"
        )
        await session.commit()
        assert u2.id == u1_id
        assert u2.display_name == "A updated"
