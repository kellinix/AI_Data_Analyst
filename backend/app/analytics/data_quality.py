"""
Data quality checks used by the analysis pipeline.
"""

from __future__ import annotations

from typing import Any

import duckdb

from app.analytics.sql_utils import quote_identifier as _quote_identifier


def analyze_data_quality(
    conn: duckdb.DuckDBPyConnection,
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
    table: str = "data",
) -> dict[str, Any]:
    row_count = _row_count(conn, table)
    if row_count == 0:
        return {"score": 0, "issues": [], "fixes": []}

    issues: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []

    for column in schema:
        name = column["name"]
        quoted = _quote_identifier(name)
        null_count = _single_int(
            conn,
            f"SELECT COUNT(*) - COUNT({quoted}) FROM {_quote_identifier(table)}",
        )
        null_fraction = null_count / row_count
        if null_fraction > 0:
            severity = "critical" if null_fraction > 0.5 else "high" if null_fraction > 0.2 else "low"
            issues.append({
                "type": "missing_values",
                "column": name,
                "severity": severity,
                "description": f"{null_fraction:.1%} of values are missing",
                "affected_rows": null_count,
            })
            fixes.append({
                "id": f"fill_missing_{name}",
                "label": f"Review missing values in {name}",
                "type": "review",
                "safe_to_auto_apply": False,
            })
        # IQR outlier scans only make sense for measurable quantities;
        # on categorical codes or identifiers every rare code reads as an
        # "unusual value".
        if column.get("is_numeric") and column.get("analysis_role") in {None, "metric", "attribute"}:
            issues.extend(_numeric_quality_issues(conn, table, name, numeric_stats.get(name, {})))

    issues.extend(_relationship_issues(conn, table, {column["name"] for column in schema}))

    duplicate_count = _duplicate_count(conn, table)
    if duplicate_count > 0:
        duplicate_ratio = duplicate_count / row_count
        issues.append({
            "type": "duplicates",
            "column": None,
            "severity": _ratio_severity(duplicate_ratio),
            "description": (
                f"{duplicate_count:,} rows ({duplicate_ratio:.0%} of the dataset) "
                "are exact copies of other rows"
            ),
            "affected_rows": duplicate_count,
        })
        fixes.append({
            "id": "remove_duplicate_rows",
            "label": "Remove exact duplicate rows",
            "type": "deduplicate",
            "safe_to_auto_apply": True,
        })

    score = _quality_score(row_count, issues)
    return {"score": score, "issues": issues[:25], "fixes": fixes[:10]}


def _numeric_quality_issues(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    column: str,
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    q1 = stats.get("p25")
    q3 = stats.get("p75")
    minimum = stats.get("min")

    if q1 is not None and q3 is not None:
        iqr = q3 - q1
        if iqr > 0:
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            quoted = _quote_identifier(column)
            count = _single_int(
                conn,
                f"""
                SELECT COUNT(*)
                FROM {_quote_identifier(table)}
                WHERE {quoted} < {lower} OR {quoted} > {upper}
                """,
            )
            if count > 0:
                # A right-skewed metric is the subject matter, not a defect. A
                # portfolio holding HS2 always has values far above the IQR
                # fence, and calling that a medium-severity quality issue told
                # a non-technical reader their data was faulty and docked the
                # score for it. Values only *below* a fence the column can
                # actually reach are still worth flagging as odd.
                below = _single_int(
                    conn,
                    f"SELECT COUNT(*) FROM {_quote_identifier(table)} WHERE {quoted} < {lower}",
                )
                high_side_only = below == 0
                # Never quote a bound the column cannot reach: cost columns
                # were shown a "typical range" starting at -300.
                display_lower = max(lower, minimum) if minimum is not None and minimum >= 0 else lower
                issues.append({
                    "type": "wide_spread" if high_side_only else "outliers",
                    "column": column,
                    "severity": "low" if high_side_only else "medium",
                    "description": (
                        f"{count:,} value{'s' if count != 1 else ''} sit well above the rest "
                        f"(most fall between {display_lower:,.0f} and {upper:,.0f})"
                        if high_side_only
                        else (
                            f"{count:,} value{'s' if count != 1 else ''} fall far outside "
                            f"the typical range ({display_lower:,.0f} to {upper:,.0f})"
                        )
                    ),
                    "affected_rows": count,
                    "bounds": {"lower": lower, "upper": upper},
                })

    normalized = column.lower().replace(" ", "_")
    money_like = any(word in normalized for word in ("revenue", "sales", "amount", "price", "profit", "cost"))
    if money_like and minimum is not None and minimum < 0:
        quoted = _quote_identifier(column)
        count = _single_int(
            conn,
            f"SELECT COUNT(*) FROM {_quote_identifier(table)} WHERE {quoted} < 0",
        )
        issues.append({
            "type": "negative_financial_values",
            "column": column,
            "severity": "high",
            "description": f"{count:,} negative financial values detected",
            "affected_rows": count,
        })

    return issues


def _ratio_severity(ratio: float) -> str:
    """Severity of an issue proportional to how much of the dataset it touches."""
    if ratio >= 0.5:
        return "critical"
    if ratio >= 0.2:
        return "high"
    if ratio >= 0.05:
        return "medium"
    return "low"


def _quality_score(row_count: int, issues: list[dict[str, Any]]) -> int:
    penalty = 0.0
    severity_weight = {"low": 1.5, "medium": 4.0, "high": 8.0, "critical": 14.0}
    for issue in issues:
        affected = issue.get("affected_rows") or 0
        affected_ratio = min(float(affected) / max(row_count, 1), 1.0)
        weight = severity_weight.get(issue.get("severity", "medium"), 4.0)
        # An issue touching most of the dataset dominates everything computed
        # from it — the score must not stay in the "healthy" band.
        if affected_ratio > 0.5:
            weight *= 2
        penalty += weight * max(affected_ratio, 0.05)
    return max(0, min(100, int(round(100 - penalty))))


def _row_count(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    return _single_int(conn, f"SELECT COUNT(*) FROM {_quote_identifier(table)}")


def _duplicate_count(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    try:
        columns = [
            str(row[0])
            for row in conn.execute(f"DESCRIBE {_quote_identifier(table)}").fetchall()
        ]
        if not columns:
            return 0
        grouped_columns = ", ".join(_quote_identifier(column) for column in columns)
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(row_count - 1), 0)
            FROM (
                SELECT COUNT(*) AS row_count
                FROM {_quote_identifier(table)}
                GROUP BY {grouped_columns}
                HAVING COUNT(*) > 1
            ) duplicates
            """
        ).fetchone()
        if row:
            return int(row[0])
    except Exception:
        return 0
    return 0


def _relationship_issues(conn: duckdb.DuckDBPyConnection, table: str, columns: set[str]) -> list[dict[str, Any]]:
    """Flag "part exceeds whole" pairs for common business ratio columns
    (e.g. a completed count that's larger than its own total)."""
    checks = [
        ("units_returned", "units_sold", "units_returned_exceeds_units_sold"),
        ("completed_orders", "total_orders", "completed_orders_exceed_total"),
        ("successful_deliveries", "total_deliveries", "successful_deliveries_exceed_total"),
    ]
    issues: list[dict[str, Any]] = []
    for left, right, issue_type in checks:
        if {left, right} <= columns:
            count = _single_int(conn, f"SELECT COUNT(*) FROM {_quote_identifier(table)} WHERE {_quote_identifier(left)} > {_quote_identifier(right)}")
            if count:
                issues.append({"type": issue_type, "column": left, "severity": "high", "description": f"{count:,} rows have {left} greater than {right}", "affected_rows": count})
    return issues


def _single_int(conn: duckdb.DuckDBPyConnection, query: str) -> int:
    row = conn.execute(query).fetchone()
    return int(row[0] or 0) if row else 0
