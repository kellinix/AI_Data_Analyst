from fastapi import APIRouter

from app.api.v1.endpoints import (
    health,
    users,
    uploads,
    analyses,
    insights,
    chat,
    exports,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(analyses.router, prefix="/analyses", tags=["analyses"])
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
