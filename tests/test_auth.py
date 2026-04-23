from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import RedirectResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from podking.models import Base, User


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_login_redirects_to_google(migrated_engine: AsyncEngine) -> None:
    from podking.main import create_app

    app = create_app()

    # Mock authorize_redirect so we don't hit Google's OIDC discovery endpoint.
    with patch("podking.auth.oauth") as mock_oauth:
        async def fake_redirect(request, redirect_uri):
            return RedirectResponse(
                url=f"https://accounts.google.com/o/oauth2/auth?redirect_uri={redirect_uri}",
                status_code=302,
            )

        mock_oauth.google.authorize_redirect = fake_redirect
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
        ) as c:
            resp = await c.get("/auth/login")
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_rejects_non_allowlisted_email(migrated_engine: AsyncEngine) -> None:
    from podking.main import create_app

    app = create_app()
    fake_token = {
        "userinfo": {"email": "nope@example.com", "sub": "sub-x", "name": "Nope"}
    }

    with patch("podking.auth.oauth") as mock_oauth:
        mock_oauth.google.authorize_access_token = AsyncMock(return_value=fake_token)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
        ) as c:
            resp = await c.get("/auth/callback?code=abc&state=x")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_callback_creates_user_and_session(migrated_engine: AsyncEngine) -> None:
    from podking.main import create_app

    app = create_app()
    fake_token = {
        "userinfo": {"email": "allowed@example.com", "sub": "sub-ok", "name": "OK"}
    }

    with patch("podking.auth.oauth") as mock_oauth:
        mock_oauth.google.authorize_access_token = AsyncMock(return_value=fake_token)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
        ) as c:
            resp = await c.get("/auth/callback?code=abc&state=x")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"

    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u = (
            await session.execute(select(User).where(User.google_sub == "sub-ok"))
        ).scalar_one()
        assert u.email == "allowed@example.com"
