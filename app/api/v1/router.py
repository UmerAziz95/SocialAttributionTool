"""API router configuration for version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1.routes import dashboard, hello, user

router = APIRouter()
router.include_router(user.router)
router.include_router(dashboard.router)
router.include_router(hello.router)

__all__ = ["router"]
