from __future__ import annotations

"""
Statistical anomaly detection.
"""

from typing import Any

import duckdb


def detect_anomalies(
    conn: duckdb.DuckDBPyConnection,
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
    table: str = "data",
    max_anomalies: int = 8,
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    date_columns = [column["name"] for column in schema if column.get("is_date")]
    candidate_columns = {
        column["name"]
        for column in schema
        if column.get("is_numeric")
        and column.get("analysis_role") in {None, "metric"}
        and _is_business_metric(column["name"])
    }

    for column, stats in numeric_stats.items():
        if column not in candidate_columns:
            continue
        anomalies.extend(_distribution_anomalies(conn, table, column, stats))
        if date_columns:
            anomalies.extend(_time_series_anomalies(conn, table, date_columns[0], column))
        if len(anomalies) >= max_anomalies:
            break

    return sorted(anomalies, key=lambda item: item["score"], reverse=True)[:max_anomalies]


def _distribution_anomalies(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    column: str,
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    mean = stats.get("mean")
    std = stats.get("std")
    if mean is None or not std:
        return []

    quoted = _quote_identifier(column)
    rows = conn.execute(
        f"""
        SELECT {quoted}, ABS(({quoted} - {mean}) / {std}) AS z_score
        FROM {_quote_identifier(table)}
        WHERE {quoted} IS NOT NULL AND ABS(({quoted} - {mean}) / {std}) >= 3
        ORDER BY z_score DESC
        LIMIT 1
        """
    ).fetchall()

    return [
        {
            "type": "statistical_outlier",
            "column": column,
            "title": f"Standout {label}",
            "description": (
                f"One record reached {float(value):,.2f} for {label}, "
                "which is much higher than the usual range in this file."
            ),
            "score": round(float(z_score), 2),
            "value": float(value),
        }
        for value, z_score in rows
        for label in [_humanize(column)]
    ]


def _time_series_anomalies(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    date_column: str,
    metric_column: str,
) -> list[dict[str, Any]]:
    date_q = _quote_identifier(date_column)
    metric_q = _quote_identifier(metric_column)
    rows = conn.execute(
        f"""
        WITH series AS (
            SELECT
                DATE_TRUNC('month', {date_q}) AS period,
                SUM({metric_q}) AS value
            FROM {_quote_identifier(table)}
            WHERE {date_q} IS NOT NULL AND {metric_q} IS NOT NULL
            GROUP BY 1
        ),
        scored AS (
            SELECT
                period,
                value,
                AVG(value) OVER () AS mean_value,
                STDDEV(value) OVER () AS std_value
            FROM series
        )
        SELECT period, value, ABS((value - mean_value) / NULLIF(std_value, 0)) AS z_score
        FROM scored
        WHERE z_score >= 2.5
        ORDER BY z_score DESC
        LIMIT 2
        """
    ).fetchall()

    return [
        {
            "type": "time_series_spike",
            "column": metric_column,
            "date_column": date_column,
            "title": f"Unexpected {metric_column} movement",
            "description": f"{metric_column} reached {float(value):,.2f} in {period}, unusually far from the monthly pattern.",
            "score": round(float(z_score), 2),
            "period": str(period),
            "value": float(value),
        }
        for period, value, z_score in rows
        if z_score is not None
    ]


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _is_business_metric(column: str) -> bool:
    normalized = column.lower().replace(" ", "_")
    parts = set(normalized.split("_"))
    return not (
        normalized in {"goals_team", "goals_opponent"}
        or normalized == "year"
        or normalized.endswith("_year")
        or "date" in parts
        or "time" in parts
        or "timestamp" in parts
        or "age" in parts
        or "height" in parts
        or "weight" in parts
        or "jersey" in parts
        or "latitude" in parts
        or "longitude" in parts
        or "coord" in parts
        or "shirt_number" in normalized
        or "squad_number" in normalized
        or normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("id_")
        or normalized.startswith("is_")
        or normalized.startswith("has_")
    )


def _humanize(value: str) -> str:
    replacements = {"xg": "xG", "xa": "xA", "pct": "%", "km": "km", "kmh": "km/h"}
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in value.replace("_", " ").split()
    )
