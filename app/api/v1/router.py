from fastapi import APIRouter

from app.api.v1.endpoints import dashboard, hello, user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(user.router)
api_router.include_router(dashboard.router)
api_router.include_router(hello.router)
