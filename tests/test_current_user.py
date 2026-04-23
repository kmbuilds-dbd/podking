import pytest
from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from podking.deps import current_user
from podking.models import Base, User
from podking.repositories.users import upsert_user_from_google


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_protected_endpoint_returns_401_without_session(
    migrated_engine: AsyncEngine,
) -> None:
    from podking.main import create_app

    app = create_app()

    @app.get("/protected")
    async def protected(user: User = Depends(current_user)) -> dict[str, str]:
        return {"email": user.email}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/protected")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_returns_user_with_session(
    migrated_engine: AsyncEngine,
) -> None:
    from podking.main import create_app

    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        user = await upsert_user_from_google(
            session, google_sub="s", email="a@b.com", display_name="A"
        )
        await session.commit()
        user_id = user.id

    app = create_app()

    @app.get("/protected")
    async def protected(u: User = Depends(current_user)) -> dict[str, str]:
        return {"email": u.email}

    @app.post("/test/_login")
    async def _login(request: Request) -> dict[str, bool]:
        request.session["user_id"] = str(user_id)
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/test/_login")).status_code == 200
        resp = await c.get("/protected")
    assert resp.status_code == 200
    assert resp.json() == {"email": "a@b.com"}
