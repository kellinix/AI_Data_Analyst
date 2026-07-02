from __future__ import annotations

from app.analytics.kpi_detector import detect_kpis


def test_detect_revenue_kpi():
    schema = [{"name": "revenue", "is_numeric": True, "is_date": False}]
    numeric_stats = {"revenue": {"total": 100000.0, "mean": 1000.0, "min": 0.0, "max": 5000.0}}
    kpis = detect_kpis(schema, numeric_stats)
    assert len(kpis) >= 1
    assert any(k["kpi_type"] == "revenue" for k in kpis)


def test_fallback_kpi_from_non_matching_columns():
    schema = [{"name": "engagement_index", "is_numeric": True, "is_date": False}]
    numeric_stats = {"engagement_index": {"total": 100.0, "mean": 1.0, "min": 0.0, "max": 10.0}}
    kpis = detect_kpis(schema, numeric_stats)
    assert len(kpis) == 1
    assert kpis[0]["kpi_type"] == "other"


def test_kpi_is_currency():
    schema = [{"name": "total_revenue", "is_numeric": True, "is_date": False}]
    numeric_stats = {"total_revenue": {"total": 5000.0, "mean": 500.0, "min": 10.0, "max": 1000.0}}
    kpis = detect_kpis(schema, numeric_stats)
    assert kpis[0]["is_currency"] is True


def test_ignores_player_attributes_and_date_kpis():
    schema = [
        {"name": "match_date", "is_numeric": True, "is_date": False, "analysis_role": "temporal_dimension"},
        {"name": "goals_opponent", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "height_cm", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "weight_kg", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "jersey_number", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "expected_goals_xg", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "player_rating", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    numeric_stats = {
        "match_date": {"total": 110619600.0, "mean": 2026000.0},
        "goals_opponent": {"total": 72410.0, "mean": 1.33, "count": 54600},
        "height_cm": {"total": 9918286.0, "mean": 181.65},
        "weight_kg": {"total": 4136337.0, "mean": 75.76},
        "jersey_number": {"total": 1365000.0, "mean": 25.0},
        "expected_goals_xg": {"total": 1250.5, "mean": 0.23, "count": 54600},
        "player_rating": {"total": 365820.0, "mean": 6.7, "count": 54600},
    }

    kpis = detect_kpis(schema, numeric_stats)
    columns = [kpi["column"] for kpi in kpis]

    assert "match_date" not in columns
    assert "goals_opponent" not in columns
    assert "height_cm" not in columns
    assert "weight_kg" not in columns
    assert "jersey_number" not in columns
    assert "expected_goals_xg" in columns
    rating = next(kpi for kpi in kpis if kpi["column"] == "player_rating")
    assert rating["value"] == 6.7
    assert rating["is_total"] is False
