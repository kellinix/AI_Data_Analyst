from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DB
from app.models.user import User
from app.models.subscription import Subscription
from app.schemas.user import UserProfileResponse, UserResponse, UserUpdate, UsageStats
from app.core.config import settings

router = APIRouter()

PLAN_LIMITS = {
    "free":         {"analyses": 5,   "ai_queries": 20,   "storage": 100 * 1024 * 1024},
    "starter":      {"analyses": 20,  "ai_queries": 100,  "storage": 1 * 1024 * 1024 * 1024},
    "professional": {"analyses": 100, "ai_queries": 500,  "storage": 10 * 1024 * 1024 * 1024},
    "enterprise":   {"analyses": 9999,"ai_queries": 9999, "storage": 100 * 1024 * 1024 * 1024},
}


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: CurrentUser, db: DB):
    """Return the authenticated user's profile and usage stats."""
    # Fetch subscription
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()

    limits = PLAN_LIMITS.get(current_user.plan, PLAN_LIMITS["free"])
    usage = UsageStats(
        analyses_this_month=current_user.analyses_this_month,
        analyses_limit=limits["analyses"],
        storage_used_bytes=current_user.storage_used_bytes,
        storage_limit_bytes=limits["storage"],
        ai_queries_this_month=current_user.ai_queries_this_month,
        ai_queries_limit=limits["ai_queries"],
    )

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        plan=current_user.plan,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        subscription=subscription,
        usage=usage,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update the current user's profile."""
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    await db.flush()
    await db.refresh(current_user)
    return current_user
