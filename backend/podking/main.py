from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from podking import auth
from podking.api import health, me
from podking.api import settings as settings_api
from podking.config import get_settings
from podking.logging import configure_logging

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend_dist"
if not FRONTEND_DIST.exists():
    FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
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
    app.include_router(me.router)
    app.include_router(settings_api.router)

    if FRONTEND_DIST.exists():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        index_html = FRONTEND_DIST / "index.html"

        @app.exception_handler(404)
        async def spa_fallback(request: Request, exc: Exception) -> FileResponse:
            return FileResponse(index_html)

    return app


app = create_app()
