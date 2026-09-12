"""
Strict visual specification contract for dashboard charts.

The AI must never generate frontend code. Charts are represented as bounded
Vega-Lite-style JSON specs that the frontend renders through a fixed wrapper.
"""

from __future__ import annotations

from typing import Any

VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"


def attach_visual_specs(charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**chart, "visual_spec": build_visual_spec(chart)} for chart in charts]


def build_visual_spec(chart: dict[str, Any]) -> dict[str, Any]:
    chart_type = chart.get("type")
    if chart_type == "line":
        return _line_spec(chart)
    if chart_type == "bar":
        return _bar_spec(chart)
    if chart_type == "donut":
        return _arc_spec(chart)
    if chart_type == "scatter":
        return _scatter_spec(chart)
    if chart_type == "histogram":
        return _histogram_spec(chart)
    return _empty_spec(chart)


def _axis_title(chart: dict[str, Any], axis: str) -> Any:
    """The human label for an axis, falling back to the raw column name.

    `apply_display_metadata_to_charts` writes decoded labels onto the ECharts
    axes, but the frontend renders *this* spec — so without carrying them over,
    charts were labelled `financial_year_baseline_currency_m_including_non_...`.
    """
    option = _object(chart.get("echarts_option"))
    name = _object(option.get(f"{axis}Axis")).get("name")
    if isinstance(name, str) and name.strip():
        return name
    return chart.get(f"{axis}Axis")


def _base_spec(chart: dict[str, Any], mark: str | dict[str, Any], values: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "spec_version": "1.0",
        "renderer": "safe-chart-wrapper",
        "title": chart.get("title"),
        "description": chart.get("description"),
        "mark": mark,
        "data": {"values": values[:1_000]},
        "encoding": {},
    }


def _line_spec(chart: dict[str, Any]) -> dict[str, Any]:
    opt = _object(chart.get("echarts_option"))
    x_axis = _object(opt.get("xAxis"))
    x_values = [str(value) for value in _list(x_axis.get("data"))]
    series_items = [_object(item) for item in _list(opt.get("series"))]
    rows: list[dict[str, Any]] = []
    for series in series_items:
        metric = str(series.get("name") or chart.get("yAxis") or "value")
        for index, value in enumerate(_list(series.get("data"))):
            if index < len(x_values):
                rows.append(
                    {
                        "period": x_values[index],
                        "metric": metric,
                        "value": _number(value),
                    }
                )

    spec = _base_spec(chart, {"type": "line", "tooltip": True}, rows)
    spec["encoding"] = {
        "x": {"field": "period", "type": "ordinal", "title": _axis_title(chart, "x")},
        "y": {"field": "value", "type": "quantitative", "title": _axis_title(chart, "y") or "Value"},
        "color": {"field": "metric", "type": "nominal", "title": None},
        "tooltip": [
            {"field": "period", "type": "ordinal"},
            {"field": "metric", "type": "nominal"},
            {"field": "value", "type": "quantitative"},
        ],
    }
    return spec


def _bar_spec(chart: dict[str, Any]) -> dict[str, Any]:
    opt = _object(chart.get("echarts_option"))
    if _object(opt.get("_columns")).get("series_by"):
        return _stacked_bar_spec(chart)
    x_axis = _object(opt.get("xAxis"))
    y_axis = _object(opt.get("yAxis"))
    series = _object(_first(_list(opt.get("series"))))
    horizontal = y_axis.get("type") == "category"
    labels = [str(value) for value in _list((y_axis if horizontal else x_axis).get("data"))]
    values = [_number(value) for value in _list(series.get("data"))]
    rows = [
        {"category": label, "value": values[index] if index < len(values) else 0}
        for index, label in enumerate(labels)
    ]

    spec = _base_spec(chart, {"type": "bar", "tooltip": True}, rows)
    spec["encoding"] = {
        "x": {"field": "value", "type": "quantitative", "title": _axis_title(chart, "x")},
        "y": {
            "field": "category",
            "type": "nominal",
            "title": _axis_title(chart, "y"),
            "sort": "-x",
        },
        "tooltip": [
            {"field": "category", "type": "nominal"},
            {"field": "value", "type": "quantitative"},
        ],
    }
    if not horizontal:
        spec["encoding"]["x"], spec["encoding"]["y"] = spec["encoding"]["y"], spec["encoding"]["x"]
    return spec


def _stacked_bar_spec(chart: dict[str, Any]) -> dict[str, Any]:
    """One bar per category, split into a segment per series value."""
    opt = _object(chart.get("echarts_option"))
    categories = [str(value) for value in _list(_object(opt.get("xAxis")).get("data"))]
    rows: list[dict[str, Any]] = []
    for item in _list(opt.get("series")):
        series = _object(item)
        name = str(series.get("name") or "")
        for index, value in enumerate(_list(series.get("data"))):
            if index < len(categories):
                rows.append({"category": categories[index], "series": name, "value": _number(value)})

    spec = _base_spec(chart, {"type": "bar", "tooltip": True}, rows)
    spec["encoding"] = {
        "x": {"field": "category", "type": "nominal", "title": _axis_title(chart, "x")},
        "y": {"field": "value", "type": "quantitative", "title": _axis_title(chart, "y"), "stack": "zero"},
        "color": {"field": "series", "type": "nominal", "title": None},
        "tooltip": [
            {"field": "category", "type": "nominal"},
            {"field": "series", "type": "nominal"},
            {"field": "value", "type": "quantitative"},
        ],
    }
    return spec


def _arc_spec(chart: dict[str, Any]) -> dict[str, Any]:
    opt = _object(chart.get("echarts_option"))
    series = _object(_first(_list(opt.get("series"))))
    rows = [
        {"category": str(item.get("name")), "value": _number(item.get("value"))}
        for item in (_object(value) for value in _list(series.get("data")))
        if item.get("name") is not None
    ]
    spec = _base_spec(chart, {"type": "arc", "innerRadius": 70, "tooltip": True}, rows)
    spec["encoding"] = {
        "theta": {"field": "value", "type": "quantitative"},
        "color": {"field": "category", "type": "nominal"},
        "tooltip": [
            {"field": "category", "type": "nominal"},
            {"field": "value", "type": "quantitative"},
        ],
    }
    return spec


def _scatter_spec(chart: dict[str, Any]) -> dict[str, Any]:
    opt = _object(chart.get("echarts_option"))
    series = _object(_first(_list(opt.get("series"))))
    rows = [
        {"x": _number(point[0]), "y": _number(point[1])}
        for point in _list(series.get("data"))
        if isinstance(point, list) and len(point) >= 2
    ]
    spec = _base_spec(chart, {"type": "point", "tooltip": True}, rows)
    x_encoding: dict[str, Any] = {
        "field": "x", "type": "quantitative", "title": _axis_title(chart, "x")
    }
    y_encoding: dict[str, Any] = {
        "field": "y", "type": "quantitative", "title": _axis_title(chart, "y")
    }
    # The populator decides this: an axis spanning orders of magnitude draws
    # every point in one corner on a linear scale.
    scale = _object(opt.get("_scale"))
    if scale.get("x"):
        x_encoding["scale"] = {"type": "log"}
    if scale.get("y"):
        y_encoding["scale"] = {"type": "log"}
    spec["encoding"] = {
        "x": x_encoding,
        "y": y_encoding,
        "tooltip": [
            {"field": "x", "type": "quantitative"},
            {"field": "y", "type": "quantitative"},
        ],
    }
    return spec


def _histogram_spec(chart: dict[str, Any]) -> dict[str, Any]:
    opt = _object(chart.get("echarts_option"))
    x_axis = _object(opt.get("xAxis"))
    series = _object(_first(_list(opt.get("series"))))
    labels = [str(value) for value in _list(x_axis.get("data"))]
    values = [_number(value) for value in _list(series.get("data"))]
    rows = [
        {"bucket": label, "count": values[index] if index < len(values) else 0}
        for index, label in enumerate(labels)
    ]
    spec = _base_spec(chart, {"type": "bar", "tooltip": True}, rows)
    spec["encoding"] = {
        "x": {"field": "bucket", "type": "ordinal", "title": _axis_title(chart, "x")},
        "y": {"field": "count", "type": "quantitative", "title": "Count"},
        "tooltip": [
            {"field": "bucket", "type": "ordinal"},
            {"field": "count", "type": "quantitative"},
        ],
    }
    return spec


def _empty_spec(chart: dict[str, Any]) -> dict[str, Any]:
    return _base_spec(chart, {"type": "bar"}, [])


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first(values: list[Any]) -> Any:
    return values[0] if values else {}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
