"""Owner-only preview and versioned approval of reusable calculations."""

import uuid
from pathlib import Path

import duckdb
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.limiter import limiter
from app.models.analysis import Analysis, AnalysisStatus
from app.models.metric_definition import MetricDefinition
from app.schemas.metric_definition import (
    MetricDefinitionInput,
    MetricDefinitionResponse,
    MetricPreviewResponse,
)
from app.services.file_processor import FileProcessor
from app.services.metric_definitions import calculate_metric, preview_metric, validate_metric_source

router = APIRouter()


async def _owned_analysis(db: DB, user_id: uuid.UUID, analysis_id: uuid.UUID, *, lock: bool = False) -> Analysis:
    statement = select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    result = await db.execute(statement.options(selectinload(Analysis.file)))
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="Analysis has not finished")
    return analysis


def _validate(analysis: Analysis, body: MetricDefinitionInput) -> None:
    try:
        validate_metric_source(
            (analysis.metadata_ or {}).get("schema", []), body.aggregation, body.column_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _preview(analysis: Analysis, body: MetricDefinitionInput) -> MetricPreviewResponse:
    if not Path(analysis.file.storage_path).is_file():
        raise HTTPException(status_code=409, detail="The saved dataset is unavailable")
    value, row_count, truncated = await preview_metric(
        analysis.file.storage_path, body.aggregation, body.column_name
    )
    return MetricPreviewResponse(
        value=value, row_count=row_count, sample_truncated=truncated,
        source_filename=analysis.file.original_filename, definition=body,
    )


@router.post("/{analysis_id}/metrics/preview", response_model=MetricPreviewResponse)
@limiter.limit(f"{settings.live_query_rate_limit_per_minute}/minute")
async def preview_definition(
    request: Request, analysis_id: uuid.UUID, body: MetricDefinitionInput,
    current_user: CurrentUser, db: DB,
) -> MetricPreviewResponse:
    analysis = await _owned_analysis(db, current_user.id, analysis_id)
    _validate(analysis, body)
    return await _preview(analysis, body)


@router.get("/{analysis_id}/metrics", response_model=list[MetricDefinitionResponse])
async def list_definitions(
    analysis_id: uuid.UUID, current_user: CurrentUser, db: DB,
) -> list[MetricDefinitionResponse]:
    analysis = await _owned_analysis(db, current_user.id, analysis_id)
    result = await db.execute(
        select(MetricDefinition).where(
            MetricDefinition.analysis_id == analysis_id,
            MetricDefinition.user_id == current_user.id,
            MetricDefinition.file_id == analysis.file_id,
            MetricDefinition.is_current.is_(True),
        ).order_by(MetricDefinition.created_at, MetricDefinition.id)
    )
    definitions = list(result.scalars())
    if not definitions:
        return []
    if not Path(analysis.file.storage_path).is_file():
        raise HTTPException(status_code=409, detail="The saved dataset is unavailable")
    conn = duckdb.connect(":memory:")
    try:
        row_count, truncated = await FileProcessor().read_to_duckdb_ex(
            conn, analysis.file.storage_path, Path(analysis.file.storage_path).suffix.lower()
        )
        return [
            MetricDefinitionResponse.model_validate(item).model_copy(update={
                "value": calculate_metric(conn, item.aggregation, item.column_name),
                "row_count": row_count,
                "sample_truncated": truncated,
            })
            for item in definitions
        ]
    finally:
        conn.close()


@router.post("/{analysis_id}/metrics", response_model=MetricDefinitionResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def approve_definition(
    request: Request, analysis_id: uuid.UUID, body: MetricDefinitionInput,
    current_user: CurrentUser, db: DB,
) -> MetricDefinitionResponse:
    analysis = await _owned_analysis(db, current_user.id, analysis_id, lock=True)
    _validate(analysis, body)
    preview = await _preview(analysis, body)
    count = await db.scalar(select(func.count()).select_from(MetricDefinition).where(
        MetricDefinition.analysis_id == analysis_id,
        MetricDefinition.user_id == current_user.id,
        MetricDefinition.file_id == analysis.file_id,
        MetricDefinition.is_current.is_(True),
    ))
    if (count or 0) >= 25:
        raise HTTPException(status_code=409, detail="This analysis already has 25 definitions")
    definition = MetricDefinition(
        user_id=current_user.id, analysis_id=analysis.id, file_id=analysis.file_id,
        family_id=uuid.uuid4(), version=1, is_current=True,
        name=body.name.strip(), aggregation=body.aggregation,
        column_name=body.column_name, approved_at=func.now(),
    )
    db.add(definition)
    await db.flush()
    await db.refresh(definition)
    return MetricDefinitionResponse.model_validate(definition).model_copy(update={
        "value": preview.value, "row_count": preview.row_count,
        "sample_truncated": preview.sample_truncated,
    })


@router.put("/{analysis_id}/metrics/{family_id}", response_model=MetricDefinitionResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def revise_definition(
    request: Request, analysis_id: uuid.UUID, family_id: uuid.UUID,
    body: MetricDefinitionInput, current_user: CurrentUser, db: DB,
) -> MetricDefinitionResponse:
    analysis = await _owned_analysis(db, current_user.id, analysis_id, lock=True)
    _validate(analysis, body)
    current = await db.scalar(select(MetricDefinition).where(
        MetricDefinition.family_id == family_id,
        MetricDefinition.analysis_id == analysis_id,
        MetricDefinition.user_id == current_user.id,
        MetricDefinition.file_id == analysis.file_id,
        MetricDefinition.is_current.is_(True),
    ))
    if current is None:
        raise HTTPException(status_code=404, detail="Metric definition not found")
    preview = await _preview(analysis, body)
    current.is_current = False
    definition = MetricDefinition(
        user_id=current_user.id, analysis_id=analysis.id, file_id=analysis.file_id,
        family_id=family_id, version=current.version + 1, is_current=True,
        name=body.name.strip(), aggregation=body.aggregation,
        column_name=body.column_name, approved_at=func.now(),
    )
    db.add(definition)
    await db.flush()
    await db.refresh(definition)
    return MetricDefinitionResponse.model_validate(definition).model_copy(update={
        "value": preview.value, "row_count": preview.row_count,
        "sample_truncated": preview.sample_truncated,
    })
