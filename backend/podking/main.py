from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from podking import auth
from podking.api import health
from podking.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="podking")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        same_site="lax",
        https_only=False,
        max_age=30 * 24 * 3600,
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
