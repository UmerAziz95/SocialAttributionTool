# app/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.v1.router import api_router  # <-- keep on one line
from app.middlewares.cors import add_cors

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

def create_app() -> FastAPI:
    app = FastAPI(title="My FastAPI", version="1.0.0", lifespan=lifespan)

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
