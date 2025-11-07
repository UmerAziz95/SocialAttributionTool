"""API router configuration for version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1.routes import dashboard, hello, ingestion, user

api_router = APIRouter()
api_router.include_router(user.router)
api_router.include_router(dashboard.router)
api_router.include_router(hello.router)
api_router.include_router(ingestion.router)

__all__ = ["api_router"]
