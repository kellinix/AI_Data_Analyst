"""Make a time chart's first measured point explicit without adding observations."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.analytics.labels import derive_label, sentence_label
from app.analytics.summary_evidence import _finite


def present_time_line(chart: dict[str, Any]) -> dict[str, Any]:
    if chart.get("type") != "line":
        return chart
    result = deepcopy(chart)
    option = result.get("echarts_option") or {}
    axis, series = option.get("xAxis") or {}, option.get("series") or []
    if option.get("_line_start_presentation") or not isinstance(axis, dict) or len(series) != 1:
        return result
    item = series[0]
    if (item.get("lineStyle") or {}).get("opacity") == 0:
        return result
    dates, values = axis.get("data") or [], item.get("data") or []
    measured = [(index, _finite(value)) for index, value in enumerate(values) if index < len(dates) and _finite(value) is not None]
    if not measured:
        return result
    columns = option.get("_columns") or {}
    measure = sentence_label(str((option.get("yAxis") or {}).get("name") or derive_label(str(chart.get("yAxis") or "value"))))
    period = "week" if str(columns.get("x", "")).lower() == "week_start_date" else "date"
    aggregation = columns.get("aggregation") or chart.get("aggregation")
    if aggregation == "sum":
        description = f"Total for each {period}." if measure.lower() == "total" else f"Total {measure} for each {period}."
    elif aggregation == "average":
        description = f"Average {measure} for each {period}."
    else:
        description = str(chart.get("description") or "")
    result["description"] = description
    axis.update({"boundaryGap": False, "nameLocation": "middle", "nameGap": 32,
                 "axisLabel": {**(axis.get("axisLabel") or {}), "fontSize": 10, "showMinLabel": True, "showMaxLabel": True}})
    month_labels = {}
    for date in dates:
        try:
            month_labels[str(date)] = datetime.fromisoformat(str(date)).strftime("%b %Y")
        except ValueError:
            pass
    axis["_monthYearLabels"] = month_labels
    y_axis = option.get("yAxis") or {}
    y_axis.pop("min", None)
    y_axis.pop("max", None)
    y_axis["scale"] = True
    item["smooth"] = False
    option.update({"xAxis": axis, "yAxis": y_axis, "series": series,
                   "grid": {"left": 44, "right": 24, "top": 44, "bottom": 64, "containLabel": True},
                   "_line_start_presentation": True})
    result["echarts_option"] = option
    from app.analytics.chart_specs import build_visual_spec
    result["visual_spec"] = build_visual_spec(result)
    return result
