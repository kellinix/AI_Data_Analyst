from __future__ import annotations

from app.analytics.chart_specs import build_visual_spec


def test_build_visual_spec_returns_bounded_vega_lite_style_bar_spec() -> None:
    chart = {
        "id": "abc123",
        "type": "bar",
        "title": "Top Country by Revenue",
        "description": "Ranking of countries",
        "xAxis": "revenue",
        "yAxis": "country",
        "series": ["revenue"],
        "echarts_option": {
            "xAxis": {"type": "value"},
            "yAxis": {"type": "category", "data": ["United States", "Canada"]},
            "series": [{"type": "bar", "data": [120, 80], "name": "revenue"}],
        },
    }

    spec = build_visual_spec(chart)

    assert spec["$schema"] == "https://vega.github.io/schema/vega-lite/v5.json"
    assert spec["renderer"] == "safe-chart-wrapper"
    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["x"]["field"] == "value"
    assert spec["encoding"]["y"]["field"] == "category"
    assert spec["data"]["values"] == [
        {"category": "United States", "value": 120.0},
        {"category": "Canada", "value": 80.0},
    ]


def test_spec_axes_carry_the_decoded_labels() -> None:
    """Regression: the frontend renders this spec, and its encodings fell back
    to the raw column name — so a chart's axis read
    `financial_year_baseline_currency_m_including_non_government_costs`
    even though the decoded label was already on the ECharts option."""
    chart = {
        "type": "bar",
        "title": "Whole life cost by department",
        "xAxis": "total_baseline_whole_life_costs_currency_m_including_non_government_costs",
        "yAxis": "department",
        "series": ["total_baseline_whole_life_costs_currency_m_including_non_government_costs"],
        "echarts_option": {
            "xAxis": {"type": "value", "name": "Total Baseline Whole Life Costs (£m)"},
            "yAxis": {"type": "category", "name": "Department", "data": ["MOD", "DFT"]},
            "series": [{"type": "bar", "data": [117457, 67446]}],
        },
    }

    spec = build_visual_spec(chart)

    assert spec["encoding"]["x"]["title"] == "Total Baseline Whole Life Costs (£m)"
    assert spec["encoding"]["y"]["title"] == "Department"


def test_stacked_bar_spec_carries_a_colour_encoding() -> None:
    """Without the colour channel the frontend drew one anonymous series, so a
    cost-by-department-by-RAG chart rendered as a plain total."""
    chart = {
        "type": "bar",
        "title": "Whole life cost by department and delivery confidence",
        "xAxis": "department",
        "yAxis": "whole_life_cost",
        "series": ["delivery_confidence"],
        "echarts_option": {
            "xAxis": {"type": "category", "name": "Department", "data": ["MOD", "DFT"]},
            "yAxis": {"type": "value", "name": "Whole Life Cost (£m)"},
            "series": [
                {"type": "bar", "stack": "total", "name": "Amber", "data": [100, 60]},
                {"type": "bar", "stack": "total", "name": "Red", "data": [17, 7]},
            ],
            "_columns": {"x": "department", "y": "whole_life_cost", "series_by": "delivery_confidence"},
        },
    }

    spec = build_visual_spec(chart)

    assert spec["encoding"]["color"]["field"] == "series"
    assert spec["encoding"]["x"]["field"] == "category"
    assert spec["encoding"]["y"]["stack"] == "zero"
    assert spec["encoding"]["x"]["title"] == "Department"
    assert spec["encoding"]["y"]["title"] == "Whole Life Cost (£m)"
    assert spec["data"]["values"] == [
        {"category": "MOD", "series": "Amber", "value": 100.0},
        {"category": "DFT", "series": "Amber", "value": 60.0},
        {"category": "MOD", "series": "Red", "value": 17.0},
        {"category": "DFT", "series": "Red", "value": 7.0},
    ]


def test_spec_axis_titles_fall_back_to_the_column_name() -> None:
    chart = {
        "type": "scatter",
        "title": "Baseline vs forecast",
        "xAxis": "baseline",
        "yAxis": "forecast",
        "series": ["baseline"],
        "echarts_option": {
            "xAxis": {"type": "value"},
            "yAxis": {"type": "value"},
            "series": [{"type": "scatter", "data": [[1, 2], [3, 4]]}],
        },
    }

    spec = build_visual_spec(chart)

    assert spec["encoding"]["x"]["title"] == "baseline"
    assert spec["encoding"]["y"]["title"] == "forecast"


def test_build_visual_spec_limits_embedded_rows() -> None:
    chart = {
        "type": "histogram",
        "title": "Distribution",
        "xAxis": "value",
        "yAxis": "count",
        "series": ["value"],
        "echarts_option": {
            "xAxis": {"type": "category", "data": [str(index) for index in range(1_200)]},
            "series": [{"type": "bar", "data": list(range(1_200))}],
        },
    }

    spec = build_visual_spec(chart)

    assert len(spec["data"]["values"]) == 1_000
