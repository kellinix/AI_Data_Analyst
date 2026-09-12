"""
Recommendation feedback — owners mark a recommendation helpful or not.

This is the production outcome signal for confidence calibration. Each row
snapshots the recommendation's confidence, source, and priority when the
verdict is given, and the `recommendation_calibration` view (migration 003)
aggregates the rows per confidence source. The offline benchmark
(`backend/evals/calibration/`) is the other signal; see
`docs/analytics/10_Confidence_Calibration.md` for how the two relate.

No `from __future__ import annotations` here: slowapi's `@limiter.limit`
wrapper makes FastAPI resolve string annotations against slowapi's module,
where these types don't exist (same as analyses.py).
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.limiter import limiter
from app.models.analysis import Analysis
from app.models.insight import Insight
from app.models.recommendation_feedback import RecommendationFeedback
from app.schemas.analysis import RecommendationFeedbackRequest, RecommendationFeedbackResponse

router = APIRouter()

_FEEDBACK_PATH = "/{analysis_id}/insights/{insight_id}/feedback"


async def _load_owned_recommendation(
    db: DB, user_id: uuid.UUID, analysis_id: uuid.UUID, insight_id: uuid.UUID
) -> Insight:
    result = await db.execute(
        select(Insight)
        .join(Analysis, Insight.analysis_id == Analysis.id)
        .where(
            Insight.id == insight_id,
            Insight.analysis_id == analysis_id,
            Analysis.user_id == user_id,
        )
    )
    insight = result.scalar_one_or_none()
    if insight is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if insight.type != "recommendation":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Feedback is only accepted on recommendations",
        )
    return insight


def _short_str(value: Any, limit: int) -> str | None:
    return str(value)[:limit] if value else None


@router.put(_FEEDBACK_PATH, response_model=RecommendationFeedbackResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def set_recommendation_feedback(
    request: Request,
    analysis_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: RecommendationFeedbackRequest,
    current_user: CurrentUser,
    db: DB,
) -> RecommendationFeedbackResponse:
    """Record or change the owner's verdict on one recommendation."""
    insight = await _load_owned_recommendation(db, current_user.id, analysis_id, insight_id)
    data = insight.data or {}

    statement = pg_insert(RecommendationFeedback).values(
        user_id=current_user.id,
        analysis_id=analysis_id,
        insight_id=insight.id,
        verdict=body.verdict,
        recommendation_title=insight.title[:512],
        importance=insight.importance,
        confidence=insight.confidence,
        confidence_source=_short_str(data.get("confidence_source"), 32),
        confidence_method=_short_str(data.get("confidence_method"), 16),
    )
    snapshot_columns = (
        "verdict",
        "recommendation_title",
        "importance",
        "confidence",
        "confidence_source",
        "confidence_method",
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_recommendation_feedback_insight_user",
        set_={
            **{column: statement.excluded[column] for column in snapshot_columns},
            "updated_at": func.now(),
        },
    )
    await db.execute(statement)
    await db.commit()
    return RecommendationFeedbackResponse(insight_id=insight.id, verdict=body.verdict)


@router.delete(_FEEDBACK_PATH, status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def clear_recommendation_feedback(
    request: Request,
    analysis_id: uuid.UUID,
    insight_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Withdraw the owner's verdict on one recommendation."""
    insight = await _load_owned_recommendation(db, current_user.id, analysis_id, insight_id)
    await db.execute(
        delete(RecommendationFeedback).where(
            RecommendationFeedback.insight_id == insight.id,
            RecommendationFeedback.user_id == current_user.id,
        )
    )
    await db.commit()
