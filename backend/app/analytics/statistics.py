"""
Statistical analysis layer.

Performs all quantitative analysis BEFORE passing anything to the LLM.
This ensures the AI is grounded in real numbers, not hallucinations.
"""

from __future__ import annotations

from typing import Any

import duckdb

from app.analytics.data_quality import analyze_data_quality
from app.analytics.semantic_detector import enrich_schema_with_semantics
from app.core.logging import get_logger

logger = get_logger(__name__)


class StatisticsEngine:
    """Compute descriptive statistics and data profiles from DuckDB."""

    def __init__(self, conn: duckdb.DuckDBPyConnection, table: str = "data"):
        self.conn = conn
        self.table = table

    def describe_all(self) -> dict[str, Any]:
        """Return a comprehensive statistical summary of all columns."""
        schema = self._get_schema()
        numeric_cols = [c["name"] for c in schema if c["is_numeric"]]
        date_cols = [c["name"] for c in schema if c["is_date"]]
        categorical_cols = [c["name"] for c in schema if not c["is_numeric"] and not c["is_date"]]
        numeric_stats = self._numeric_stats(numeric_cols)
        categorical_stats = self._categorical_stats(categorical_cols)
        schema = enrich_schema_with_semantics(schema, numeric_stats, categorical_stats)

        result: dict[str, Any] = {
            "row_count": self._row_count(),
            "column_count": len(schema),
            "schema": schema,
            "numeric_stats": numeric_stats,
            "date_range": self._date_range(date_cols),
            "categorical_stats": categorical_stats,
            "data_quality": analyze_data_quality(self.conn, schema, numeric_stats, self.table),
            "correlations": self._correlations(numeric_cols) if len(numeric_cols) >= 2 else {},
        }
        return result

    def _row_count(self) -> int:
        r = self.conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(self.table)}").fetchone()
        return r[0] if r else 0

    def _get_schema(self) -> list[dict[str, Any]]:
        cols = self.conn.execute(f"DESCRIBE {_quote_identifier(self.table)}").fetchall()
        schema = []
        for name, dtype, null, _key, _default, _extra in cols:
            dtype_lower = str(dtype).lower()
            is_numeric = any(t in dtype_lower for t in ["int", "float", "double", "decimal", "numeric", "real", "bigint", "hugeint"])
            is_date = any(t in dtype_lower for t in ["date", "timestamp", "time"])
            schema.append({
                "name": name,
                "dtype": dtype,
                "is_numeric": is_numeric,
                "is_date": is_date,
                "nullable": null == "YES",
            })
        return schema

    def _numeric_stats(self, columns: list[str]) -> dict[str, Any]:
        if not columns:
            return {}
        stats: dict[str, Any] = {}
        for col in columns[:20]:  # Limit to 20 columns
            safe_col = _quote_identifier(col)
            try:
                row = self.conn.execute(f"""
                    SELECT
                        COUNT({safe_col}) as count,
                        COUNT(*) - COUNT({safe_col}) as null_count,
                        MIN({safe_col}) as min_val,
                        MAX({safe_col}) as max_val,
                        AVG({safe_col}) as mean_val,
                        STDDEV({safe_col}) as std_val,
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {safe_col}) as p25,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {safe_col}) as p50,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {safe_col}) as p75,
                        SUM({safe_col}) as total
                    FROM {_quote_identifier(self.table)}
                """).fetchone()
                if row:
                    stats[col] = {
                        "count": row[0],
                        "null_count": row[1],
                        "min": float(row[2]) if row[2] is not None else None,
                        "max": float(row[3]) if row[3] is not None else None,
                        "mean": float(row[4]) if row[4] is not None else None,
                        "std": float(row[5]) if row[5] is not None else None,
                        "p25": float(row[6]) if row[6] is not None else None,
                        "p50": float(row[7]) if row[7] is not None else None,
                        "p75": float(row[8]) if row[8] is not None else None,
                        "total": float(row[9]) if row[9] is not None else None,
                    }
            except Exception as exc:
                logger.debug("Numeric stats failed for column", col=col, exc=str(exc))
        return stats

    def _date_range(self, columns: list[str]) -> dict[str, Any]:
        if not columns:
            return {}
        ranges: dict[str, Any] = {}
        for col in columns[:5]:
            safe_col = _quote_identifier(col)
            try:
                row = self.conn.execute(
                    f"SELECT MIN({safe_col}), MAX({safe_col}) FROM {_quote_identifier(self.table)}"
                ).fetchone()
                if row and row[0] and row[1]:
                    ranges[col] = {"min": str(row[0]), "max": str(row[1])}
            except Exception:
                pass
        return ranges

    def _categorical_stats(self, columns: list[str]) -> dict[str, Any]:
        if not columns:
            return {}
        stats: dict[str, Any] = {}
        for col in columns[:50]:
            safe_col = _quote_identifier(col)
            try:
                row = self.conn.execute(
                    f"SELECT COUNT(DISTINCT {safe_col}) FROM {_quote_identifier(self.table)}"
                ).fetchone()
                unique_count = row[0] if row else 0

                # Only get top values for low-cardinality columns
                if unique_count <= 50:
                    top = self.conn.execute(f"""
                        SELECT {safe_col}, COUNT(*) as cnt
                        FROM {_quote_identifier(self.table)}
                        WHERE {safe_col} IS NOT NULL
                        GROUP BY {safe_col}
                        ORDER BY cnt DESC
                        LIMIT 10
                    """).fetchall()
                    stats[col] = {
                        "unique_count": unique_count,
                        "top_values": [{"value": str(r[0]), "count": r[1]} for r in top],
                    }
                else:
                    stats[col] = {"unique_count": unique_count, "top_values": []}
            except Exception as exc:
                logger.debug("Categorical stats failed for column", col=col, exc=str(exc))
        return stats

    def _correlations(self, columns: list[str]) -> dict[str, float]:
        if len(columns) < 2:
            return {}
        pairs = {}
        numeric_cols = columns[:10]  # Limit pairs
        for i, col_a in enumerate(numeric_cols):
            for col_b in numeric_cols[i + 1:]:
                safe_a = _quote_identifier(col_a)
                safe_b = _quote_identifier(col_b)
                try:
                    row = self.conn.execute(
                        f"SELECT CORR({safe_a}, {safe_b}) FROM {_quote_identifier(self.table)}"
                    ).fetchone()
                    if row and row[0] is not None:
                        corr = float(row[0])
                        if abs(corr) > 0.3:  # Only report meaningful correlations
                            pairs[f"{col_a}|{col_b}"] = round(corr, 3)
                except Exception:
                    pass
        return pairs


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
