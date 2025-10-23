from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.v1.router import api_router
from app.middlewares.cors import add_cors

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup hooks (e.g., DB check) could go here
    yield
    # shutdown hooks go here

def create_app() -> FastAPI:
    app = FastAPI(title="My FastAPI", version="1.0.0", lifespan=lifespan)

    # CORS (adjust origins if needed)
    add_cors(app, origins=["http://localhost:3000"])

    # Versioned API
    app.include_router(api_router)

    # Health checks
    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        return {"status": "ready"}

    return app

app = create_app()
