from __future__ import annotations

import statistics as pystats

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


def test_high_outlier_is_still_described_as_high():
    values = [140.0, 145.0, 150.0, 155.0, 160.0] * 40 + [250.0]
    conn = _make_table(values)

    anomalies = detect_anomalies(conn, SCHEMA, _stats(values))

    assert anomalies, "expected the high outlier to be detected"
    outlier = anomalies[0]
    assert outlier["value"] == 250.0
    assert outlier["percentile"] >= 99
    assert "higher than almost every other record" in outlier["description"]
