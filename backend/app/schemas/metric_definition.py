from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Aggregation = Literal["sum", "average", "count", "distinct_count"]


class MetricDefinitionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    aggregation: Aggregation
    column_name: str | None = Field(default=None, max_length=512)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Metric name cannot be empty")
        return value


class MetricDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    analysis_id: uuid.UUID
    file_id: uuid.UUID
    version: int
    name: str
    aggregation: Aggregation
    column_name: str | None
    approved_at: datetime
    value: float | int | None = None
    row_count: int | None = None
    sample_truncated: bool = False


class MetricPreviewResponse(BaseModel):
    value: float | int | None
    row_count: int
    sample_truncated: bool
    source_filename: str
    definition: MetricDefinitionInput
