"""
Statistical anomaly detection.
"""

from __future__ import annotations

from typing import Any

import duckdb

from app.analytics.sql_utils import quote_identifier as _quote_identifier
from app.analytics.text_matching import shorten_label
from app.analytics.time_series import is_dense_monthly_series


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
        anomalies.extend(_distribution_anomalies(conn, table, column, stats, schema))
        if date_columns:
            anomalies.extend(_time_series_anomalies(conn, table, date_columns[0], column))
        if len(anomalies) >= max_anomalies:
            break

    return sorted(anomalies, key=lambda item: item["score"], reverse=True)[:max_anomalies]


def _is_identifier_column(item: dict[str, Any]) -> bool:
    """An identifier explains nothing about why a record stands out.

    The GMPP id column is typed as a dimension, so insight text read
    "(GMPP ID Number DFT_0027_1617-Q1, Project Name Midland Main Line ...)" —
    a reference number quoted at someone who wants to know what happened.
    """
    if item.get("analysis_role") == "identifier":
        return True
    normalized = str(item.get("name", "")).lower().replace(" ", "_")
    return (
        normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("id_")
        or "id_number" in normalized
    )


def _distribution_anomalies(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    column: str,
    stats: dict[str, Any],
    schema: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mean = stats.get("mean")
    std = stats.get("std")
    if mean is None or not std:
        return []

    quoted = _quote_identifier(column)
    display_labels = {
        item["name"]: item["display_label"]
        for item in schema
        if item.get("display_label")
    }
    context_columns = [
        item["name"] for item in schema
        if item["name"] != column
        and (item.get("is_date") or item.get("analysis_role") in {"dimension", "temporal_dimension"})
        and not _is_identifier_column(item)
    ][:4]
    context_select = "".join(f", {_quote_identifier(name)}" for name in context_columns)
    # Percentile must be computed over every non-null row BEFORE filtering to
    # outliers; a window over the filtered set would rank the value among the
    # outliers only (e.g. a minimum could read as the "100th percentile").
    rows = conn.execute(
        f"""
        SELECT * FROM (
            SELECT {quoted}, ABS(({quoted} - {mean}) / {std}) AS z_score{context_select},
                   100.0 * CUME_DIST() OVER (ORDER BY {quoted}) AS percentile
            FROM {_quote_identifier(table)}
            WHERE {quoted} IS NOT NULL
        )
        WHERE z_score >= 3
        ORDER BY z_score DESC
        LIMIT 1
        """
    ).fetchall()

    results = []
    for row in rows:
        value, z_score = row[0], row[1]
        context = {
            name: _json_safe(row[index + 2])
            for index, name in enumerate(context_columns)
            if row[index + 2] is not None
        }
        percentile = float(row[-1])
        # Shortened: a government export names a column with its whole
        # definition, so this sentence carried 200 characters of "Ipa Delivery
        # Confidence Assessment A Delivery Confidence Assessment Of The
        # Project At A Fixed Point In Time..." before reaching the value.
        context_text = ", ".join(
            f"{shorten_label(display_labels.get(name, _humanize(name)), 40)} "
            f"{_format_context_value(value)}"
            for name, value in context.items()
        )
        label = display_labels.get(column, _humanize(column))
        results.append({
            "type": "statistical_outlier",
            "column": column,
            "title": f"Unusually high or low {label}",
            "description": (
                f"One entry reached {float(value):,.2f} for {label}, "
                f"{_plain_percentile(percentile)}"
                + (f" ({context_text})." if context_text else ".")
            ),
            "score": round(float(z_score), 2),
            "value": float(value),
            "percentile": round(percentile, 1),
            "context": context,
        })
    return results


def _json_safe(value: Any) -> Any:
    """DuckDB returns DATE/TIMESTAMP cells as date/datetime objects, but anomalies
    are stored in JSONB (`analyses.metadata`, `insights.data`), which can't hold
    them — an unconverted date made every cleaned upload with a date column fail
    to save."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _format_context_value(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return f"{value:.0f}"
    return value


def _plain_percentile(percentile: float) -> str:
    """Translate a percentile rank into a plain-English comparison.

    "Record" is a database word. A business reader has projects, orders or
    customers in front of them, not records.
    """
    if percentile >= 99:
        return "higher than almost everything else in the file"
    if percentile <= 1:
        return "lower than almost everything else in the file"
    if percentile >= 50:
        return f"higher than about {percentile:.0f}% of the rest"
    return f"lower than about {100 - percentile:.0f}% of the rest"


def _time_series_anomalies(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    date_column: str,
    metric_column: str,
) -> list[dict[str, Any]]:
    date_q = _quote_identifier(date_column)
    metric_q = _quote_identifier(metric_column)
    # Monthly z-scores only mean something over a real series. Project start
    # dates spanning decades give a handful of scattered months, where every
    # populated month looks extreme next to the empty ones.
    months = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DATE_TRUNC('month', {date_q}) AS period
            FROM {_quote_identifier(table)}
            WHERE {date_q} IS NOT NULL AND {metric_q} IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()
    ]
    if not is_dense_monthly_series(months):
        return []

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


def _is_business_metric(column: str) -> bool:
    normalized = column.lower().replace(" ", "_")
    parts = set(normalized.split("_"))
    return not (
        normalized == "year"
        or normalized.endswith("_year")
        or "date" in parts
        or "time" in parts
        or "timestamp" in parts
        or "age" in parts
        or "latitude" in parts
        or "longitude" in parts
        or "coord" in parts
        or normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("id_")
        or normalized.startswith("is_")
        or normalized.startswith("has_")
    )


def _humanize(value: str) -> str:
    replacements = {"pct": "%", "km": "km", "kmh": "km/h"}
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in value.replace("_", " ").split()
    )
