"""Unauthenticated, read-only access to analyses via a share link.

No `from __future__ import annotations` here: slowapi's `@limiter.limit`
wrapper makes FastAPI resolve string annotations against slowapi's module,
where `DB` doesn't exist — the session dependency then degraded into an
unresolvable query parameter, breaking this endpoint and /api/openapi.json.
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.analytics.histogram_presentation import present_histogram
from app.analytics.record_context import record_context
from app.api.deps import DB
from app.core.limiter import limiter
from app.models.analysis import Analysis
from app.schemas.analysis import ChartConfig, InsightResponse, SharedAnalysisResponse
from app.services.report_language import present_insight, present_metadata

router = APIRouter()


@router.get("/shared/{share_token}", response_model=SharedAnalysisResponse)
@limiter.limit("30/minute")
async def get_shared_analysis(request: Request, share_token: str, db: DB):
    result = await db.execute(
        select(Analysis)
        .where(Analysis.share_token == share_token)
        .options(selectinload(Analysis.insights))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="This share link is invalid or has been revoked.")

    insights = [InsightResponse.model_validate(present_insight(InsightResponse.model_validate(i).model_dump(), analysis.metadata_))
                for i in analysis.insights]
    charts = [ChartConfig(**present_histogram(c, record_context(analysis.metadata_ or {}))) for c in (analysis.charts or [])]

    return SharedAnalysisResponse(
        name=analysis.name,
        row_count=analysis.row_count,
        column_count=analysis.column_count,
        created_at=analysis.created_at,
        summary=present_metadata(analysis.metadata_, analysis.summary)[1],
        insights=insights,
        charts=charts,
    )
