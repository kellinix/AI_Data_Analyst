"""Validate and execute user-approved metric definitions on the analysed file."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import duckdb

from app.analytics.sql_utils import quote_identifier
from app.services.file_processor import FileProcessor

Aggregation = Literal["sum", "average", "count", "distinct_count"]


def validate_metric_source(
    schema: list[dict[str, Any]], aggregation: Aggregation, column_name: str | None
) -> None:
    """Never interpolate a column unless it belongs to the saved analysis schema."""
    from app.analytics.survey_context import survey_fields
    survey = survey_fields(schema)
    if survey and column_name == survey["percentage"] and aggregation in {"sum", "average"}:
        raise ValueError("Use a comparison filtered to one survey question, answer and group. An overall survey percentage cannot be calculated from unrelated results.")
    if aggregation == "count":
        if column_name is not None:
            raise ValueError("Record count does not take a source column")
        return
    column = next((item for item in schema if item.get("name") == column_name), None)
    if column is None:
        raise ValueError("Source column is not in this analysis")
    role = column.get("analysis_role")
    if aggregation in {"sum", "average"}:
        if not column.get("is_numeric") or role not in {"metric", "attribute"}:
            raise ValueError("Sum and average require a numeric measure")
    elif aggregation == "distinct_count":
        if role not in {"identifier", "dimension", "flag", "attribute", "metric"}:
            raise ValueError("Distinct count requires a recorded ID or grouping column")


def calculate_metric(
    conn: duckdb.DuckDBPyConnection, aggregation: Aggregation, column_name: str | None
) -> float | int | None:
    if aggregation == "count":
        expression = "COUNT(*)"
    else:
        assert column_name is not None
        column = quote_identifier(column_name)
        expression = {
            "sum": f"SUM({column})",
            "average": f"AVG({column})",
            "distinct_count": f"COUNT(DISTINCT {column})",
        }[aggregation]
    result = conn.execute(f"SELECT {expression} FROM data").fetchone()
    value = result[0] if result else None
    if value is None:
        return None
    if aggregation in {"count", "distinct_count"}:
        return int(value)
    value = float(value)
    return value if math.isfinite(value) else None


async def preview_metric(
    file_path: str, aggregation: Aggregation, column_name: str | None
) -> tuple[float | int | None, int, bool]:
    conn = duckdb.connect(":memory:")
    try:
        row_count, truncated = await FileProcessor().read_to_duckdb_ex(
            conn, file_path, Path(file_path).suffix.lower()
        )
        value = calculate_metric(conn, aggregation, column_name)
        return value, row_count, truncated
    finally:
        conn.close()
