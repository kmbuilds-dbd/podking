from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from podking import auth
from podking.api import events, health, jobs, me, search, subscriptions, summaries, tags
from podking.api import settings as settings_api
from podking.config import get_settings
from podking.db import get_sessionmaker
from podking.logging import configure_logging

log = structlog.get_logger()

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend_dist"
if not FRONTEND_DIST.exists():
    FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from podking.api.jobs import mark_interrupted_jobs_failed
    from podking.scheduler import run_feed_poller, run_retention_cleanup
    from podking.worker.runner import run_worker

    sm = get_sessionmaker()
    async with sm() as db:
        await mark_interrupted_jobs_failed(db)

    worker_task = asyncio.create_task(run_worker())
    poller_task = asyncio.create_task(run_feed_poller())
    cleanup_task = asyncio.create_task(run_retention_cleanup())

    log.info("background_tasks_started")
    try:
        yield
    finally:
        for task in (worker_task, poller_task, cleanup_task):
            task.cancel()
        await asyncio.gather(worker_task, poller_task, cleanup_task, return_exceptions=True)
        log.info("background_tasks_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="podking", lifespan=lifespan)
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
    app.include_router(jobs.router)
    app.include_router(events.router)
    app.include_router(summaries.router)
    app.include_router(tags.router)
    app.include_router(search.router)
    app.include_router(subscriptions.router)

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
