import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://podking:podking@localhost:5432/podking_test",
)


@pytest.fixture(scope="session", autouse=True)
def configure_env() -> Iterator[None]:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["SESSION_SECRET_KEY"] = "test-secret-at-least-32-bytes-long-xxxxx"
    # Fixed Fernet key for determinism in tests; generate real ones per deployment.
    os.environ["FERNET_KEY"] = "g9g_Lr-HRfT7ORu6rcs3RY4g09Mw6Un5WlKT99rkY7o="
    os.environ["ALLOWED_EMAILS"] = "allowed@example.com"
    from podking.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Fresh engine per test with a clean `public` schema and pgvector enabled."""
    from podking.db import get_engine, get_sessionmaker

    get_engine.cache_clear()  # type: ignore[attr-defined]
    get_sessionmaker.cache_clear()  # type: ignore[attr-defined]
    eng = create_async_engine(TEST_DATABASE_URL, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    get_engine.cache_clear()  # type: ignore[attr-defined]
    get_sessionmaker.cache_clear()  # type: ignore[attr-defined]
    yield eng
    await eng.dispose()


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    from podking.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
