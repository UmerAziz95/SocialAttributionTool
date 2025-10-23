"""Top-level API router wiring together all exposed routes."""

from fastapi import APIRouter

from app.api.v1.router import router as v1_router

api_router = APIRouter(prefix="/api")
api_router.include_router(v1_router, prefix="/v1")

__all__ = ["api_router"]
