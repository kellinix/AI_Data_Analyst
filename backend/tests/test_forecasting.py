from __future__ import annotations

from datetime import date

import duckdb

from app.analytics.forecasting import generate_forecasts

SCHEMA = [
    {"name": "period_date", "is_date": True, "is_numeric": False, "analysis_role": "temporal_dimension"},
    {"name": "revenue", "is_date": False, "is_numeric": True, "analysis_role": "metric"},
]
KPIS = [{"column": "revenue", "kpi_type": "revenue"}]


def _connection(rows: list[tuple[date, float]]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("CREATE TABLE data (period_date DATE, revenue DOUBLE)")
    conn.executemany("INSERT INTO data VALUES (?, ?)", rows)
    return conn


def test_forecasts_a_contiguous_monthly_series():
    rows = [(date(2025, month, 1), 1000.0 + month * 50) for month in range(1, 13)]

    forecasts = generate_forecasts(_connection(rows), SCHEMA, KPIS)

    assert len(forecasts) == 1
    assert forecasts[0]["metric"] == "revenue"
    assert forecasts[0]["observations"] == 12


def test_skips_dates_scattered_across_years():
    """Regression: a project portfolio's start dates spanning 1997-2024 gave 41
    monthly observations across 27 years, and the product forecast "next month"
    from them — meaningless, but presented with a confidence score."""
    rows = [(date(year, 6, 15), 500.0 + year) for year in range(2015, 2025)]

    assert generate_forecasts(_connection(rows), SCHEMA, KPIS) == []


def test_skips_a_series_with_long_gaps():
    rows = [(date(2025, month, 1), 900.0) for month in (1, 2, 9, 10, 11, 12)]

    assert generate_forecasts(_connection(rows), SCHEMA, KPIS) == []


def test_tolerates_one_missing_month():
    rows = [(date(2025, month, 1), 800.0 + month) for month in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11)]

    forecasts = generate_forecasts(_connection(rows), SCHEMA, KPIS)

    assert len(forecasts) == 1
    assert forecasts[0]["observations"] == 10
