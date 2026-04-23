from fastapi import FastAPI

from podking.api import health


def create_app() -> FastAPI:
    app = FastAPI(title="podking")
    app.include_router(health.router)
    return app


app = create_app()
