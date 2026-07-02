"""
Chart selector: automatically picks the best chart for each data pattern.
"""

from __future__ import annotations

import uuid
from typing import Any


def select_charts(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
    categorical_stats: dict[str, Any],
    date_range: dict[str, Any],
    correlations: dict[str, float],
    max_charts: int = 8,
) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []

    date_cols = [
        c["name"]
        for c in schema
        if c["is_date"] or c.get("analysis_role") == "temporal_dimension"
    ]
    numeric_cols = [
        c["name"]
        for c in schema
        if c["is_numeric"]
        and c.get("analysis_role") == "metric"
        and _is_business_metric(c["name"])
    ]
    categorical_cols = sorted(
        [
            c["name"]
            for c in schema
            if _is_chart_dimension(c, categorical_stats)
        ],
        key=lambda col: _dimension_score(col, categorical_stats),
        reverse=True,
    )

    if date_cols and numeric_cols:
        date_col = date_cols[0]
        if len(numeric_cols) >= 2:
            charts.append(_multi_line_chart(date_col, numeric_cols[:3]))
        charts.append(_time_series_chart(date_col, numeric_cols[0]))

    if categorical_cols and numeric_cols:
        primary_category = categorical_cols[0]
        for numeric_col in numeric_cols[:3]:
            charts.append(_horizontal_bar_chart(primary_category, numeric_col))
            if len(charts) >= max_charts:
                break

    for cat_col in categorical_cols[:3]:
        cat_stats = categorical_stats.get(cat_col, {})
        top_values = cat_stats.get("top_values", [])
        if len(top_values) >= 2 and numeric_cols and not any(chart.get("xAxis") == numeric_cols[0] and chart.get("yAxis") == cat_col for chart in charts):
            charts.append(_horizontal_bar_chart(cat_col, numeric_cols[0], top_values))
        if len(charts) >= max_charts:
            break

    for cat_col in categorical_cols:
        cat_stats = categorical_stats.get(cat_col, {})
        top_values = cat_stats.get("top_values", [])
        unique_count = cat_stats.get("unique_count", 0)
        if 2 <= unique_count <= 8 and len(top_values) >= 2:
            charts.append(_donut_chart(cat_col, top_values))
            break

    if correlations:
        valid_correlations = [
            (pair, value)
            for pair, value in correlations.items()
            if all(_is_business_metric(column) for column in pair.split("|"))
        ]
        if valid_correlations:
            top_corr = max(valid_correlations, key=lambda item: abs(item[1]))
            col_a, col_b = top_corr[0].split("|")
            charts.append(_scatter_chart(col_a, col_b, top_corr[1]))

    if numeric_cols:
        charts.append(_histogram_chart(numeric_cols[0], numeric_stats.get(numeric_cols[0], {})))

    return charts[:max_charts]


def _normalize(value: str) -> str:
    return value.lower().replace(" ", "_")


def _is_business_metric(column: str) -> bool:
    normalized = _normalize(column)
    parts = set(normalized.split("_"))
    return not (
        normalized in {"goals_team", "goals_opponent"}
        or normalized == "year"
        or normalized.endswith("_year")
        or "date" in parts
        or "time" in parts
        or "timestamp" in parts
        or "age" in parts
        or "height" in parts
        or "weight" in parts
        or "jersey" in parts
        or "latitude" in parts
        or "longitude" in parts
        or "coord" in parts
        or "shirt_number" in normalized
        or "squad_number" in normalized
        or normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("id_")
        or normalized.startswith("is_")
        or normalized.startswith("has_")
    )


def _is_chart_dimension(
    column: dict[str, Any],
    categorical_stats: dict[str, Any],
) -> bool:
    role = column.get("analysis_role")
    if role not in {"dimension", "temporal_dimension"}:
        return False

    normalized = _normalize(column["name"])
    if (
        normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("id_")
        or "description" in normalized
        or normalized in {"summary", "title", "headline"}
    ):
        return False

    stats = categorical_stats.get(column["name"], {})
    unique_count = stats.get("unique_count", 0)
    if unique_count and unique_count > 500:
        return False
    return True


def _dimension_score(column: str, categorical_stats: dict[str, Any]) -> float:
    normalized = _normalize(column)
    score = 0.0
    if normalized in {"source_file", "source file"}:
        score += 20
    if any(term in normalized for term in ("company", "organisation", "organization", "sponsor", "therapy", "area", "type", "phase", "status", "country", "category")):
        score += 10
    if normalized == "year" or normalized.endswith("_year"):
        score += 6
    unique_count = categorical_stats.get(column, {}).get("unique_count", 0)
    if 2 <= unique_count <= 30:
        score += 4
    elif 31 <= unique_count <= 100:
        score += 2
    return score


def _chart_id() -> str:
    return str(uuid.uuid4())[:8]


def _time_series_chart(date_col: str, value_col: str) -> dict[str, Any]:
    value_label = _humanize(value_col)
    date_label = _humanize(date_col)
    return {
        "id": _chart_id(),
        "type": "line",
        "title": f"{value_label} over time",
        "description": f"Shows how {value_label.lower()} changes across {date_label.lower()}",
        "xAxis": date_col,
        "yAxis": value_col,
        "series": [value_col],
        "color_scheme": ["#2563eb"],
        "echarts_option": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "name": date_col},
            "yAxis": {"type": "value", "name": value_col},
            "series": [{
                "type": "line",
                "smooth": True,
                "areaStyle": {"opacity": 0.08},
                "name": value_col,
                "symbol": "none",
                "lineStyle": {"width": 2},
            }],
            "_columns": {"x": date_col, "y": value_col},
        },
    }


def _multi_line_chart(date_col: str, value_cols: list[str]) -> dict[str, Any]:
    date_label = _humanize(date_col)
    return {
        "id": _chart_id(),
        "type": "line",
        "title": "Key metrics over time",
        "description": f"Shows selected measures across {date_label.lower()}",
        "xAxis": date_col,
        "yAxis": "metrics",
        "series": value_cols,
        "color_scheme": ["#2563eb", "#10b981", "#f59e0b"],
        "echarts_option": {
            "tooltip": {"trigger": "axis"},
            "legend": {"show": True, "bottom": 0},
            "xAxis": {"type": "category", "name": date_col},
            "yAxis": {"type": "value"},
            "series": [
                {
                    "type": "line",
                    "smooth": True,
                    "name": col,
                    "symbol": "none",
                    "lineStyle": {"width": 2},
                }
                for col in value_cols
            ],
            "_columns": {"x": date_col, "ys": value_cols},
        },
    }


def _horizontal_bar_chart(cat_col: str, value_col: str, top_values: list[dict] | None = None) -> dict[str, Any]:
    top_values = top_values or []
    labels = [str(v["value"]) for v in top_values[:10]]
    cat_label = _humanize(cat_col)
    value_label = _humanize(value_col)
    return {
        "id": _chart_id(),
        "type": "bar",
        "title": f"{value_label} by {cat_label}",
        "description": f"Compares {value_label.lower()} across {cat_label.lower()}",
        "xAxis": value_col,
        "yAxis": cat_col,
        "series": [value_col],
        "color_scheme": ["#2563eb"],
        "echarts_option": {
            "grid": {"left": 112, "right": 20, "top": 16, "bottom": 24},
            "xAxis": {"type": "value"},
            "yAxis": {"type": "category", "data": labels[::-1]},
            "series": [{
                "type": "bar",
                "data": [v["count"] for v in top_values[:10]][::-1],
                "itemStyle": {"borderRadius": [0, 6, 6, 0]},
                "name": value_col,
            }],
            "_columns": {"x": cat_col, "y": value_col, "orientation": "horizontal"},
        },
    }


def _donut_chart(cat_col: str, top_values: list[dict]) -> dict[str, Any]:
    data = [{"value": v["count"], "name": str(v["value"])} for v in top_values]
    cat_label = _humanize(cat_col)
    return {
        "id": _chart_id(),
        "type": "donut",
        "title": f"{cat_label} distribution",
        "description": f"Share of records by {cat_label.lower()}",
        "xAxis": None,
        "yAxis": None,
        "series": [cat_col],
        "color_scheme": ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"],
        "echarts_option": {
            "tooltip": {"trigger": "item"},
            "series": [{
                "type": "pie",
                "radius": ["45%", "72%"],
                "data": data,
                "itemStyle": {"borderRadius": 8, "borderWidth": 2, "borderColor": "#fff"},
                "label": {"show": False},
            }],
            "_columns": {"category": cat_col},
        },
    }


def _scatter_chart(col_a: str, col_b: str, correlation: float) -> dict[str, Any]:
    direction = "positive" if correlation > 0 else "negative"
    return {
        "id": _chart_id(),
        "type": "scatter",
        "title": f"{col_a} vs {col_b}",
        "description": f"{direction.capitalize()} correlation (r={correlation:.2f})",
        "xAxis": col_a,
        "yAxis": col_b,
        "series": [col_a, col_b],
        "color_scheme": ["#2563eb"],
        "echarts_option": {
            "xAxis": {"type": "value", "name": col_a},
            "yAxis": {"type": "value", "name": col_b},
            "series": [{
                "type": "scatter",
                "symbolSize": 6,
                "itemStyle": {"opacity": 0.68},
                "name": f"{col_a} vs {col_b}",
            }],
            "_columns": {"x": col_a, "y": col_b},
        },
    }


def _histogram_chart(value_col: str, stats: dict[str, Any]) -> dict[str, Any]:
    value_label = _humanize(value_col)
    return {
        "id": _chart_id(),
        "type": "histogram",
        "title": f"{value_label} distribution",
        "description": "Distribution and spread of values",
        "xAxis": value_col,
        "yAxis": "count",
        "series": [value_col],
        "color_scheme": ["#14b8a6"],
        "echarts_option": {
            "xAxis": {"type": "category", "name": value_col},
            "yAxis": {"type": "value", "name": "Count"},
            "series": [{
                "type": "bar",
                "data": [],
                "itemStyle": {"borderRadius": [6, 6, 0, 0]},
                "name": value_col,
            }],
            "_columns": {"x": value_col, "min": stats.get("min"), "max": stats.get("max")},
        },
    }


def _humanize(value: str) -> str:
    replacements = {
        "xg": "xG",
        "xa": "xA",
        "pct": "%",
        "km": "km",
        "kmh": "km/h",
    }
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in value.replace("_", " ").split()
    )
