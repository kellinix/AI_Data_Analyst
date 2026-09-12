from __future__ import annotations

import pytest

from app.analytics.kpi_detector import _classify_column, _is_currency, detect_kpis


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        # Regression: "arr" matched inside "n-arr-ative", so narrative text
        # columns in a government project dataset became annual recurring
        # revenue and were summed as money.
        ("departmental_narrative_on_schedule_including_any_deviation", None),
        ("departmental_narrative_on_budgeted_benefits", None),
        ("departmental_commentary_on_actions_planned_or_taken", None),
        # Real vocabulary still matches, including plurals and phrases.
        ("total_revenue", "revenue"),
        ("whole_life_costs", "cost"),
        ("units_sold", "orders"),
        ("new_customers", "customers"),
        ("avg_order_value", "revenue"),
        ("customer_satisfaction_rating", "average"),
        ("annual_recurring_revenue", "arr"),
    ],
)
def test_classify_column_matches_whole_words_only(column, expected):
    assert _classify_column(column) == expected


def test_narrative_columns_are_not_currency():
    assert _is_currency("departmental_narrative_on_budgeted_whole_life_costs") is True  # "costs"
    assert _is_currency("departmental_narrative_on_schedule") is False
    assert _is_currency("total_revenue") is True


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


def test_outcome_flag_column_becomes_leading_rate_kpi():
    """A binary outcome column like 'target' is the point of the dataset —
    it must surface as a percentage-rate KPI, ranked first."""
    schema = [
        {"name": "chol", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "target", "is_numeric": True, "is_date": False, "analysis_role": "flag"},
    ]
    numeric_stats = {
        "chol": {"total": 252150.0, "mean": 246.0, "count": 1025},
        "target": {"mean": 0.513, "count": 1025},
    }

    kpis = detect_kpis(schema, numeric_stats)

    assert kpis[0]["column"] == "target"
    assert kpis[0]["kpi_type"] == "outcome_rate"
    assert kpis[0]["value"] == 51.3
    assert kpis[0]["is_percent"] is True


def test_non_outcome_flags_do_not_become_kpis():
    schema = [{"name": "sex", "is_numeric": True, "is_date": False, "analysis_role": "flag"}]
    numeric_stats = {"sex": {"mean": 0.696, "count": 1025}}

    kpis = detect_kpis(schema, numeric_stats)

    assert all(kpi["column"] != "sex" for kpi in kpis)


def test_fallback_kpi_shows_average_not_raw_sum():
    """A column with no recognized business meaning (e.g. resting blood
    pressure) must not headline the SUM over all rows — regression test for
    a 'Trestbps: 134,902' KPI card on the heart dataset."""
    schema = [{"name": "trestbps", "is_numeric": True, "is_date": False}]
    numeric_stats = {"trestbps": {"total": 134902.0, "mean": 131.6, "count": 1025}}

    kpis = detect_kpis(schema, numeric_stats)

    assert kpis[0]["value"] == 131.6
    assert kpis[0]["is_total"] is False


def test_kpi_is_currency():
    schema = [{"name": "total_revenue", "is_numeric": True, "is_date": False}]
    numeric_stats = {"total_revenue": {"total": 5000.0, "mean": 500.0, "min": 10.0, "max": 1000.0}}
    kpis = detect_kpis(schema, numeric_stats)
    assert kpis[0]["is_currency"] is True


def test_ignores_identifiers_coordinates_and_date_kpis():
    schema = [
        {"name": "order_date", "is_numeric": True, "is_date": False, "analysis_role": "temporal_dimension"},
        {"name": "customer_id", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "warehouse_latitude", "is_numeric": True, "is_date": False, "analysis_role": "attribute"},
        {"name": "units_sold", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
        {"name": "customer_satisfaction_rating", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    numeric_stats = {
        "order_date": {"total": 110619600.0, "mean": 2026000.0},
        "customer_id": {"total": 72410.0, "mean": 1.33, "count": 54600},
        "warehouse_latitude": {"total": 9918286.0, "mean": 181.65},
        "units_sold": {"total": 1250.5, "mean": 0.23, "count": 54600},
        "customer_satisfaction_rating": {"total": 365820.0, "mean": 6.7, "count": 54600},
    }

    kpis = detect_kpis(schema, numeric_stats)
    columns = [kpi["column"] for kpi in kpis]

    assert "order_date" not in columns
    assert "customer_id" not in columns
    assert "warehouse_latitude" not in columns
    assert "units_sold" in columns
    rating = next(kpi for kpi in kpis if kpi["column"] == "customer_satisfaction_rating")
    assert rating["value"] == 6.7
    assert rating["is_total"] is False
