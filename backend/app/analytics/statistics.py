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
from app.analytics.sql_utils import quote_identifier as _quote_identifier
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
        # Numeric columns recognized as categorical codes act as dimensions
        # downstream, so they need the same grouped value counts.
        coded_cols = [
            c["name"] for c in schema
            if c["is_numeric"] and c.get("analysis_role") in {"dimension", "flag"}
        ]
        categorical_stats.update(self._categorical_stats(coded_cols))

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

    _NUMERIC_AGGS_PER_COLUMN = 11

    def _numeric_stats(self, columns: list[str]) -> dict[str, Any]:
        if not columns:
            return {}
        limited = columns[:20]  # Limit to 20 columns
        try:
            return self._numeric_stats_batched(limited)
        except Exception as exc:
            logger.debug("Batched numeric stats failed, falling back per-column", exc=str(exc))
            return self._numeric_stats_sequential(limited)

    def _numeric_stats_batched(self, columns: list[str]) -> dict[str, Any]:
        """One round trip for all columns instead of one query per column."""
        select_parts = []
        for col in columns:
            safe_col = _quote_identifier(col)
            select_parts.extend([
                f"COUNT({safe_col})",
                f"COUNT(*) - COUNT({safe_col})",
                f"MIN({safe_col})",
                f"MAX({safe_col})",
                f"AVG({safe_col})",
                f"STDDEV({safe_col})",
                f"PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {safe_col})",
                f"PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {safe_col})",
                f"PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {safe_col})",
                f"SUM({safe_col})",
                f"COUNT(DISTINCT {safe_col})",
            ])
        row = self.conn.execute(
            f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(self.table)}"
        ).fetchone()
        if not row:
            return {}

        stats: dict[str, Any] = {}
        width = self._NUMERIC_AGGS_PER_COLUMN
        for index, col in enumerate(columns):
            chunk = row[index * width : (index + 1) * width]
            stats[col] = {
                "count": chunk[0],
                "null_count": chunk[1],
                "min": float(chunk[2]) if chunk[2] is not None else None,
                "max": float(chunk[3]) if chunk[3] is not None else None,
                "mean": float(chunk[4]) if chunk[4] is not None else None,
                "std": float(chunk[5]) if chunk[5] is not None else None,
                "p25": float(chunk[6]) if chunk[6] is not None else None,
                "p50": float(chunk[7]) if chunk[7] is not None else None,
                "p75": float(chunk[8]) if chunk[8] is not None else None,
                "total": float(chunk[9]) if chunk[9] is not None else None,
                "unique_count": int(chunk[10]) if chunk[10] is not None else None,
            }
        return stats

    def _numeric_stats_sequential(self, columns: list[str]) -> dict[str, Any]:
        """Fallback used only if the batched query fails (e.g. on a column
        that trips a per-value error some other column doesn't)."""
        stats: dict[str, Any] = {}
        for col in columns:
            try:
                stats.update(self._numeric_stats_batched([col]))
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
        limited = columns[:50]
        unique_counts = self._categorical_unique_counts(limited)

        stats: dict[str, Any] = {}
        for col in limited:
            unique_count = unique_counts.get(col, 0)
            safe_col = _quote_identifier(col)
            try:
                # Only get top values for low-cardinality columns. Each column
                # needs its own GROUP BY, so these can't be batched like the
                # unique-count query above.
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

    def _categorical_unique_counts(self, columns: list[str]) -> dict[str, int]:
        try:
            select_parts = [
                f"COUNT(DISTINCT {_quote_identifier(col)})" for col in columns
            ]
            row = self.conn.execute(
                f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(self.table)}"
            ).fetchone()
            if row:
                return {col: (row[i] or 0) for i, col in enumerate(columns)}
        except Exception as exc:
            logger.debug("Batched unique-count query failed, falling back per-column", exc=str(exc))

        counts: dict[str, int] = {}
        for col in columns:
            try:
                row = self.conn.execute(
                    f"SELECT COUNT(DISTINCT {_quote_identifier(col)}) FROM {_quote_identifier(self.table)}"
                ).fetchone()
                counts[col] = row[0] if row else 0
            except Exception as exc:
                logger.debug("Unique count failed for column", col=col, exc=str(exc))
                counts[col] = 0
        return counts

    def _correlations(self, columns: list[str]) -> dict[str, float]:
        if len(columns) < 2:
            return {}
        numeric_cols = columns[:10]  # Limit pairs
        pair_names = [
            (col_a, col_b)
            for i, col_a in enumerate(numeric_cols)
            for col_b in numeric_cols[i + 1:]
        ]
        try:
            values = self._correlations_batched(pair_names)
        except Exception as exc:
            logger.debug("Batched correlations failed, falling back per-pair", exc=str(exc))
            values = self._correlations_sequential(pair_names)

        return {
            f"{col_a}|{col_b}": round(corr, 3)
            for (col_a, col_b), corr in zip(pair_names, values, strict=False)
            if corr is not None and abs(corr) > 0.3  # Only report meaningful correlations
        }

    def _correlations_batched(self, pairs: list[tuple[str, str]]) -> list[float | None]:
        """One round trip computing CORR for every pair instead of one query each."""
        if not pairs:
            return []
        select_parts = [
            f"CORR({_quote_identifier(col_a)}, {_quote_identifier(col_b)})"
            for col_a, col_b in pairs
        ]
        row = self.conn.execute(
            f"SELECT {', '.join(select_parts)} FROM {_quote_identifier(self.table)}"
        ).fetchone()
        if not row:
            return [None] * len(pairs)
        return [float(value) if value is not None else None for value in row]

    def _correlations_sequential(self, pairs: list[tuple[str, str]]) -> list[float | None]:
        values: list[float | None] = []
        for col_a, col_b in pairs:
            try:
                values.extend(self._correlations_batched([(col_a, col_b)]))
            except Exception:
                values.append(None)
        return values
