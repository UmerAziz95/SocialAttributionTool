from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.middlewares.cors import add_cors


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run application start-up and shut-down events."""

    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

    add_cors(app, origins=settings.CORS_ORIGINS)

    app.include_router(api_router)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    return app


app = create_app()
