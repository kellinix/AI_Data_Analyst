from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analytics.histogram_presentation import present_histogram
from app.analytics.line_presentation import present_time_line
from app.analytics.record_context import record_context
from app.analytics.report_relevance import useful_charts, useful_insights
from app.services.investigation import evidence_revision, evidence_spec, supporting_figures
from app.services.report_language import chart_description, present_insight, present_metadata


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
    @model_validator(mode="after")
    def clarify_count_description(self) -> ChartConfig:
        self.description = chart_description(self.description)
        if self.type == "line":
            presented_line = present_time_line(self.model_dump())
            self.description, self.echarts_option, self.visual_spec = presented_line["description"], presented_line["echarts_option"], presented_line["visual_spec"]
        if self.type == "histogram":
            presented = present_histogram(self.model_dump())
            for key in ("title", "description", "currency", "xAxis", "yAxis", "echarts_option", "visual_spec"):
                setattr(self, key, presented.get(key))
        return self

    id: str
    type: str
    title: str
    description: str | None = None
    xAxis: str | None = None
    yAxis: str | None = None
    series: list[str] = Field(default_factory=list)
    color_scheme: list[str] = Field(default_factory=list)
    # Set when the chart's measure is money, so the UI formats it in that
    # currency rather than as a bare number.
    currency: str | None = None
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
    # The requesting owner's verdict on a recommendation; always None on
    # shared/public views.
    user_feedback: Literal["helpful", "not_helpful"] | None = None

    @model_validator(mode="after")
    def business_wording(self) -> InsightResponse:
        presented = present_insight(self.model_dump())
        self.title = presented["title"]
        self.description = presented["description"]
        self.data = presented["data"]
        return self


class RecommendationFeedbackRequest(BaseModel):
    verdict: Literal["helpful", "not_helpful"]


class RecommendationFeedbackResponse(BaseModel):
    insight_id: uuid.UUID
    verdict: Literal["helpful", "not_helpful"]


class FilterableColumn(BaseModel):
    """A column the interactive dashboard can offer as a slicer, derived from
    the analysis's stored data profile."""

    column: str
    display_label: str
    role: str
    kind: Literal["categorical", "numeric", "date"]
    unique_count: int | None = None
    top_values: list[dict[str, Any]] | None = None
    min: float | None = None
    max: float | None = None
    min_date: str | None = None
    max_date: str | None = None


class FilterSpec(BaseModel):
    column: str
    op: Literal["in", "between", "date_between"]
    values: list[Any] = Field(..., min_length=1, max_length=50)


class LiveQueryRequest(BaseModel):
    filters: list[FilterSpec] = Field(default_factory=list, max_length=8)


class ChartPatch(BaseModel):
    id: str
    echarts_option: dict[str, Any] = Field(default_factory=dict)
    visual_spec: dict[str, Any] | None = None
    skipped: bool = False


class KpiPatch(BaseModel):
    insight_id: uuid.UUID
    value: float | None = None
    skipped: bool = False


class LiveQueryResponse(BaseModel):
    row_count: int
    sample_row_count: int
    charts: list[ChartPatch] = Field(default_factory=list)
    kpis: list[KpiPatch] = Field(default_factory=list)


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
    error_message: str | None = None
    insights: list[InsightResponse] = Field(default_factory=list)
    charts: list[ChartConfig] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    share_token: str | None = None
    filterable_columns: list[FilterableColumn] = Field(default_factory=list)

    @model_validator(mode="after")
    def business_wording(self) -> AnalysisDetailResponse:
        chart_ids = {c["id"] for c in useful_charts([c.model_dump() for c in self.charts])}
        self.charts = [c for c in self.charts if c.id in chart_ids]
        insight_ids = {i["id"] for i in useful_insights([i.model_dump() for i in self.insights])}
        self.insights = [i for i in self.insights if i.id in insight_ids]
        raw_metadata = self.metadata or {}
        context = record_context(raw_metadata)
        if context and context["kind"] == "admission":
            priority = {"chance_of_admit": 0, "cgpa": 1, "gre_score": 2, "toefl_score": 3, "university_rating": 4}
            self.insights.sort(key=lambda i: priority.get((i.data or {}).get("column"), 100))
        for chart in self.charts:
            presented_chart = present_histogram(chart.model_dump(), context)
            for key in ("title", "description", "xAxis", "yAxis", "echarts_option", "visual_spec"):
                setattr(chart, key, presented_chart.get(key))
        revision = evidence_revision(self.id, self.row_count, raw_metadata)
        for insight in self.insights:
            saved = insight.model_dump()
            presented = present_insight(saved, raw_metadata)
            insight.title, insight.description, insight.data = presented["title"], presented["description"], presented["data"]
            figures = supporting_figures(raw_metadata, saved)
            if figures:
                insight.data = {**(insight.data or {}), "supporting_figures": figures}
            if evidence_spec(raw_metadata, saved):
                insight.data = {**(insight.data or {}), "evidence_link": {
                    "kind": "insight", "insight_id": str(insight.id), "evidence_revision": revision}}
        self.metadata, self.summary = present_metadata(self.metadata, self.summary)
        if context:
            self.metadata = {**(self.metadata or {}), "record_context": context}
        for index, issue in enumerate(((self.metadata or {}).get("data_quality") or {}).get("issues") or []):
            if evidence_spec(raw_metadata, issue_index=index):
                issue["evidence_link"] = {"kind": "quality", "issue_index": index, "evidence_revision": revision}
        return self


class AnalysisStatusResponse(BaseModel):
    status: str
    progress: int
    error: str | None = None


class ShareLinkResponse(BaseModel):
    share_token: str
    share_url: str


class SharedAnalysisResponse(BaseModel):
    @model_validator(mode="after")
    def relevant_content(self) -> SharedAnalysisResponse:
        chart_ids = {c["id"] for c in useful_charts([c.model_dump() for c in self.charts])}
        self.charts = [c for c in self.charts if c.id in chart_ids]
        insight_ids = {i["id"] for i in useful_insights([i.model_dump() for i in self.insights])}
        self.insights = [i for i in self.insights if i.id in insight_ids]
        return self

    name: str
    row_count: int | None
    column_count: int | None
    created_at: datetime
    summary: str | None
    insights: list[InsightResponse] = Field(default_factory=list)
    charts: list[ChartConfig] = Field(default_factory=list)


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    limit: int
    pages: int
