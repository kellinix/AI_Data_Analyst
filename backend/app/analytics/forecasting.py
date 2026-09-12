"""
Lightweight statistical forecasting.

This intentionally stays deterministic and transparent. It gives the LLM and UI
grounded forecast ranges without claiming more certainty than the data supports.
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np

from app.analytics.sql_utils import quote_identifier as _quote_identifier


def generate_forecasts(
    conn: duckdb.DuckDBPyConnection,
    schema: list[dict[str, Any]],
    kpis: list[dict[str, Any]],
    table: str = "data",
    max_forecasts: int = 3,
) -> list[dict[str, Any]]:
    date_columns = [column["name"] for column in schema if column.get("is_date")]
    if not date_columns:
        return []

    metric_columns = [kpi["column"] for kpi in kpis if kpi.get("kpi_type") in {"revenue", "profit", "orders", "customers"}]
    if not metric_columns:
        metric_columns = [
            column["name"]
            for column in schema
            if column.get("is_numeric")
            and column.get("analysis_role") in {None, "metric"}
            and _is_business_metric(column["name"])
        ][:max_forecasts]

    forecasts: list[dict[str, Any]] = []
    for metric_column in metric_columns[:max_forecasts]:
        forecast = _forecast_metric(conn, table, date_columns[0], metric_column)
        if forecast:
            forecasts.append(forecast)
    return forecasts


def _forecast_metric(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    date_column: str,
    metric_column: str,
) -> dict[str, Any] | None:
    rows = conn.execute(
        f"""
        SELECT
            DATE_TRUNC('month', {_quote_identifier(date_column)}) AS period,
            SUM({_quote_identifier(metric_column)}) AS value
        FROM {_quote_identifier(table)}
        WHERE {_quote_identifier(date_column)} IS NOT NULL
          AND {_quote_identifier(metric_column)} IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    if len(rows) < 3:
        return None
    if _monthly_density([row[0] for row in rows]) < _MIN_MONTHLY_DENSITY:
        return None

    y = np.array([float(row[1]) for row in rows], dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residual_std = float(np.std(y - fitted)) if len(y) > 2 else 0.0

    horizons = {"next_month": 1, "next_quarter": 3, "next_year": 12}
    predictions: dict[str, dict[str, float]] = {}
    for label, periods in horizons.items():
        projected = float(slope * (len(y) + periods - 1) + intercept)
        interval = 1.96 * residual_std * max(periods ** 0.5, 1.0)
        predictions[label] = {
            "value": round(projected, 2),
            "lower": round(projected - interval, 2),
            "upper": round(projected + interval, 2),
        }

    latest = y[-1]
    next_month = predictions["next_month"]["value"]
    change_percent = ((next_month - latest) / latest * 100) if latest else 0.0

    return {
        "metric": metric_column,
        "date_column": date_column,
        "method": "linear_regression_monthly",
        "observations": len(rows),
        "latest_value": round(float(latest), 2),
        "monthly_slope": round(float(slope), 2),
        "change_percent_next_month": round(change_percent, 2),
        "predictions": predictions,
        "confidence": _confidence(len(rows), residual_std, float(np.mean(y))),
    }


# A trend line only means something if the months form a series. Below this
# share of the months between the first and last observation, the column is a
# scatter of dates rather than a periodic measure.
_MIN_MONTHLY_DENSITY = 0.6


def _monthly_density(periods: list[Any]) -> float:
    """Share of the months between the first and last observation that have data.

    Guards against forecasting from date columns that aren't reporting periods:
    a project portfolio's start dates spanning 1997-2024 gave 41 observations
    across 27 years, and the product projected "next month" from them.
    """
    if not periods:
        return 0.0
    first, last = periods[0], periods[-1]
    span_months = (last.year - first.year) * 12 + (last.month - first.month) + 1
    return len(periods) / span_months if span_months > 0 else 0.0


def _confidence(observations: int, residual_std: float, mean_value: float) -> float:
    history_score = min(observations / 12, 1.0)
    noise_ratio = residual_std / abs(mean_value) if mean_value else 1.0
    noise_score = max(0.2, 1.0 - min(noise_ratio, 0.8))
    return round(0.45 + 0.45 * history_score * noise_score, 2)


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
