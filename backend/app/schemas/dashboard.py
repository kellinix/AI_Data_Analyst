from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DashboardSpec(BaseModel):
    schema_version: Literal[1] = 1
    chart_order: list[str] = Field(default_factory=list)
    hidden_chart_ids: list[str] = Field(default_factory=list)
    chart_palettes: dict[str, str] = Field(default_factory=dict)
    metric_family_ids: list[str] = Field(default_factory=list)
    saved_filters: list[dict[str, Any]] = Field(default_factory=list)


class DashboardState(BaseModel):
    version: int
    spec: DashboardSpec


class DashboardEdit(BaseModel):
    expected_version: int = Field(ge=0)
    action: Literal["hide", "show", "move_up", "move_down", "set_palette", "pin_metric", "unpin_metric", "save_filters", "undo"]
    chart_id: str | None = None
    palette: str | None = None
    metric_family_id: str | None = None
    filters: list[dict[str, Any]] | None = Field(default=None, max_length=8)
