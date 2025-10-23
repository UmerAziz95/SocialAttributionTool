from fastapi import APIRouter
from .endpoints import user, dashboard

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(user.router)
api_router.include_router(dashboard.router)
