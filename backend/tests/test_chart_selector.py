from __future__ import annotations

from app.analytics.chart_selector import select_charts


def test_chart_selector_ignores_numeric_attributes():
    schema = [
        {"name": "department", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
        {"name": "employee_id", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "age", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "latitude", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "revenue", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    categorical_stats = {
        "department": {
            "unique_count": 4,
            "top_values": [
                {"value": "Sales", "count": 100},
                {"value": "Support", "count": 80},
            ],
        }
    }
    numeric_stats = {
        "age": {"total": 1200},
        "employee_id": {"total": 900},
        "latitude": {"total": 9000},
        "revenue": {"total": 50000},
    }

    charts = select_charts(schema, numeric_stats, categorical_stats, {}, {})
    chart_axes = {(chart.get("xAxis"), chart.get("yAxis")) for chart in charts}

    assert ("age", "department") not in chart_axes
    assert ("employee_id", "department") not in chart_axes
    assert ("latitude", "department") not in chart_axes
    assert ("revenue", "department") in chart_axes


TIME_SCHEMA = [
    {"name": "period_date", "is_numeric": False, "is_date": True, "analysis_role": "temporal_dimension"},
    {"name": "revenue", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
]


def test_dates_scattered_across_decades_are_not_charted_over_time():
    """Regression: project end dates running 2023-2045 produced a "costs over
    time" line across 23 years of scattered points."""
    date_range = {"period_date": {"min": "2023-01-27 00:00:00", "max": "2045-12-29 00:00:00"}}
    numeric_stats = {"revenue": {"count": 106, "total": 244568.0}}

    charts = select_charts(TIME_SCHEMA, numeric_stats, {}, date_range, {})

    assert not [c for c in charts if c.get("xAxis") == "period_date"]


def test_a_real_reporting_period_still_gets_its_time_chart():
    date_range = {"period_date": {"min": "2025-02-03 00:00:00", "max": "2026-07-27 00:00:00"}}
    numeric_stats = {"revenue": {"count": 936, "total": 12285143.0}}

    charts = select_charts(TIME_SCHEMA, numeric_stats, {}, date_range, {})

    assert [c for c in charts if c.get("xAxis") == "period_date"]


def test_real_dimensions_outrank_the_source_file_column():
    """Regression: source_file scored +20 against +10 for a business dimension,
    so a six-department portfolio was charted "by Source File" — one bar,
    labelled with a filename."""
    schema = [
        {"name": "source_file", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
        {"name": "department", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
        {"name": "whole_life_cost", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    categorical_stats = {
        "source_file": {
            "unique_count": 6,
            "top_values": [{"value": "MOD.xlsx", "count": 49}, {"value": "DFT.xlsx", "count": 19}],
        },
        "department": {
            "unique_count": 6,
            "top_values": [{"value": "MOD", "count": 49}, {"value": "DFT", "count": 19}],
        },
    }
    numeric_stats = {"whole_life_cost": {"count": 118, "total": 244568.0}}

    charts = select_charts(schema, numeric_stats, categorical_stats, {}, {})
    first_bar = next(chart for chart in charts if chart["type"] == "bar")

    assert first_bar["yAxis"] == "department"


def test_bar_charts_average_non_additive_metrics():
    """Grouping a measurement like blood pressure by category must average it —
    a SUM per group just mirrors group sizes."""
    schema = [
        {"name": "cp", "is_numeric": True, "is_date": False, "analysis_role": "dimension"},
        {"name": "trestbps", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    categorical_stats = {
        "cp": {"unique_count": 4, "top_values": [{"value": "0", "count": 500}, {"value": "2", "count": 280}]},
    }
    numeric_stats = {"trestbps": {"count": 1025, "mean": 131.6}}

    charts = select_charts(schema, numeric_stats, categorical_stats, {}, {})
    bar = next(c for c in charts if c["type"] == "bar" and c["yAxis"] == "cp")

    assert bar["echarts_option"]["_columns"]["aggregation"] == "average"
    assert bar["title"].startswith("Avg ")


def test_outcome_flag_gets_donut_and_rate_charts():
    """A binary outcome column (e.g. 'target') must be surfaced: overall
    split plus its rate across the leading dimension."""
    schema = [
        {"name": "cp", "is_numeric": True, "is_date": False, "analysis_role": "dimension"},
        {"name": "target", "is_numeric": True, "is_date": False, "analysis_role": "flag"},
        {"name": "chol", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    categorical_stats = {
        "cp": {"unique_count": 4, "top_values": [{"value": "0", "count": 500}, {"value": "2", "count": 280}]},
        "target": {"unique_count": 2, "top_values": [{"value": "1", "count": 526}, {"value": "0", "count": 499}]},
    }
    numeric_stats = {"chol": {"count": 1025, "mean": 246.0}}

    charts = select_charts(schema, numeric_stats, categorical_stats, {}, {})

    donut = next(c for c in charts if c["type"] == "donut")
    assert donut["series"] == ["target"]

    rate_chart = next(
        c for c in charts
        if c["type"] == "bar" and c["echarts_option"]["_columns"].get("aggregation") == "percent_rate"
    )
    assert rate_chart["echarts_option"]["_columns"]["y"] == "target"
    assert rate_chart["echarts_option"]["_columns"]["x"] == "cp"


def test_sparse_metric_over_time_uses_disconnected_markers_not_a_smoothed_line():
    """A numeric metric that's null on most rows (e.g. an optional field only
    a handful of records ever populate) must not be charted as a smoothed
    line — that visually implies a continuous trend between points that
    don't exist. Regression test for a real-world case where 112 of 115
    rows had no 'hours of work' value.
    """
    schema = [
        {"name": "created_at", "is_numeric": False, "is_date": True, "analysis_role": "temporal_dimension"},
        {"name": "hours_of_work", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    numeric_stats = {
        "hours_of_work": {"count": 3, "null_count": 112, "total": 56.0},
    }

    charts = select_charts(schema, numeric_stats, {}, {}, {})
    time_chart = next(c for c in charts if c.get("xAxis") == "created_at" and c.get("yAxis") == "hours_of_work")

    series = time_chart["echarts_option"]["series"][0]
    assert series["type"] == "line"
    assert series["smooth"] is False
    assert series["lineStyle"]["opacity"] == 0
    assert series["showSymbol"] is True


def test_dense_metric_over_time_still_uses_a_smoothed_line():
    schema = [
        {"name": "created_at", "is_numeric": False, "is_date": True, "analysis_role": "temporal_dimension"},
        {"name": "revenue", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    numeric_stats = {
        "revenue": {"count": 100, "null_count": 2, "total": 50000.0},
    }

    charts = select_charts(schema, numeric_stats, {}, {}, {})
    time_chart = next(c for c in charts if c.get("xAxis") == "created_at" and c.get("yAxis") == "revenue")

    series = time_chart["echarts_option"]["series"][0]
    assert series["smooth"] is True
    assert "opacity" not in series.get("lineStyle", {})
