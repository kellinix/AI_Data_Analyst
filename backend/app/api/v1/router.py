from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyses,
    chat,
    dashboard,
    health,
    insights,
    metric_definitions,
    public,
    recommendation_feedback,
    uploads,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(analyses.router, prefix="/analyses", tags=["analyses"])
api_router.include_router(metric_definitions.router, prefix="/analyses", tags=["metrics"])
api_router.include_router(dashboard.router, prefix="/analyses", tags=["dashboard"])
api_router.include_router(
    recommendation_feedback.router, prefix="/analyses", tags=["recommendation-feedback"]
)
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
