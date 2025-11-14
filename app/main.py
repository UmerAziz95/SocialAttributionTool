# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router  # <-- keep on one line
from app.middlewares.cors import add_cors

APP_DESCRIPTION = """Social Attribution Tool APIs for managing marketing ingestion and analytics.\n\n"""

OPENAPI_TAGS_METADATA = [
    {
        "name": "files",
        "description": (
            "Endpoints to upload raw marketing exports and trigger the ingestion "
            "pipeline. Use these routes to normalize CSV/TSV inputs and "
            "upsert them into the analytics warehouse."
        ),
    }
]
                
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

def create_app() -> FastAPI:
    app = FastAPI(
        title="Social Attribution Tool API",
        description=APP_DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS_METADATA,
    )

    add_cors(app, origins=["http://localhost:3000"])

    # Versioned API
    app.include_router(api_router, prefix="/api/v1")

    # Health checks
    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        return {"status": "ready"}

    return app

app = create_app()
