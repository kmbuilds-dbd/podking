import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from podking.models import Base
from podking.repositories.users import upsert_user_from_google
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _add_login(app: FastAPI, uid: str) -> None:
    @app.post("/test/_login")
    async def _fn(request: Request) -> dict[str, bool]:
        request.session["user_id"] = uid
        return {"ok": True}


@pytest.mark.asyncio
async def test_me_returns_401_when_anonymous(migrated_engine: AsyncEngine) -> None:
    from podking.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_info(migrated_engine: AsyncEngine) -> None:
    from podking.main import create_app

    app = create_app()

    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u = await upsert_user_from_google(
            session, google_sub="s", email="allowed@example.com", display_name="Me"
        )
        await session.commit()
        uid = str(u.id)

    _add_login(app, uid)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/test/_login")).status_code == 200
        resp = await c.get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "allowed@example.com"
    assert body["display_name"] == "Me"
    assert "audio_enabled" in body


@pytest.mark.asyncio
async def test_feed_url_lazy_creates_token_and_regenerate_rotates(
    migrated_engine: AsyncEngine,
) -> None:
    """First GET /api/me/feed-url assigns a token; subsequent GETs return
    the same token; POST regenerate rotates it."""
    from podking.main import create_app

    app = create_app()

    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u = await upsert_user_from_google(
            session, google_sub="ft", email="allowed@example.com", display_name="Me"
        )
        await session.commit()
        uid = str(u.id)

    _add_login(app, uid)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        await c.post("/test/_login")

        first = await c.get("/api/me/feed-url")
        assert first.status_code == 200
        token1 = first.json()["token"]
        assert token1
        assert first.json()["base_url"].endswith(f"/reader/{token1}")

        second = await c.get("/api/me/feed-url")
        assert second.json()["token"] == token1  # idempotent

        rotated = await c.post("/api/me/feed-url/regenerate")
        assert rotated.status_code == 200
        token2 = rotated.json()["token"]
        assert token2 != token1
        assert rotated.json()["base_url"].endswith(f"/reader/{token2}")
