from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://podking:podking@localhost:5432/podking_test",
)

_SESSION_SECRET = "test-secret-at-least-32-bytes-long-xxxxx"


@pytest.fixture(scope="session", autouse=True)
def configure_env() -> Iterator[None]:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["SESSION_SECRET_KEY"] = _SESSION_SECRET
    # Fixed Fernet key for determinism in tests; generate real ones per deployment.
    os.environ["FERNET_KEY"] = "g9g_Lr-HRfT7ORu6rcs3RY4g09Mw6Un5WlKT99rkY7o="
    os.environ["ALLOWED_EMAILS"] = "allowed@example.com"
    from podking.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield


def _run_alembic_migrations(sync_url: str) -> None:
    """Run all Alembic migrations synchronously (called from a thread)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Drop/recreate public schema, enable pgvector, run migrations, yield engine."""
    from podking.db import get_engine, get_sessionmaker

    get_engine.cache_clear()  # type: ignore[attr-defined]
    get_sessionmaker.cache_clear()  # type: ignore[attr-defined]

    eng = create_async_engine(TEST_DATABASE_URL, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Run migrations in a thread so the sync Alembic code doesn't block the loop.
    sync_url = TEST_DATABASE_URL.replace("+asyncpg", "")
    await asyncio.to_thread(_run_alembic_migrations, sync_url)

    get_engine.cache_clear()  # type: ignore[attr-defined]
    get_sessionmaker.cache_clear()  # type: ignore[attr-defined]

    yield eng
    await eng.dispose()


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    """Alias kept for backwards compat; migrations already ran in `engine`."""
    return engine


def make_session_cookie(user_id: str) -> str:
    signer = TimestampSigner(_SESSION_SECRET, salt="cookie-session")
    payload = json.dumps({"user_id": user_id})
    encoded = base64.b64encode(payload.encode()).decode()
    return signer.sign(encoded).decode()


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    from podking.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded_client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """Authenticated AsyncClient with a seeded allowlisted user."""
    from podking.db import get_sessionmaker
    from podking.main import create_app
    from podking.models import User, UserSettings

    sm = get_sessionmaker()
    async with sm() as db:
        user = User(
            email="allowed@example.com",
            google_sub="google-sub-test",
            display_name="Test User",
        )
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id, system_prompt="Summarize this."))
        await db.commit()
        user_id = str(user.id)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set("session", make_session_cookie(user_id))
        yield c
