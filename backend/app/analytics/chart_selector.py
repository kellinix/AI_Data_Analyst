"""
Chart selector: automatically picks the best chart for each data pattern.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.analytics.kpi_detector import is_outcome_column, uses_average_aggregation
from app.analytics.text_matching import is_unreported_category

# A numeric column null on more than this fraction of rows is sparse/
# optional data (e.g. a field only some records ever populate), not a
# continuous series — charting it as a smoothed line would visually imply
# a trend between points that don't actually exist.
_SPARSE_METRIC_NULL_RATIO = 0.7


def _is_sparse_numeric_column(column: str, numeric_stats: dict[str, Any]) -> bool:
    stats = numeric_stats.get(column) or {}
    count = stats.get("count") or 0
    null_count = stats.get("null_count") or 0
    total = count + null_count
    if total == 0:
        return False
    return (null_count / total) > _SPARSE_METRIC_NULL_RATIO


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

    date_cols = [
        col for col in date_cols if _has_usable_time_axis(col, date_range, numeric_stats, numeric_cols)
    ]

    if date_cols and numeric_cols:
        date_col = date_cols[0]
        dense_cols = [c for c in numeric_cols[:3] if not _is_sparse_numeric_column(c, numeric_stats)]
        if len(dense_cols) >= 2 and _comparable_scales(dense_cols, numeric_stats):
            charts.append(_multi_line_chart(date_col, dense_cols))
        primary_metric = numeric_cols[0]
        if _is_sparse_numeric_column(primary_metric, numeric_stats):
            charts.append(_sparse_metric_over_time_chart(date_col, primary_metric))
        else:
            charts.append(_time_series_chart(date_col, primary_metric))

    # A binary outcome column (e.g. "target") is the story of the dataset:
    # show its overall split and how its rate varies across the top dimension.
    outcome_cols = [
        c["name"]
        for c in schema
        if c["is_numeric"]
        and c.get("analysis_role") == "flag"
        and is_outcome_column(_normalize(c["name"]))
    ]
    if outcome_cols:
        outcome = outcome_cols[0]
        outcome_stats = categorical_stats.get(outcome, {})
        if len(outcome_stats.get("top_values", [])) >= 2:
            charts.append(_donut_chart(outcome, outcome_stats["top_values"]))
        if categorical_cols:
            charts.append(_outcome_rate_bar_chart(categorical_cols[0], outcome))

    # When outcome charts claimed slots, trim the repetitive bar variants so
    # the scatter and histogram still fit within max_charts.
    bar_budget = 2 if charts else 3

    if categorical_cols and numeric_cols:
        primary_category = categorical_cols[0]
        for numeric_col in numeric_cols[:bar_budget]:
            charts.append(_horizontal_bar_chart(primary_category, numeric_col))
            if len(charts) >= max_charts:
                break

    for cat_col in categorical_cols[:bar_budget]:
        cat_stats = categorical_stats.get(cat_col, {})
        top_values = cat_stats.get("top_values", [])
        if len(top_values) >= 2 and numeric_cols and not any(chart.get("xAxis") == numeric_cols[0] and chart.get("yAxis") == cat_col for chart in charts):
            charts.append(_horizontal_bar_chart(cat_col, numeric_cols[0], top_values))
        if len(charts) >= max_charts:
            break

    # A measure split by status across the leading dimension: "cost by
    # department, by delivery confidence" in one chart rather than two.
    status_col = _status_dimension(categorical_cols, categorical_stats)
    if status_col and categorical_cols and numeric_cols and len(charts) < max_charts:
        primary_category = next((col for col in categorical_cols if col != status_col), None)
        if primary_category:
            charts.append(_stacked_bar_chart(primary_category, numeric_cols[0], status_col))

    for cat_col in categorical_cols:
        cat_stats = categorical_stats.get(cat_col, {})
        top_values = cat_stats.get("top_values", [])
        unique_count = cat_stats.get("unique_count", 0)
        if 2 <= unique_count <= 8 and len(top_values) >= 2:
            charts.append(_donut_chart(cat_col, top_values))
            break

    if correlations:
        # Only scatter true metrics: correlations are computed over every
        # numeric column, including categorical codes (role "dimension"/
        # "flag"), and a scatter of two coded columns is a meaningless grid.
        metric_columns = set(numeric_cols)
        valid_correlations = [
            (pair, value)
            for pair, value in correlations.items()
            if all(column in metric_columns for column in pair.split("|"))
        ]
        if valid_correlations:
            top_corr = max(valid_correlations, key=lambda item: abs(item[1]))
            col_a, col_b = top_corr[0].split("|")
            charts.append(_scatter_chart(col_a, col_b, top_corr[1]))

    if numeric_cols:
        charts.append(_histogram_chart(numeric_cols[0], numeric_stats.get(numeric_cols[0], {})))

    return charts[:max_charts]


# Rows per month of span below which a date column is a scatter of dates
# rather than a reporting period. Mirrors forecasting._MIN_MONTHLY_DENSITY.
_MIN_TIME_AXIS_DENSITY = 0.6


def _has_usable_time_axis(
    date_col: str,
    date_range: dict[str, Any],
    numeric_stats: dict[str, Any],
    numeric_cols: list[str],
) -> bool:
    """Whether plotting against this date column says anything.

    A project portfolio's end dates run from 2023 to 2045: charting cost "over
    time" against them draws a line across 23 years of scattered points. Dates
    that are genuinely a reporting period have many rows per month.
    """
    bounds = (date_range or {}).get(date_col) or {}
    first, last = _year_month(bounds.get("min")), _year_month(bounds.get("max"))
    if first is None or last is None:
        return True
    span_months = (last[0] - first[0]) * 12 + (last[1] - first[1]) + 1
    if span_months <= 1:
        return True
    rows = max(
        [int((numeric_stats.get(col) or {}).get("count") or 0) for col in numeric_cols] or [0]
    )
    if not rows:
        return True
    return rows / span_months >= _MIN_TIME_AXIS_DENSITY


def _year_month(value: Any) -> tuple[int, int] | None:
    text = str(value or "")
    if len(text) < 7 or not text[:4].isdigit() or not text[5:7].isdigit():
        return None
    return int(text[:4]), int(text[5:7])


def _normalize(value: str) -> str:
    return value.lower().replace(" ", "_")


def _is_business_metric(column: str) -> bool:
    normalized = _normalize(column)
    parts = set(normalized.split("_"))
    return not (
        normalized == "year"
        or normalized.endswith("_year")
        or "date" in parts
        or "time" in parts
        or "timestamp" in parts
        or "age" in parts
        or "latitude" in parts
        or "longitude" in parts
        or "coord" in parts
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
    # A real business dimension outranks the file a row came from. Charting
    # "cost by source file" when the data has departments buries the answer —
    # a six-department portfolio produced a single-bar "by Source File" chart.
    if any(term in normalized for term in (
        "department", "ministry", "agency", "company", "organisation", "organization",
        "sponsor", "therapy", "area", "type", "phase", "status", "country", "region",
        "category", "segment", "channel", "team", "owner", "product",
    )):
        score += 10
    if normalized in {"source_file", "source file"}:
        score += 3
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


def _aggregation(column: str) -> str:
    """Shared with the KPI tiles, so a chart never averages what its tile sums."""
    return "average" if uses_average_aggregation(column) else "sum"


def _comparable_scales(columns: list[str], numeric_stats: dict[str, Any]) -> bool:
    values = [abs(float((numeric_stats.get(c) or {}).get("mean") or 0)) for c in columns]
    positive = [value for value in values if value > 0]
    return len(positive) >= 2 and max(positive) / min(positive) <= 10


def _time_series_chart(date_col: str, value_col: str) -> dict[str, Any]:
    value_label = _humanize(value_col)
    date_label = _humanize(date_col)
    aggregation = _aggregation(value_col)
    aggregation_label = "Total" if aggregation == "sum" else "Average"
    return {
        "id": _chart_id(),
        "type": "line",
        "title": f"{aggregation_label} {value_label} over time",
        "description": f"Shows the {aggregation} {value_label.lower()} for each {date_label.lower()}",
        "xAxis": date_col,
        "yAxis": value_col,
        "series": [value_col],
        "color_scheme": ["#2563eb"],
        # Kept at the top level (not just inside echarts_option._columns,
        # which chart-data population strips out) so the semantic-wrangler
        # title regeneration step can still tell sum from average.
        "aggregation": aggregation,
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
            "_columns": {"x": date_col, "y": value_col, "aggregation": aggregation},
        },
    }


def _sparse_metric_over_time_chart(date_col: str, value_col: str) -> dict[str, Any]:
    """Same data query as _time_series_chart (chronological, non-null values
    only) but rendered as disconnected markers rather than a smoothed line —
    a metric that's null on most rows has no real trend to connect between
    the handful of dates it does have a value on.
    """
    value_label = _humanize(value_col)
    date_label = _humanize(date_col)
    return {
        "id": _chart_id(),
        "type": "line",
        "title": f"{value_label} over time",
        "description": f"Shows the individual {value_label.lower()} entries recorded across {date_label.lower()} — most rows have no value for this field",
        "xAxis": date_col,
        "yAxis": value_col,
        "series": [value_col],
        "color_scheme": ["#2563eb"],
        "echarts_option": {
            "tooltip": {"trigger": "item"},
            "xAxis": {"type": "category", "name": date_col},
            "yAxis": {"type": "value", "name": value_col},
            "series": [{
                "type": "line",
                "smooth": False,
                "showSymbol": True,
                "symbol": "circle",
                "symbolSize": 9,
                "name": value_col,
                "lineStyle": {"opacity": 0},
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
            "_columns": {"x": date_col, "ys": value_cols, "aggregations": [_aggregation(c) for c in value_cols]},
        },
    }


def _horizontal_bar_chart(cat_col: str, value_col: str, top_values: list[dict] | None = None) -> dict[str, Any]:
    top_values = top_values or []
    labels = [str(v["value"]) for v in top_values[:10]]
    cat_label = _humanize(cat_col)
    value_label = _humanize(value_col)
    aggregation = _aggregation(value_col)
    aggregation_word = "total" if aggregation == "sum" else "average"
    title = f"{value_label} by {cat_label}" if aggregation == "sum" else f"Avg {value_label} by {cat_label}"
    return {
        "id": _chart_id(),
        "type": "bar",
        "title": title,
        "description": f"Compares the {aggregation_word} {value_label.lower()} across each {cat_label.lower()}",
        "xAxis": value_col,
        "yAxis": cat_col,
        "series": [value_col],
        "color_scheme": ["#2563eb"],
        "aggregation": aggregation,
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
            "_columns": {"x": cat_col, "y": value_col, "orientation": "horizontal", "aggregation": aggregation},
        },
    }


def _status_dimension(
    categorical_cols: list[str], categorical_stats: dict[str, Any]
) -> str | None:
    """A small set of states each record is in — RAG rating, stage, status.

    Splitting a measure by one of these is the question a portfolio review
    actually asks ("how much of our spend is rated Red?").

    Judged on the values that carry information rather than the raw distinct
    count: the GMPP delivery-confidence column holds five real RAG states plus
    six separate FOI-exemption sentences, so a plain 2..8 count saw 11 and hid
    the chart. Requiring retained top values also excludes the free-text
    commentary column named "...on_the_ipa_rag_rating", which matches the
    keywords but holds 117 distinct paragraphs.
    """
    for column in categorical_cols:
        normalized = _normalize(column)
        if not any(
            term in normalized
            for term in ("status", "rag", "rating", "confidence", "stage", "phase", "severity", "priority")
        ):
            continue
        top_values = (categorical_stats.get(column) or {}).get("top_values") or []
        meaningful = {
            str(item.get("value"))
            for item in top_values
            if isinstance(item, dict) and not is_unreported_category(str(item.get("value")))
        }
        if 2 <= len(meaningful) <= 8:
            return column
    return None


def _stacked_bar_chart(cat_col: str, value_col: str, series_col: str) -> dict[str, Any]:
    cat_label = _humanize(cat_col)
    value_label = _humanize(value_col)
    series_label = _humanize(series_col)
    aggregation = _aggregation(value_col)
    aggregation_word = "total" if aggregation == "sum" else "average"
    return {
        "id": _chart_id(),
        "type": "bar",
        "title": f"{value_label} by {cat_label} and {series_label}",
        "description": f"Splits the {aggregation_word} {value_label.lower()} in each {cat_label.lower()} by {series_label.lower()}",
        "xAxis": cat_col,
        "yAxis": value_col,
        "series": [series_col],
        # Top level, not just in `_columns`: chart-data population strips the
        # `_columns` hint before the display layer retitles the chart.
        "series_by": series_col,
        "color_scheme": ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"],
        "aggregation": aggregation,
        "echarts_option": {
            "tooltip": {"trigger": "axis"},
            "legend": {"show": True, "bottom": 0},
            "xAxis": {"type": "category", "name": cat_col, "data": []},
            "yAxis": {"type": "value", "name": value_col},
            "series": [],
            "_columns": {
                "x": cat_col,
                "y": value_col,
                "series_by": series_col,
                "aggregation": aggregation,
            },
        },
    }


def _outcome_rate_bar_chart(cat_col: str, outcome_col: str) -> dict[str, Any]:
    """Share of positive outcomes (mean of a 0/1 flag, as %) per category."""
    cat_label = _humanize(cat_col)
    outcome_label = _humanize(outcome_col)
    return {
        "id": _chart_id(),
        "type": "bar",
        "title": f"{outcome_label} rate by {cat_label}",
        "description": f"Share of records with {outcome_label.lower()} = 1 in each {cat_label.lower()} group",
        "xAxis": outcome_col,
        "yAxis": cat_col,
        "series": [outcome_col],
        "color_scheme": ["#8b5cf6"],
        "aggregation": "percent_rate",
        "echarts_option": {
            "grid": {"left": 112, "right": 20, "top": 16, "bottom": 24},
            "xAxis": {"type": "value", "name": f"{outcome_label} rate (%)"},
            "yAxis": {"type": "category", "data": []},
            "series": [{
                "type": "bar",
                "data": [],
                "itemStyle": {"borderRadius": [0, 6, 6, 0]},
                "name": outcome_col,
            }],
            "_columns": {"x": cat_col, "y": outcome_col, "orientation": "horizontal", "aggregation": "percent_rate"},
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


def _relationship_strength(correlation: float) -> str:
    magnitude = abs(correlation)
    if magnitude >= 0.7:
        return "strong"
    if magnitude >= 0.4:
        return "moderate"
    return "weak"


def _scatter_chart(col_a: str, col_b: str, correlation: float) -> dict[str, Any]:
    direction = "rise together" if correlation > 0 else "move in opposite directions"
    label_a = _humanize(col_a)
    label_b = _humanize(col_b)
    strength = _relationship_strength(correlation)
    return {
        "id": _chart_id(),
        "type": "scatter",
        "title": f"{label_a} vs {label_b}",
        "description": f"A {strength} relationship: as {label_a.lower()} changes, {label_b.lower()} tends to {direction}",
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
        "pct": "%",
        "km": "km",
        "kmh": "km/h",
    }
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in value.replace("_", " ").split()
    )
