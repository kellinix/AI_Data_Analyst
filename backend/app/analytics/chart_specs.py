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
        "x": {"field": "period", "type": "ordinal", "title": chart.get("xAxis")},
        "y": {"field": "value", "type": "quantitative", "title": chart.get("yAxis") or "Value"},
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
        "x": {"field": "value", "type": "quantitative", "title": chart.get("xAxis")},
        "y": {
            "field": "category",
            "type": "nominal",
            "title": chart.get("yAxis"),
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
    spec["encoding"] = {
        "x": {"field": "x", "type": "quantitative", "title": chart.get("xAxis")},
        "y": {"field": "y", "type": "quantitative", "title": chart.get("yAxis")},
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
        "x": {"field": "bucket", "type": "ordinal", "title": chart.get("xAxis")},
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
