from __future__ import annotations

from app.analytics.chart_selector import select_charts


def test_chart_selector_ignores_numeric_attributes():
    schema = [
        {"name": "position", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
        {"name": "goals_opponent", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "age", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "height_cm", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "jersey_number", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "expected_goals_xg", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    categorical_stats = {
        "position": {
            "unique_count": 4,
            "top_values": [
                {"value": "Defender", "count": 100},
                {"value": "Midfielder", "count": 80},
            ],
        }
    }
    numeric_stats = {
        "age": {"total": 1200},
        "goals_opponent": {"total": 900},
        "height_cm": {"total": 9000},
        "jersey_number": {"total": 500},
        "expected_goals_xg": {"total": 12.5},
    }

    charts = select_charts(schema, numeric_stats, categorical_stats, {}, {})
    chart_axes = {(chart.get("xAxis"), chart.get("yAxis")) for chart in charts}

    assert ("age", "position") not in chart_axes
    assert ("goals_opponent", "position") not in chart_axes
    assert ("height_cm", "position") not in chart_axes
    assert ("jersey_number", "position") not in chart_axes
    assert ("expected_goals_xg", "position") in chart_axes
