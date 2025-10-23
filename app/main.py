import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.middlewares.cors import add_cors


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run application start-up and shut-down events."""

    settings = get_settings()

    if settings.INIT_DB_ON_STARTUP:
        try:
            await init_db()
        except Exception as exc:  # pragma: no cover - startup failure is logged
            logger.exception(
                "Database initialisation failed. Check DATABASE_URL credentials and"
                " permissions."
            )
            raise RuntimeError(
                "Database initialisation failed. Verify DATABASE_URL and that the"
                " configured user can connect."
            ) from exc
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
