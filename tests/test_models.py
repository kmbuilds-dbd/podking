import uuid

import pytest
from podking.models import Base, User, UserSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_create_user_with_settings(migrated_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u = User(
            id=uuid.uuid4(),
            email="test@example.com",
            google_sub="sub-123",
            display_name="Test",
        )
        u.settings = UserSettings(system_prompt="Summarize this.")
        session.add(u)
        await session.commit()

        loaded = (
            await session.execute(
                select(User).where(User.email == "test@example.com")
            )
        ).scalar_one()
        assert loaded.google_sub == "sub-123"
        assert loaded.settings is not None
        assert loaded.settings.system_prompt == "Summarize this."
