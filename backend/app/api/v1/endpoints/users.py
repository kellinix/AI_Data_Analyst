from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import delete, func, select

from app.api.deps import DB, CurrentUser
from app.core.plan_limits import plan_limits_for
from app.models.analysis import Analysis
from app.models.subscription import Subscription
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.schemas.user import (
    UsageLedgerSummary,
    UsageStats,
    UserProfileResponse,
    UserResponse,
    UserUpdate,
)
from app.services.account_service import delete_account_uploads, delete_auth_user

router = APIRouter()


@router.get("/me/usage-ledger", response_model=UsageLedgerSummary)
async def get_usage_ledger(current_user: CurrentUser, db: DB) -> UsageLedgerSummary:
    """Report observed operations separately from the still-active legacy counters."""
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = await db.execute(
        select(
            UsageEvent.kind,
            UsageEvent.status,
            func.count(UsageEvent.id),
            func.count(UsageEvent.id).filter(
                func.coalesce(UsageEvent.completed_at, UsageEvent.occurred_at) >= month_start
            ),
        )
        .where(UsageEvent.user_id == current_user.id)
        .group_by(UsageEvent.kind, UsageEvent.status)
    )
    counts = {(kind, event_status): (total, this_month) for kind, event_status, total, this_month in rows}
    token_rows = await db.execute(select(
        func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
        func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
    ).where(UsageEvent.user_id == current_user.id, UsageEvent.kind == "ai_followup"))
    prompt_tokens, completion_tokens = token_rows.one()

    def number(kind: str, event_status: str, index: int = 0) -> int:
        return int(counts.get((kind, event_status), (0, 0))[index])

    return UsageLedgerSummary(
        calendar_month_start=month_start,
        analysis_completed_lifetime=number("analysis", "completed"),
        analysis_completed_this_month=number("analysis", "completed", 1),
        analysis_reserved=number("analysis", "reserved"),
        analysis_failed=number("analysis", "failed"),
        ai_completed_lifetime=number("ai_followup", "completed"),
        ai_completed_this_month=number("ai_followup", "completed", 1),
        ai_failed=number("ai_followup", "failed"),
        ai_legacy_unknown=number("ai_followup", "legacy_unknown"),
        prompt_tokens_recorded=int(prompt_tokens),
        completion_tokens_recorded=int(completion_tokens),
        current_counter_analyses=current_user.analyses_this_month,
        current_counter_ai_queries=current_user.ai_queries_this_month,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: CurrentUser, db: DB):
    """Return the authenticated user's profile and usage stats."""
    # Fetch subscription
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()

    limits = plan_limits_for(current_user.plan)
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


@router.delete("/me", status_code=204)
async def delete_me(current_user: CurrentUser, db: DB):
    """Delete the authenticated account, its analyses, uploads and login."""
    running = await db.execute(
        select(Analysis.id).where(
            Analysis.user_id == current_user.id,
            Analysis.status.in_(["pending", "processing"]),
        ).limit(1)
    )
    if running.first() is not None:
        raise HTTPException(409, "Wait for your analyses to finish before deleting your account")
    subscription = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    billing = subscription.scalar_one_or_none()
    if billing and billing.stripe_subscription_id and billing.status not in ("canceled", "cancelled"):
        raise HTTPException(409, "Cancel your paid subscription before deleting your account")

    # Bulk DELETE lets the database cascade all owned rows, rather than having
    # ORM relationships try to null out required foreign keys.
    await db.execute(delete(User).where(User.id == current_user.id))
    await db.flush()
    await delete_auth_user(current_user.supabase_id)
    # Keep local rows if cleanup fails, so the owner can retry this endpoint.
    try:
        delete_account_uploads(current_user.id)
    except (OSError, ValueError):
        raise HTTPException(503, "Could not remove account files; please retry") from None
    await db.commit()
    return Response(status_code=204)
