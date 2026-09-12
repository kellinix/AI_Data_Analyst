from __future__ import annotations

import json
import statistics as pystats
from datetime import date, timedelta

import duckdb

from app.analytics.anomaly_detection import detect_anomalies


def _make_table(values: list[float]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("CREATE TABLE data (thalach DOUBLE)")
    conn.executemany("INSERT INTO data VALUES (?)", [(v,) for v in values])
    return conn


def _stats(values: list[float]) -> dict[str, dict[str, float]]:
    return {"thalach": {"mean": pystats.mean(values), "std": pystats.stdev(values)}}


SCHEMA = [{"name": "thalach", "is_numeric": True, "is_date": False, "analysis_role": "metric"}]


def test_low_outlier_percentile_ranks_against_all_rows():
    """Regression test: percentile was computed with a window over only the
    filtered outlier rows, so a column minimum could be reported as 'higher
    than almost every other record'."""
    values = [140.0, 145.0, 150.0, 155.0, 160.0] * 40 + [71.0]
    conn = _make_table(values)

    anomalies = detect_anomalies(conn, SCHEMA, _stats(values))

    assert anomalies, "expected the low outlier to be detected"
    outlier = anomalies[0]
    assert outlier["value"] == 71.0
    assert outlier["percentile"] <= 1
    assert "lower than almost every other record" in outlier["description"]


CONTEXT_SCHEMA = [
    {"name": "gmpp_id_number", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
    {"name": "department", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
    {"name": "thalach", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
]


def test_identifier_columns_are_left_out_of_the_context():
    """Regression: an id column is typed as a dimension, so the insight read
    "(GMPP ID Number DFT_0027_1617-Q1, Project Name Midland Main Line ...)" —
    a reference number quoted at a reader who wants to know what happened."""
    values = [140.0, 145.0, 150.0, 155.0, 160.0] * 40 + [71.0]
    conn = duckdb.connect()
    conn.execute("CREATE TABLE data (gmpp_id_number VARCHAR, department VARCHAR, thalach DOUBLE)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?, ?)",
        [(f"ID_{index}", "MOD", value) for index, value in enumerate(values)],
    )

    anomalies = detect_anomalies(conn, CONTEXT_SCHEMA, _stats(values))

    assert anomalies
    context = anomalies[0]["context"]
    assert "gmpp_id_number" not in context
    # The dimension that actually explains the record is still there.
    assert context.get("department") == "MOD"


LONG_COLUMN = (
    "ipa_delivery_confidence_assessment_a_delivery_confidence_assessment_of_the_"
    "project_at_a_fixed_point_in_time_using_a_three_point_scale_red_amber_green"
)


def test_a_paragraph_long_context_label_is_shortened():
    """Regression: a government export names a column with its whole
    definition, so the insight sentence carried 200 characters of column name
    before reaching the value the reader actually wanted."""
    values = [140.0, 145.0, 150.0, 155.0, 160.0] * 40 + [71.0]
    conn = duckdb.connect()
    conn.execute(f'CREATE TABLE data ("{LONG_COLUMN}" VARCHAR, thalach DOUBLE)')
    conn.executemany(
        "INSERT INTO data VALUES (?, ?)", [("Amber", value) for value in values]
    )
    schema = [
        {"name": LONG_COLUMN, "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
        {"name": "thalach", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]

    anomalies = detect_anomalies(conn, schema, _stats(values))

    description = anomalies[0]["description"]
    assert "…" in description
    assert "Of The Project At A Fixed Point" not in description
    # The value itself is still there — only the column's name was trimmed.
    assert "Amber" in description


def _dated_table(rows: list[tuple[date, float]]) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("CREATE TABLE data (period_date DATE, revenue DOUBLE)")
    conn.executemany("INSERT INTO data VALUES (?, ?)", rows)
    return conn


DATED_SCHEMA = [
    {"name": "period_date", "is_numeric": False, "is_date": True, "analysis_role": "temporal_dimension"},
    {"name": "revenue", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
]


def test_monthly_anomalies_need_a_real_series():
    """Regression: monthly z-scores were computed over whatever months happened
    to exist, so project dates scattered across decades made every populated
    month look extreme next to the empty ones."""
    rows = [(date(2000 + offset, 6, 15), 100.0 + offset * 30) for offset in range(12)]
    values = [row[1] for row in rows]
    stats = {"revenue": {"mean": pystats.mean(values), "std": pystats.stdev(values)}}

    anomalies = detect_anomalies(_dated_table(rows), DATED_SCHEMA, stats)

    assert not [a for a in anomalies if a["type"] == "time_series_spike"]


def test_monthly_anomalies_are_still_found_in_a_contiguous_series():
    rows = [(date(2025, month, 1), 100.0) for month in range(1, 12)] + [(date(2025, 12, 1), 900.0)]
    values = [row[1] for row in rows]
    stats = {"revenue": {"mean": pystats.mean(values), "std": pystats.stdev(values)}}

    anomalies = detect_anomalies(_dated_table(rows), DATED_SCHEMA, stats)

    assert [a for a in anomalies if a["type"] == "time_series_spike"]


def test_context_values_are_json_serializable():
    """Regression: DuckDB returns DATE cells as datetime.date, which made every
    cleaned upload with a date column fail to save its anomalies to JSONB (and,
    with no rollback, stick at "processing" forever)."""
    conn = duckdb.connect()
    conn.execute("CREATE TABLE data (week_start_date DATE, region VARCHAR, revenue DOUBLE)")
    rows = [(date(2025, 1, 6) + timedelta(weeks=i), "Europe", 100.0 + i % 5) for i in range(60)]
    rows.append((date(2025, 11, 17), "North America", 900.0))
    conn.executemany("INSERT INTO data VALUES (?, ?, ?)", rows)
    values = [row[2] for row in rows]
    schema = [
        {"name": "week_start_date", "is_numeric": False, "is_date": True, "analysis_role": "temporal_dimension"},
        {"name": "region", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
        {"name": "revenue", "is_numeric": True, "is_date": False, "analysis_role": "metric"},
    ]
    stats = {"revenue": {"mean": pystats.mean(values), "std": pystats.stdev(values)}}

    anomalies = detect_anomalies(conn, schema, stats)

    outlier = next(a for a in anomalies if a["type"] == "statistical_outlier")
    assert outlier["context"] == {"week_start_date": "2025-11-17", "region": "North America"}
    json.dumps(anomalies)  # raises TypeError if any value can't go into JSONB


def test_high_outlier_is_still_described_as_high():
    values = [140.0, 145.0, 150.0, 155.0, 160.0] * 40 + [250.0]
    conn = _make_table(values)

    anomalies = detect_anomalies(conn, SCHEMA, _stats(values))

    assert anomalies, "expected the high outlier to be detected"
    outlier = anomalies[0]
    assert outlier["value"] == 250.0
    assert outlier["percentile"] >= 99
    assert "higher than almost every other record" in outlier["description"]
