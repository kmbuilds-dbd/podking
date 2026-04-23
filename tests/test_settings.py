import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from podking.crypto import decrypt
from podking.models import Base, User
from podking.repositories.users import upsert_user_from_google
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import selectinload


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def _setup_user(migrated_engine: AsyncEngine) -> str:
    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u = await upsert_user_from_google(
            session, google_sub="s", email="allowed@example.com", display_name="Me"
        )
        await session.commit()
        return str(u.id)


def _add_login(app: FastAPI, uid: str) -> None:
    @app.post("/test/_login")
    async def _fn(request: Request) -> dict[str, bool]:
        request.session["user_id"] = uid
        return {"ok": True}


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(migrated_engine: AsyncEngine) -> None:
    from podking.main import create_app

    app = create_app()
    uid = await _setup_user(migrated_engine)
    _add_login(app, uid)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/test/_login")
        resp = await c.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "system_prompt": "",
        "anthropic_key": {"set": False},
        "elevenlabs_key": {"set": False},
        "voyage_key": {"set": False},
    }


@pytest.mark.asyncio
async def test_patch_settings_persists_prompt_and_encrypts_keys(
    migrated_engine: AsyncEngine,
) -> None:
    from podking.main import create_app

    app = create_app()
    uid = await _setup_user(migrated_engine)
    _add_login(app, uid)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/test/_login")
        resp = await c.patch(
            "/api/settings",
            json={
                "system_prompt": "Summarize briefly.",
                "anthropic_api_key": "sk-ant-xxx",
            },
        )
    assert resp.status_code == 200

    sm = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with sm() as session:
        u = (
            await session.execute(
                select(User)
                .options(selectinload(User.settings))
                .where(User.email == "allowed@example.com")
            )
        ).scalar_one()
        assert u.settings is not None
        assert u.settings.system_prompt == "Summarize briefly."
        assert u.settings.anthropic_api_key_encrypted is not None
        assert decrypt(u.settings.anthropic_api_key_encrypted) == "sk-ant-xxx"


@pytest.mark.asyncio
async def test_settings_response_never_leaks_plaintext_keys(
    migrated_engine: AsyncEngine,
) -> None:
    from podking.main import create_app

    app = create_app()
    uid = await _setup_user(migrated_engine)
    _add_login(app, uid)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/test/_login")
        await c.patch("/api/settings", json={"anthropic_api_key": "sk-leak"})
        resp = await c.get("/api/settings")
    body = resp.text
    assert "sk-leak" not in body
    assert resp.json()["anthropic_key"] == {"set": True}
