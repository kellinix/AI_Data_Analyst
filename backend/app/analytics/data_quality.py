from __future__ import annotations

"""
Data quality checks used by the analysis pipeline.
"""

from typing import Any

import duckdb


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

    duplicate_count = _duplicate_count(conn, table)
    if duplicate_count > 0:
        issues.append({
            "type": "duplicates",
            "column": None,
            "severity": "medium",
            "description": f"{duplicate_count:,} duplicate rows detected in the first 10,000 rows",
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
                issues.append({
                    "type": "outliers",
                    "column": column,
                    "severity": "medium",
                    "description": f"{count:,} statistically unusual values detected",
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


def _quality_score(row_count: int, issues: list[dict[str, Any]]) -> int:
    penalty = 0.0
    severity_weight = {"low": 1.5, "medium": 4.0, "high": 8.0, "critical": 14.0}
    for issue in issues:
        affected = issue.get("affected_rows") or 0
        affected_ratio = min(float(affected) / max(row_count, 1), 1.0)
        penalty += severity_weight.get(issue.get("severity", "medium"), 4.0) * max(affected_ratio, 0.05)
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
                FROM (SELECT * FROM {_quote_identifier(table)} LIMIT 10000)
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


def _single_int(conn: duckdb.DuckDBPyConnection, query: str) -> int:
    row = conn.execute(query).fetchone()
    return int(row[0] or 0) if row else 0


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
