from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    unique_count: int
    sample_values: list[Any] = Field(default_factory=list)


class UploadedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    storage_path: str
    row_count: int | None
    column_count: int | None
    columns: list[ColumnInfo] | None
    created_at: datetime


class CreateAnalysisRequest(BaseModel):
    file_id: uuid.UUID
    name: str | None = None
    relationship_context: dict[str, Any] | None = None
    cleaning: dict[str, Any] | None = None


class CreateCombinedAnalysisRequest(BaseModel):
    file_ids: list[uuid.UUID] = Field(..., min_length=1)
    name: str | None = None
    relationship_context: dict[str, Any] | None = None
    cleaning: dict[str, Any] | None = None


class RenameAnalysisRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)


class ChartConfig(BaseModel):
    id: str
    type: str
    title: str
    description: str | None = None
    xAxis: str | None = None
    yAxis: str | None = None
    series: list[str] = Field(default_factory=list)
    color_scheme: list[str] = Field(default_factory=list)
    visual_spec: dict[str, Any] | None = None
    echarts_option: dict[str, Any] = Field(default_factory=dict)


class InsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    type: str
    title: str
    description: str
    importance: str
    confidence: float
    data: dict[str, Any] | None
    chart_config: dict[str, Any] | None
    created_at: datetime


class AnalysisListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    file_id: uuid.UUID
    filename: str
    row_count: int | None
    column_count: int | None
    created_at: datetime
    updated_at: datetime


class AnalysisDetailResponse(AnalysisListResponse):
    summary: str | None
    insights: list[InsightResponse] = Field(default_factory=list)
    charts: list[ChartConfig] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class AnalysisStatusResponse(BaseModel):
    status: str
    progress: int
    error: str | None = None


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    limit: int
    pages: int
