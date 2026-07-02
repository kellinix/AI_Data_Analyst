from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DB
from app.core.config import settings
from app.core.logging import get_logger
from app.models.analysis import Analysis, AnalysisStatus, UploadedFile
from app.schemas.analysis import (
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisStatusResponse,
    ChartConfig,
    CreateCombinedAnalysisRequest,
    CreateAnalysisRequest,
    PaginatedResponse,
    RenameAnalysisRequest,
    InsightResponse,
)
from app.services.file_processor import FileProcessor
from app.services.semantic_wrangler import SemanticWrangler
from app.workers.tasks import run_analysis_task

router = APIRouter()
logger = get_logger(__name__)


def _analysis_detail_response(
    analysis: Analysis,
    uploaded_file: UploadedFile,
    *,
    summary: str | None = None,
    insights: list[InsightResponse] | None = None,
    charts: list[ChartConfig] | None = None,
) -> AnalysisDetailResponse:
    return AnalysisDetailResponse(
        id=analysis.id,
        name=analysis.name,
        status=analysis.status,
        file_id=analysis.file_id,
        filename=uploaded_file.original_filename,
        row_count=analysis.row_count,
        column_count=analysis.column_count,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        summary=summary,
        insights=insights or [],
        charts=charts or [],
    )


def _cleaning_enabled(cleaning: dict | None) -> bool:
    if not cleaning:
        return False
    mode = str(cleaning.get("mode") or "").lower()
    if mode == "raw":
        return False
    if mode == "clean":
        return True
    return bool(cleaning.get("enabled"))


def _cleaning_options(cleaning: dict | None) -> dict:
    cleaning = cleaning or {}
    return {
        "remove_duplicates": cleaning.get("remove_duplicates", True),
        "fuzzy_deduplicate": cleaning.get("fuzzy_deduplicate", False),
        "standardize_columns": cleaning.get("standardize_columns", True),
        "normalize_dates": cleaning.get("normalize_dates", True),
        "clean_text": cleaning.get("clean_text", True),
        "parse_currency_percent": cleaning.get("parse_currency_percent", True),
        "drop_empty": cleaning.get("drop_empty", True),
        "missing_data_strategy": cleaning.get("missing_data_strategy", "smart"),
        "outlier_policy": cleaning.get("outlier_policy", "keep"),
        "semantic_categorical_merging": cleaning.get("semantic_categorical_merging", True),
    }


async def _create_cleaned_uploaded_file(
    *,
    source_file: UploadedFile,
    current_user: CurrentUser,
    db: DB,
    processor: FileProcessor,
    cleaning: dict | None,
) -> tuple[UploadedFile, dict | None]:
    if not _cleaning_enabled(cleaning):
        return source_file, None

    upload_dir = Path(settings.upload_dir) / str(current_user.id)
    cleaned_stem = str(uuid.uuid4())
    parquet_path = upload_dir / f"{cleaned_stem}.cleaned.parquet"
    csv_path = upload_dir / f"{cleaned_stem}.cleaned.csv"
    extension = Path(source_file.storage_path).suffix.lower()
    cleaning_options = _cleaning_options(cleaning)
    profile = await processor.clean_file(
        source_file.storage_path,
        extension,
        str(parquet_path),
        str(csv_path),
        cleaning_options,
    )
    if cleaning_options.get("semantic_categorical_merging"):
        profile = await SemanticWrangler().canonicalize_cleaned_file(
            parquet_path=str(parquet_path),
            csv_path=str(csv_path),
            profile=profile,
        )
    file_size = parquet_path.stat().st_size if parquet_path.exists() else 0
    stem = source_file.original_filename.rsplit(".", 1)[0]
    cleaned_file = UploadedFile(
        user_id=current_user.id,
        filename=parquet_path.name,
        original_filename=f"{stem} cleaned.parquet",
        file_size=file_size,
        mime_type="application/vnd.apache.parquet",
        storage_path=str(parquet_path),
        row_count=profile.get("row_count"),
        column_count=profile.get("column_count"),
        columns=profile.get("columns"),
        checksum=None,
    )
    db.add(cleaned_file)
    current_user.storage_used_bytes = (current_user.storage_used_bytes or 0) + file_size
    await db.flush()
    await db.refresh(cleaned_file)

    cleaning_metadata = {
        "enabled": True,
        "mode": "clean",
        "source_file_id": str(source_file.id),
        "source_filename": source_file.original_filename,
        "cleaned_file_id": str(cleaned_file.id),
        "cleaned_csv_path": profile.get("cleaned_csv_path"),
        "cleaned_parquet_path": profile.get("cleaned_parquet_path"),
        "report": profile.get("cleaning_report", {}),
    }
    return cleaned_file, cleaning_metadata


@router.get("", response_model=PaginatedResponse)
async def list_analyses(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List the current user's analyses with pagination."""
    query = select(Analysis).where(Analysis.user_id == current_user.id)

    if search:
        query = query.where(Analysis.name.ilike(f"%{search}%"))
    if status_filter:
        query = query.where(Analysis.status == status_filter)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    query = query.order_by(Analysis.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)
    query = query.options(selectinload(Analysis.file))

    result = await db.execute(query)
    analyses = result.scalars().all()

    items = [
        AnalysisListResponse(
            id=a.id,
            name=a.name,
            status=a.status,
            file_id=a.file_id,
            filename=a.file.original_filename,
            row_count=a.row_count,
            column_count=a.column_count,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in analyses
        if a.file is not None
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=math.ceil(total / limit) if total else 0,
    )


@router.post("", response_model=AnalysisDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    body: CreateAnalysisRequest,
    current_user: CurrentUser,
    db: DB,
):
    """Create a new analysis and enqueue it for processing."""
    # Verify file belongs to user
    file_result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == body.file_id,
            UploadedFile.user_id == current_user.id,
        )
    )
    uploaded_file = file_result.scalar_one_or_none()
    if not uploaded_file:
        raise HTTPException(status_code=404, detail="File not found")

    processor = FileProcessor()
    analysis_file, cleaning_metadata = await _create_cleaned_uploaded_file(
        source_file=uploaded_file,
        current_user=current_user,
        db=db,
        processor=processor,
        cleaning=body.cleaning,
    )

    analysis_name = body.name or uploaded_file.original_filename.rsplit(".", 1)[0]
    upload_context = {
        **(body.relationship_context or {}),
        "cleaning": cleaning_metadata or {"enabled": False, "mode": "raw"},
    }

    analysis = Analysis(
        user_id=current_user.id,
        file_id=analysis_file.id,
        name=analysis_name,
        status=AnalysisStatus.PENDING.value,
        row_count=analysis_file.row_count,
        column_count=analysis_file.column_count,
        metadata_={"upload_context": upload_context},
    )
    db.add(analysis)
    current_user.analyses_this_month = (current_user.analyses_this_month or 0) + 1
    await db.flush()
    await db.refresh(analysis)

    # Commit before queueing so a fast Celery worker can read the analysis row.
    await db.commit()

    try:
        task = run_analysis_task.delay(str(analysis.id))
        analysis.celery_task_id = task.id
        await db.flush()
        await db.refresh(analysis)
    except Exception as exc:
        logger.error(
            "Failed to enqueue analysis task",
            analysis_id=str(analysis.id),
            exc=str(exc),
        )

    logger.info("Analysis created", analysis_id=str(analysis.id))
    return _analysis_detail_response(analysis, analysis_file)


@router.post("/combined", response_model=AnalysisDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_combined_analysis(
    body: CreateCombinedAnalysisRequest,
    current_user: CurrentUser,
    db: DB,
):
    """Create one analysis from multiple uploaded files."""
    file_result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(body.file_ids),
            UploadedFile.user_id == current_user.id,
        )
    )
    uploaded_files = list(file_result.scalars().all())
    if len(uploaded_files) != len(set(body.file_ids)):
        raise HTTPException(status_code=404, detail="One or more files were not found")

    files_by_id = {uploaded_file.id: uploaded_file for uploaded_file in uploaded_files}
    ordered_files = [files_by_id[file_id] for file_id in body.file_ids]

    upload_dir = Path(settings.upload_dir) / str(current_user.id)
    combined_filename = f"{uuid.uuid4()}.parquet"
    combined_path = upload_dir / combined_filename
    relationship_context = body.relationship_context or {}

    profile = await FileProcessor().combine_uploaded_files(
        ordered_files,
        str(combined_path),
        relationship_context,
    )
    file_size = combined_path.stat().st_size if combined_path.exists() else 0
    source_names = [uploaded_file.original_filename for uploaded_file in ordered_files]
    analysis_name = body.name or "Combined analysis"
    original_filename = f"{analysis_name}.parquet"

    combined_file = UploadedFile(
        user_id=current_user.id,
        filename=combined_filename,
        original_filename=original_filename,
        file_size=file_size,
        mime_type="application/vnd.apache.parquet",
        storage_path=str(combined_path),
        row_count=profile.get("row_count"),
        column_count=profile.get("column_count"),
        columns=profile.get("columns"),
        checksum=None,
    )
    db.add(combined_file)
    current_user.storage_used_bytes = (current_user.storage_used_bytes or 0) + file_size
    await db.flush()
    await db.refresh(combined_file)

    processor = FileProcessor()
    analysis_file, cleaning_metadata = await _create_cleaned_uploaded_file(
        source_file=combined_file,
        current_user=current_user,
        db=db,
        processor=processor,
        cleaning=body.cleaning,
    )

    combined_context = {
        **relationship_context,
        "combined": True,
        "cleaning": cleaning_metadata or {"enabled": False, "mode": "raw"},
        "source_files": [
            {
                "id": str(uploaded_file.id),
                "name": uploaded_file.original_filename,
                "row_count": uploaded_file.row_count,
                "column_count": uploaded_file.column_count,
            }
            for uploaded_file in ordered_files
        ],
    }

    analysis = Analysis(
        user_id=current_user.id,
        file_id=analysis_file.id,
        name=analysis_name,
        status=AnalysisStatus.PENDING.value,
        row_count=analysis_file.row_count,
        column_count=analysis_file.column_count,
        metadata_={
            "upload_context": combined_context,
        },
    )
    db.add(analysis)
    current_user.analyses_this_month = (current_user.analyses_this_month or 0) + 1
    await db.flush()
    await db.refresh(analysis)

    await db.commit()

    try:
        task = run_analysis_task.delay(str(analysis.id))
        analysis.celery_task_id = task.id
        await db.flush()
        await db.refresh(analysis)
    except Exception as exc:
        logger.error(
            "Failed to enqueue combined analysis task",
            analysis_id=str(analysis.id),
            exc=str(exc),
        )

    logger.info(
        "Combined analysis created",
        analysis_id=str(analysis.id),
        source_files=source_names,
    )
    return _analysis_detail_response(analysis, analysis_file)


@router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
async def get_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """Get a single analysis with all insights and charts."""
    result = await db.execute(
        select(Analysis)
        .where(Analysis.id == analysis_id, Analysis.user_id == current_user.id)
        .options(
            selectinload(Analysis.insights),
            selectinload(Analysis.file),
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    charts = [ChartConfig(**c) for c in (analysis.charts or [])]
    insights = [InsightResponse.model_validate(i) for i in analysis.insights]

    return AnalysisDetailResponse(
        id=analysis.id,
        name=analysis.name,
        status=analysis.status,
        file_id=analysis.file_id,
        filename=analysis.file.original_filename,
        row_count=analysis.row_count,
        column_count=analysis.column_count,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        summary=analysis.summary,
        insights=insights,
        charts=charts,
        metadata=analysis.metadata_,
    )


@router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id, Analysis.user_id == current_user.id
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return AnalysisStatusResponse(
        status=analysis.status,
        progress=analysis.progress,
        error=analysis.error_message,
    )


@router.get("/{analysis_id}/cleaned-download")
async def download_cleaned_dataset(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis)
        .where(Analysis.id == analysis_id, Analysis.user_id == current_user.id)
        .options(selectinload(Analysis.file))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    upload_context = (analysis.metadata_ or {}).get("upload_context") or {}
    cleaning = upload_context.get("cleaning") if isinstance(upload_context, dict) else {}
    csv_path = cleaning.get("cleaned_csv_path") if isinstance(cleaning, dict) else None
    if not csv_path:
        raise HTTPException(
            status_code=404,
            detail="No cleaned dataset is available for this analysis",
        )

    path = Path(csv_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cleaned dataset file not found")

    filename = f"{analysis.name.replace(' ', '_').lower()}_cleaned.csv"
    return FileResponse(
        path=str(path),
        media_type="text/csv",
        filename=filename,
    )


@router.get("/{analysis_id}/profile-json")
async def download_profile_json(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == current_user.id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    profile_path = (analysis.metadata_ or {}).get("profile_json_path")
    if not profile_path:
        raise HTTPException(
            status_code=404,
            detail="No Profile JSON is available for this analysis",
        )

    path = Path(profile_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Profile JSON file not found")

    filename = f"{analysis.name.replace(' ', '_').lower()}_profile.json"
    return FileResponse(
        path=str(path),
        media_type="application/json",
        filename=filename,
    )


@router.patch("/{analysis_id}", response_model=AnalysisListResponse)
async def rename_analysis(
    analysis_id: uuid.UUID,
    body: RenameAnalysisRequest,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id, Analysis.user_id == current_user.id
        ).options(selectinload(Analysis.file))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis.name = body.name
    await db.flush()
    await db.refresh(analysis)
    return AnalysisListResponse(
        id=analysis.id,
        name=analysis.name,
        status=analysis.status,
        file_id=analysis.file_id,
        filename=analysis.file.original_filename,
        row_count=analysis.row_count,
        column_count=analysis.column_count,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id, Analysis.user_id == current_user.id
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    await db.delete(analysis)


@router.post("/{analysis_id}/rerun", response_model=AnalysisDetailResponse)
async def rerun_analysis(
    analysis_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id, Analysis.user_id == current_user.id
        ).options(selectinload(Analysis.file), selectinload(Analysis.insights))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis.status = AnalysisStatus.PENDING.value
    analysis.progress = 0
    analysis.summary = None
    analysis.error_message = None
    analysis.charts = None

    # Delete existing insights
    for insight in analysis.insights:
        await db.delete(insight)

    await db.flush()
    await db.refresh(analysis)
    await db.commit()

    try:
        task = run_analysis_task.delay(str(analysis.id))
        analysis.celery_task_id = task.id
        await db.flush()
        await db.refresh(analysis)
    except Exception as exc:
        logger.error(
            "Failed to enqueue analysis rerun task",
            analysis_id=str(analysis.id),
            exc=str(exc),
        )

    return _analysis_detail_response(analysis, analysis.file)
