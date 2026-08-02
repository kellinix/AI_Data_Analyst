"""
Live filtering / re-aggregation for interactive dashboard slicers.

The same per-chart-type aggregation queries originally used to populate a
chart's data (see `populate_chart_option`) are reused here with an added
WHERE clause, so a filtered view and the original unfiltered view can never
drift apart from having two independently-maintained copies of the SQL.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

import duckdb

from app.analytics.chart_specs import build_visual_spec
from app.analytics.sql_utils import quote_identifier as _quote_identifier

FilterOp = Literal["in", "between"]

# Only columns with these roles may be filtered — identifiers, free text, and
# date/temporal columns are excluded because filtering on them isn't a
# meaningful "slicer" action and because it widens the set of user-controlled
# values that reach SQL.
ALLOWED_FILTER_ROLES = {"dimension", "flag", "metric", "attribute"}


class FilterValidationError(ValueError):
    """Raised when a filter references a column outside the analysis's
    validated schema/role allow-list — never let an unvalidated column name
    reach raw SQL identifier interpolation."""


def validate_filters(
    filters: list[dict[str, Any]],
    schema: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the subset of `filters` that are safe to compile into SQL.

    Raises FilterValidationError for a column not present in `schema`, a
    disallowed `analysis_role`, or a `"between"` op on a non-numeric column.
    """
    by_name = {c["name"]: c for c in schema}
    validated = []
    for f in filters:
        column = by_name.get(f.get("column"))
        if column is None or column.get("analysis_role") not in ALLOWED_FILTER_ROLES:
            raise FilterValidationError(f"Column not filterable: {f.get('column')!r}")
        if f.get("op") == "between" and not column.get("is_numeric"):
            raise FilterValidationError(f"'between' requires a numeric column: {f['column']}")
        if not f.get("values"):
            continue
        validated.append(f)
    return validated


def build_where_clause(filters: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    """Returns (clause_sql, params) with no leading WHERE/AND keyword — the
    caller composes it into whatever WHERE clause it already has. Empty
    string + [] when there are no filters."""
    clauses: list[str] = []
    params: list[Any] = []
    for f in filters:
        column = _quote_identifier(f["column"])
        if f["op"] == "in":
            values = [str(v) for v in f["values"]]
            placeholders = ", ".join(["?"] * len(values))
            clauses.append(f"CAST({column} AS VARCHAR) IN ({placeholders})")
            params.extend(values)
        elif f["op"] == "between":
            lo, hi = f["values"][0], f["values"][1]
            clauses.append(f"{column} BETWEEN ? AND ?")
            params.extend([lo, hi])
    return " AND ".join(clauses), params


def _extra_and(filter_sql: str) -> str:
    return f" AND {filter_sql}" if filter_sql else ""


def _populate_line_multi(
    conn: duckdb.DuckDBPyConnection,
    opt: dict[str, Any],
    cols: dict[str, Any],
    filter_sql: str,
    filter_params: list[Any],
) -> bool:
    x_col, y_cols = cols.get("x"), cols.get("ys", [])
    if not (x_col and y_cols):
        return False
    aggregations = cols.get("aggregations", ["average"] * len(y_cols))
    select_columns = ", ".join(
        f"{'SUM' if aggregations[i] == 'sum' else 'AVG'}({_quote_identifier(col)}) AS {_quote_identifier(col)}"
        for i, col in enumerate(y_cols)
    )
    x_identifier = _quote_identifier(x_col)
    rows = conn.execute(
        f"""
        SELECT CAST({x_identifier} AS VARCHAR) AS period, {select_columns}
        FROM data
        WHERE {x_identifier} IS NOT NULL{_extra_and(filter_sql)}
        GROUP BY {x_identifier}
        ORDER BY {x_identifier}
        LIMIT 100
        """,
        filter_params,
    ).fetchall()
    opt["xAxis"]["data"] = [str(r[0]) for r in rows]
    for index, _col in enumerate(y_cols):
        opt["series"][index]["data"] = [
            round(float(r[index + 1]), 2) if r[index + 1] is not None else 0 for r in rows
        ]
    return True


def _populate_line_single(
    conn: duckdb.DuckDBPyConnection,
    opt: dict[str, Any],
    cols: dict[str, Any],
    filter_sql: str,
    filter_params: list[Any],
) -> bool:
    x_col, y_col = cols.get("x"), cols.get("y")
    if not (x_col and y_col):
        return False
    x_identifier, y_identifier = _quote_identifier(x_col), _quote_identifier(y_col)
    aggregate = "SUM" if cols.get("aggregation") == "sum" else "AVG"
    rows = conn.execute(
        f"""
        SELECT CAST({x_identifier} AS VARCHAR), {aggregate}({y_identifier})
        FROM data
        WHERE {x_identifier} IS NOT NULL AND {y_identifier} IS NOT NULL{_extra_and(filter_sql)}
        GROUP BY {x_identifier}
        ORDER BY {x_identifier}
        LIMIT 100
        """,
        filter_params,
    ).fetchall()
    opt["xAxis"]["data"] = [str(r[0]) for r in rows]
    opt["series"][0]["data"] = [round(float(r[1]), 2) if r[1] is not None else 0 for r in rows]
    return True


def _populate_bar(
    conn: duckdb.DuckDBPyConnection,
    opt: dict[str, Any],
    cols: dict[str, Any],
    filter_sql: str,
    filter_params: list[Any],
) -> bool:
    x_col, y_col = cols.get("x"), cols.get("y")
    if not (x_col and y_col):
        return False
    x_identifier, y_identifier = _quote_identifier(x_col), _quote_identifier(y_col)
    aggregation = cols.get("aggregation", "sum")
    if aggregation == "percent_rate":
        agg_expr = f"100.0 * AVG({y_identifier})"
    elif aggregation == "average":
        agg_expr = f"AVG({y_identifier})"
    else:
        agg_expr = f"SUM({y_identifier})"
    rows = conn.execute(
        f"""
        SELECT CAST({x_identifier} AS VARCHAR), {agg_expr} as value
        FROM data
        WHERE {x_identifier} IS NOT NULL AND {y_identifier} IS NOT NULL{_extra_and(filter_sql)}
        GROUP BY {x_identifier}
        ORDER BY value DESC
        LIMIT 15
        """,
        filter_params,
    ).fetchall()
    labels = [str(r[0]) for r in rows]
    values = [round(float(r[1]), 2) for r in rows]
    if cols.get("orientation") == "horizontal":
        opt["yAxis"]["data"] = labels[::-1]
        opt["series"][0]["data"] = values[::-1]
    else:
        opt["xAxis"]["data"] = labels
        opt["series"][0]["data"] = values
    return True


def _populate_donut(
    conn: duckdb.DuckDBPyConnection,
    opt: dict[str, Any],
    cols: dict[str, Any],
    filter_sql: str,
    filter_params: list[Any],
) -> bool:
    cat_col = cols.get("category")
    if not cat_col:
        return False
    cat_identifier = _quote_identifier(cat_col)
    rows = conn.execute(
        f"""
        SELECT CAST({cat_identifier} AS VARCHAR), COUNT(*) as cnt
        FROM data
        WHERE {cat_identifier} IS NOT NULL{_extra_and(filter_sql)}
        GROUP BY {cat_identifier}
        ORDER BY cnt DESC
        LIMIT 8
        """,
        filter_params,
    ).fetchall()
    opt["series"][0]["data"] = [{"name": str(r[0]), "value": int(r[1])} for r in rows]
    return True


def _populate_scatter(
    conn: duckdb.DuckDBPyConnection,
    opt: dict[str, Any],
    cols: dict[str, Any],
    filter_sql: str,
    filter_params: list[Any],
) -> bool:
    x_col, y_col = cols.get("x"), cols.get("y")
    if not (x_col and y_col):
        return False
    x_identifier, y_identifier = _quote_identifier(x_col), _quote_identifier(y_col)
    rows = conn.execute(
        f"""
        SELECT {x_identifier}, {y_identifier}
        FROM data
        WHERE {x_identifier} IS NOT NULL AND {y_identifier} IS NOT NULL{_extra_and(filter_sql)}
        LIMIT 500
        """,
        filter_params,
    ).fetchall()
    opt["series"][0]["data"] = [
        [float(r[0]), float(r[1])] for r in rows if r[0] is not None and r[1] is not None
    ]
    return True


def _populate_histogram(
    conn: duckdb.DuckDBPyConnection,
    opt: dict[str, Any],
    cols: dict[str, Any],
    filter_sql: str,
    filter_params: list[Any],
) -> bool:
    x_col = cols.get("x")
    if not x_col:
        return False
    x_identifier = _quote_identifier(x_col)
    rows = conn.execute(
        f"""
        SELECT {x_identifier}
        FROM data
        WHERE {x_identifier} IS NOT NULL{_extra_and(filter_sql)}
        LIMIT 10000
        """,
        filter_params,
    ).fetchall()
    values = [float(row[0]) for row in rows if row[0] is not None]
    if not values:
        return True
    min_value, max_value = min(values), max(values)
    bucket_count = min(12, max(1, len(set(values))))
    if min_value == max_value:
        opt["xAxis"]["data"] = [f"{min_value:.0f}"]
        opt["series"][0]["data"] = [len(values)]
        return True
    bucket_size = (max_value - min_value) / bucket_count
    counts = [0 for _ in range(bucket_count)]
    for value in values:
        index = min(int((value - min_value) / bucket_size), bucket_count - 1)
        counts[index] += 1
    opt["xAxis"]["data"] = [
        f"{min_value + (i * bucket_size):.0f}-{min_value + ((i + 1) * bucket_size):.0f}"
        for i in range(bucket_count)
    ]
    opt["series"][0]["data"] = counts
    return True


def populate_chart_option(
    conn: duckdb.DuckDBPyConnection,
    chart: dict[str, Any],
    filter_sql: str = "",
    filter_params: list[Any] | None = None,
) -> bool:
    """Mutate `chart["echarts_option"]` in place with query results, optionally
    narrowed by an already-validated `filter_sql`/`filter_params` (see
    `build_where_clause`). Returns whether a matching chart-type/column
    combination was found and queried; the chart is left with its previous
    `echarts_option` (still assigned back) when nothing matches, mirroring
    the pre-refactor behavior of the inline pipeline code."""
    filter_params = filter_params or []
    opt = chart.get("echarts_option", {})
    cols = opt.get("_columns", {})
    chart_type = chart.get("type")

    matched = False
    if chart_type == "line" and cols.get("ys"):
        matched = _populate_line_multi(conn, opt, cols, filter_sql, filter_params)
    elif chart_type == "line":
        matched = _populate_line_single(conn, opt, cols, filter_sql, filter_params)
    elif chart_type == "bar":
        matched = _populate_bar(conn, opt, cols, filter_sql, filter_params)
    elif chart_type == "donut":
        matched = _populate_donut(conn, opt, cols, filter_sql, filter_params)
    elif chart_type == "scatter":
        matched = _populate_scatter(conn, opt, cols, filter_sql, filter_params)
    elif chart_type == "histogram":
        matched = _populate_histogram(conn, opt, cols, filter_sql, filter_params)

    chart["echarts_option"] = opt
    return matched


def requery_chart(
    conn: duckdb.DuckDBPyConnection,
    chart: dict[str, Any],
    filter_sql: str = "",
    filter_params: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Return a NEW chart dict (the stored `chart` is never mutated) with
    fresh `echarts_option` data and a freshly rebuilt `visual_spec` for the
    given filter. Returns None when the chart has no retained `_columns`
    query spec (e.g. a chart persisted before this feature shipped) or when
    its columns don't match a known chart type — callers should treat that
    as "not filterable", not as an error."""
    if not (chart.get("echarts_option") or {}).get("_columns"):
        return None
    working = copy.deepcopy(chart)
    if not populate_chart_option(conn, working, filter_sql, filter_params or []):
        return None
    working["visual_spec"] = build_visual_spec(working)
    return working


def recompute_kpi(
    conn: duckdb.DuckDBPyConnection,
    column: str,
    is_total: bool,
    is_percent: bool,
    filter_sql: str = "",
    filter_params: list[Any] | None = None,
) -> float | None:
    """Re-aggregate a single KPI column under a filter, using the same
    SUM/AVG/percent-rate choice the original KPI was computed with."""
    filter_params = filter_params or []
    col = _quote_identifier(column)
    if is_percent:
        expr = f"100.0 * AVG({col})"
    elif is_total:
        expr = f"SUM({col})"
    else:
        expr = f"AVG({col})"
    where_sql = f" WHERE {filter_sql}" if filter_sql else ""
    row = conn.execute(f"SELECT {expr} FROM data{where_sql}", filter_params).fetchone()
    if not row or row[0] is None:
        return None
    return round(float(row[0]), 2)
