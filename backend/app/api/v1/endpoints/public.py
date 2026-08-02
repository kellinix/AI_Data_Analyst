"""Unauthenticated, read-only access to analyses via a share link."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB
from app.core.limiter import limiter
from app.models.analysis import Analysis
from app.schemas.analysis import ChartConfig, InsightResponse, SharedAnalysisResponse

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

    insights = [InsightResponse.model_validate(i) for i in analysis.insights]
    charts = [ChartConfig(**c) for c in (analysis.charts or [])]

    return SharedAnalysisResponse(
        name=analysis.name,
        row_count=analysis.row_count,
        column_count=analysis.column_count,
        created_at=analysis.created_at,
        summary=analysis.summary,
        insights=insights,
        charts=charts,
    )
