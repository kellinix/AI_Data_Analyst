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
