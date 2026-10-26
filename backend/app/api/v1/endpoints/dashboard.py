"""Owner-only, versioned layout edits. Generated chart data is never changed."""

import math
import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.analytics.live_filter import FilterValidationError, validate_filters
from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.limiter import limiter
from app.models.analysis import Analysis, AnalysisStatus
from app.models.dashboard_revision import DashboardRevision
from app.models.metric_definition import MetricDefinition
from app.schemas.dashboard import DashboardEdit, DashboardState
from app.services.dashboard_spec import default_spec, edit_spec, reconcile_spec

router = APIRouter()


async def _owned_analysis(db: DB, user_id: uuid.UUID, analysis_id: uuid.UUID, *, lock: bool = False) -> Analysis:
    statement = select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    analysis = await db.scalar(statement)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="Analysis has not finished")
    return analysis


async def _latest(db: DB, analysis_id: uuid.UUID, user_id: uuid.UUID) -> DashboardRevision | None:
    return await db.scalar(select(DashboardRevision).where(
        DashboardRevision.analysis_id == analysis_id,
        DashboardRevision.user_id == user_id,
    ).order_by(DashboardRevision.version.desc()).limit(1))


async def _metric_ids(db: DB, analysis: Analysis, user_id: uuid.UUID) -> list[str]:
    result = await db.scalars(select(MetricDefinition.family_id).where(
        MetricDefinition.analysis_id == analysis.id,
        MetricDefinition.file_id == analysis.file_id,
        MetricDefinition.user_id == user_id,
        MetricDefinition.is_current.is_(True),
    ))
    return [str(item) for item in result]


def _safe_filters(filters: list[dict], analysis: Analysis) -> list[dict]:
    if len(filters) > 8:
        raise ValueError("Too many filters")
    normalized = []
    for item in filters:
        if not isinstance(item, dict) or item.get("op") not in ("in", "between", "date_between"):
            raise ValueError("Invalid dashboard filter")
        values = item.get("values")
        if not isinstance(values, list) or not 1 <= len(values) <= 50:
            raise ValueError("Filter needs 1 to 50 values")
        if item["op"] == "in" and any(
            isinstance(value, bool) or not isinstance(value, str | int | float)
            or (isinstance(value, float) and not math.isfinite(value))
            for value in values
        ):
            raise ValueError("Category filter values must be finite text or numbers")
        normalized.append({"column": item.get("column"), "op": item["op"], "values": values})
    return validate_filters(normalized, (analysis.metadata_ or {}).get("schema", []))


def _reconcile(spec: dict, analysis: Analysis, metric_ids: list[str]) -> dict:
    result = reconcile_spec(spec, analysis.charts or [], metric_ids)
    try:
        result["saved_filters"] = _safe_filters(result["saved_filters"], analysis)
    except (ValueError, FilterValidationError):
        result["saved_filters"] = []
    return result


@router.get("/{analysis_id}/dashboard", response_model=DashboardState)
async def get_dashboard(analysis_id: uuid.UUID, current_user: CurrentUser, db: DB) -> DashboardState:
    analysis = await _owned_analysis(db, current_user.id, analysis_id)
    current = await _latest(db, analysis_id, current_user.id)
    metric_ids = await _metric_ids(db, analysis, current_user.id)
    spec = _reconcile(current.spec, analysis, metric_ids) if current else default_spec(analysis.charts or [])
    return DashboardState(version=current.version if current else 0, spec=spec)


@router.post("/{analysis_id}/dashboard", response_model=DashboardState)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def edit_dashboard(
    request: Request, analysis_id: uuid.UUID, body: DashboardEdit,
    current_user: CurrentUser, db: DB,
) -> DashboardState:
    analysis = await _owned_analysis(db, current_user.id, analysis_id, lock=True)
    current = await _latest(db, analysis_id, current_user.id)
    metric_ids = await _metric_ids(db, analysis, current_user.id)
    version = current.version if current else 0
    if body.expected_version != version:
        raise HTTPException(status_code=409, detail="Dashboard changed. Refresh and try again")
    current_spec = _reconcile(current.spec, analysis, metric_ids) if current else default_spec(analysis.charts or [])
    if body.action == "undo":
        if current is None:
            raise HTTPException(status_code=409, detail="No dashboard change to undo")
        previous = await db.scalar(select(DashboardRevision).where(
            DashboardRevision.analysis_id == analysis_id,
            DashboardRevision.user_id == current_user.id,
            DashboardRevision.version == version - 1,
        )) if version > 1 else None
        next_spec = _reconcile(previous.spec, analysis, metric_ids) if previous else default_spec(analysis.charts or [])
    else:
        try:
            filters = _safe_filters(body.filters or [], analysis) if body.action == "save_filters" else None
            next_spec = edit_spec(current_spec, body.action, body.chart_id,
                                  metric_ids=metric_ids, metric_family_id=body.metric_family_id,
                                  filters=filters, palette=body.palette)
        except (ValueError, FilterValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if next_spec == current_spec:
        return DashboardState(version=version, spec=current_spec)
    revision = DashboardRevision(
        analysis_id=analysis_id, user_id=current_user.id, version=version + 1, spec=next_spec
    )
    db.add(revision)
    await db.flush()
    return DashboardState(version=revision.version, spec=next_spec)
