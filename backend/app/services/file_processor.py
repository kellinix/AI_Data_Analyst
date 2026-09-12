from __future__ import annotations

import asyncio
import csv
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import chardet
import duckdb
import pandas as pd
import polars as pl

from app.core.logging import get_logger

logger = get_logger(__name__)

_MISSING_TEXT_VALUES = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "nan",
    "none",
    "null",
    "nil",
    "unknown",
    "missing",
    "#n/a",
    "#na",
}

# A numeric column null in more than this fraction of rows is treated as an
# optional/sparse field, not a required metric, when deciding whether a row
# has "no numeric data at all" and should be dropped during smart cleaning.
_SPARSE_NUMERIC_METRIC_NULL_RATIO = 0.7


class FileProcessor:
    """Reads uploaded files into DuckDB and Polars for profiling and analysis."""

    SAMPLE_ROWS = 200_000
    HEADER_SCAN_ROWS = 25
    DATE_FORMATS = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d %Y",
        "%B %d %Y",
    )

    async def profile(self, file_path: str, extension: str) -> dict[str, Any]:
        """Profile the file: row count, column count, column metadata."""
        return await asyncio.to_thread(self._profile_sync, file_path, extension)

    def _profile_sync(self, file_path: str, extension: str) -> dict[str, Any]:
        try:
            df, truncated = self._read_file_ex(file_path, extension)
            columns = []
            for col in df.columns:
                series = df[col]
                null_count = series.null_count()
                non_null_count = len(series) - null_count
                try:
                    unique_count = series.n_unique()
                except Exception:
                    unique_count = 0
                sample_raw = series.drop_nulls().head(5).to_list()
                sample_values = [str(v) for v in sample_raw]
                columns.append({
                    "name": col,
                    "dtype": str(series.dtype),
                    "non_null_count": non_null_count,
                    "null_count": null_count,
                    "unique_count": unique_count,
                    "sample_values": sample_values,
                })
            return {
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": columns,
                "parser": self._parser_metadata(file_path, extension),
                "truncated": truncated,
                "sample_row_limit": self.SAMPLE_ROWS if truncated else None,
            }
        except Exception as exc:
            logger.warning("Profile failed", file_path=file_path, exc=str(exc))
            return {"row_count": None, "column_count": None, "columns": None}

    def _read_file(self, file_path: str, extension: str) -> pl.DataFrame:
        return self._read_file_ex(file_path, extension)[0]

    def _read_file_ex(self, file_path: str, extension: str) -> tuple[pl.DataFrame, bool]:
        """Read a file capped at SAMPLE_ROWS, consistently across formats.

        Returns (dataframe, truncated) so callers can tell the user when an
        analysis only covers a sample of a larger file rather than silently
        dropping rows.
        """
        ext = extension.lower()
        if ext == ".csv" or ext == ".tsv":
            return self._read_delimited_file(file_path, ext)
        elif ext in (".xlsx", ".xls"):
            sheets = pl.read_excel(
                file_path,
                sheet_id=0,
                has_header=False,
                read_options={"n_rows": self.SAMPLE_ROWS + 1},
                infer_schema_length=1000,
            )
            df = self._normalize_excel_sheets(sheets)
            return self._cap_dataframe(df)
        elif ext == ".json":
            # polars has no row-limited JSON reader for arbitrary (non-NDJSON)
            # structures, so this still parses the full file before capping.
            df = pl.read_json(file_path)
            return self._cap_dataframe(df)
        elif ext == ".parquet":
            df = pl.read_parquet(file_path, n_rows=self.SAMPLE_ROWS + 1)
            return self._cap_dataframe(df)
        else:
            raise ValueError(f"Unsupported extension: {ext}")

    def _cap_dataframe(self, df: pl.DataFrame) -> tuple[pl.DataFrame, bool]:
        if len(df) > self.SAMPLE_ROWS:
            return df.head(self.SAMPLE_ROWS), True
        return df, False

    def _read_delimited_file(self, file_path: str, extension: str) -> tuple[pl.DataFrame, bool]:
        encoding = self._detect_encoding(file_path)
        delimiter = self._detect_delimiter(file_path, encoding, extension)
        rows = self._read_delimited_rows(file_path, encoding, delimiter)
        if not rows:
            return pl.DataFrame(), False

        truncated = len(rows) > self.SAMPLE_ROWS
        if truncated:
            rows = rows[: self.SAMPLE_ROWS]

        width = max(len(row) for row in rows)
        padded_rows = [
            [self._clean_raw_text_cell(value) for value in row] + [None] * (width - len(row))
            for row in rows
        ]
        df = pl.DataFrame(
            {f"column_{index + 1}": [row[index] for row in padded_rows] for index in range(width)}
        )
        return self._normalize_report_table(df), truncated

    def _parser_metadata(self, file_path: str, extension: str) -> dict[str, Any]:
        ext = extension.lower()
        if ext in {".csv", ".tsv"}:
            encoding = self._detect_encoding(file_path)
            delimiter = self._detect_delimiter(file_path, encoding, ext)
            return {
                "type": "delimited",
                "encoding": encoding,
                "delimiter": "\\t" if delimiter == "\t" else delimiter,
            }
        if ext in {".xlsx", ".xls"}:
            return {
                "type": "excel",
                "header_scan_rows": self.HEADER_SCAN_ROWS,
            }
        return {"type": ext.removeprefix(".")}

    def _detect_encoding(self, file_path: str) -> str:
        raw = Path(file_path).read_bytes()[:128_000]
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        detection = chardet.detect(raw)
        encoding = detection.get("encoding") or "utf-8"
        confidence = float(detection.get("confidence") or 0)
        if confidence < 0.45:
            return "utf-8"
        return encoding

    def _detect_delimiter(self, file_path: str, encoding: str, extension: str) -> str:
        sample = self._read_text_sample(file_path, encoding)
        non_empty_lines = [line for line in sample.splitlines() if line.strip()][:30]
        if not non_empty_lines:
            return "\t" if extension == ".tsv" else ","

        try:
            dialect = csv.Sniffer().sniff("\n".join(non_empty_lines), delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            pass

        candidates = ["\t", ";", "|", ","]
        if extension == ".tsv":
            candidates = ["\t", ",", ";", "|"]

        best_delimiter = candidates[0]
        best_score = -1.0
        for delimiter in candidates:
            counts = [line.count(delimiter) for line in non_empty_lines]
            populated = [count for count in counts if count > 0]
            if not populated:
                continue
            consistency = populated.count(max(set(populated), key=populated.count)) / len(populated)
            score = (sum(populated) / len(populated)) * consistency * (len(populated) / len(non_empty_lines))
            if score > best_score:
                best_score = score
                best_delimiter = delimiter
        return best_delimiter

    def _read_text_sample(self, file_path: str, encoding: str) -> str:
        raw = Path(file_path).read_bytes()[:128_000]
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")

    def _read_delimited_rows(
        self,
        file_path: str,
        encoding: str,
        delimiter: str,
    ) -> list[list[str | None]]:
        # Read one row beyond the cap so callers can detect truncation
        # without a separate full-file scan.
        read_limit = self.SAMPLE_ROWS + 1
        rows: list[list[str | None]] = []
        try:
            with open(file_path, encoding=encoding, errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                for row in reader:
                    rows.append(row)
                    if len(rows) >= read_limit:
                        break
        except LookupError:
            with open(file_path, encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                for row in reader:
                    rows.append(row)
                    if len(rows) >= read_limit:
                        break
        return rows

    def _clean_raw_text_cell(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().removeprefix("\ufeff").strip()
        return cleaned if cleaned else None

    async def clean_file(
        self,
        input_path: str,
        extension: str,
        parquet_output_path: str,
        csv_output_path: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._clean_file_sync,
            input_path,
            extension,
            parquet_output_path,
            csv_output_path,
            options or {},
        )

    def _clean_file_sync(
        self,
        input_path: str,
        extension: str,
        parquet_output_path: str,
        csv_output_path: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        df = self._read_file(input_path, extension)
        cleaned, report = self.clean_dataframe(df, options)

        parquet_path = Path(parquet_output_path)
        csv_path = Path(csv_output_path)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned.write_parquet(parquet_path)
        cleaned.write_csv(csv_path)

        return {
            **self._profile_dataframe(cleaned),
            "cleaning_report": report,
            "cleaned_parquet_path": str(parquet_path),
            "cleaned_csv_path": str(csv_path),
        }

    def clean_dataframe(
        self,
        df: pl.DataFrame,
        options: dict[str, Any] | None = None,
    ) -> tuple[pl.DataFrame, dict[str, Any]]:
        options = _cleaning_options(options or {})
        report: dict[str, Any] = {
            "enabled": True,
            "options": options,
            "input_rows": df.height,
            "input_columns": len(df.columns),
            "steps": [],
            "renamed_columns": {},
            "missing_values": {},
        }

        # Detect before standardising: renaming strips the symbol that says
        # which currency the money columns are in ("(£m)" -> "currency_m").
        report["currency"] = _detect_currency(df)

        cleaned = df.clone()
        if options["standardize_columns"]:
            original_columns = cleaned.columns
            standardized = _standardize_column_names(original_columns)
            cleaned.columns = standardized
            report["renamed_columns"] = {
                original: new
                for original, new in zip(original_columns, standardized, strict=False)
                if original != new
            }
            if report["renamed_columns"]:
                report["steps"].append("standardized_column_names")

        if options["clean_text"]:
            cleaned = self._trim_text_values(cleaned)
            report["steps"].append("trimmed_text_values")

        if options["drop_empty"]:
            before_rows = cleaned.height
            before_columns = len(cleaned.columns)
            cleaned = self._drop_empty_rows_and_columns(cleaned)
            report["dropped_empty_rows"] = before_rows - cleaned.height
            report["dropped_empty_columns"] = before_columns - len(cleaned.columns)
            if report["dropped_empty_rows"] or report["dropped_empty_columns"]:
                report["steps"].append("dropped_empty_rows_columns")

        if options["normalize_dates"]:
            cleaned, converted_dates, date_report = self._normalize_date_columns(cleaned)
            report["converted_date_columns"] = converted_dates
            report["date_normalization"] = date_report
            if converted_dates:
                report["steps"].append("normalized_dates")

        withheld_columns: set[str] = set()
        if options["parse_currency_percent"]:
            cleaned, converted_numeric = self._parse_numeric_text_columns(cleaned)
            report["converted_numeric_columns"] = converted_numeric
            # Columns where some values were withheld rather than absent. Those
            # cells must stay empty: imputing a redacted cost invents public
            # spending — it inflated a £244,568m portfolio total to £367,548m.
            withheld_columns = {
                item["column"] for item in converted_numeric if item.get("withheld_values")
            }
            report["withheld_value_columns"] = sorted(withheld_columns)
            if converted_numeric:
                report["steps"].append("parsed_currency_percentage_numbers")

        if options["missing_data_strategy"] == "smart":
            before_rows = cleaned.height
            cleaned, missing_report = self._handle_missing_values(cleaned, withheld_columns)
            report["missing_values"] = missing_report
            report["dropped_rows_missing_critical_metrics"] = before_rows - cleaned.height
            if missing_report.get("steps"):
                report["steps"].extend(missing_report["steps"])

        if options["remove_duplicates"]:
            before_rows = cleaned.height
            cleaned = cleaned.unique(maintain_order=True)
            report["removed_duplicate_rows"] = before_rows - cleaned.height
            if report["removed_duplicate_rows"]:
                report["steps"].append("removed_duplicate_rows")

        if options["fuzzy_deduplicate"]:
            before_rows = cleaned.height
            cleaned, fuzzy_report = self._remove_fuzzy_duplicate_rows(cleaned)
            report["fuzzy_duplicates"] = fuzzy_report
            report["removed_fuzzy_duplicate_rows"] = before_rows - cleaned.height
            if report["removed_fuzzy_duplicate_rows"]:
                report["steps"].append("removed_fuzzy_duplicate_rows")
        else:
            report["removed_fuzzy_duplicate_rows"] = 0

        if options["outlier_policy"] == "cap":
            cleaned, cap_report = self._cap_outlier_values(cleaned)
            report["outlier_capping"] = cap_report
            report["capped_outlier_values"] = cap_report.get("capped_values", 0)
            report["excluded_outlier_rows"] = 0
            if report["capped_outlier_values"]:
                report["steps"].append("capped_outlier_values")
        elif options["outlier_policy"] == "exclude":
            before_rows = cleaned.height
            cleaned = self._exclude_outlier_rows(cleaned)
            report["excluded_outlier_rows"] = before_rows - cleaned.height
            report["capped_outlier_values"] = 0
            if report["excluded_outlier_rows"]:
                report["steps"].append("excluded_outlier_rows")
        else:
            report["excluded_outlier_rows"] = 0
            report["capped_outlier_values"] = 0

        report["output_rows"] = cleaned.height
        report["output_columns"] = len(cleaned.columns)
        return cleaned, report

    def _trim_text_values(self, df: pl.DataFrame) -> pl.DataFrame:
        expressions = []
        for column in df.columns:
            if df[column].dtype != pl.String:
                continue
            stripped = (
                pl.col(column)
                .str.replace_all(r"\s+", " ")
                .str.strip_chars()
            )
            expressions.append(
                pl.when(stripped.str.to_lowercase().is_in(_MISSING_TEXT_VALUES))
                .then(None)
                .otherwise(stripped)
                .alias(column)
            )
        return df.with_columns(expressions) if expressions else df

    def _drop_empty_rows_and_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df

        keep_columns = [column for column in df.columns if df[column].null_count() < df.height]
        if len(keep_columns) != len(df.columns):
            df = df.select(keep_columns)
        if not df.columns:
            return df
        return df.filter(pl.any_horizontal([pl.col(column).is_not_null() for column in df.columns]))

    def _parse_numeric_text_columns(self, df: pl.DataFrame) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
        expressions = []
        converted: list[dict[str, Any]] = []
        for column in df.columns:
            if df[column].dtype != pl.String:
                continue
            series = df[column]
            non_null = series.drop_nulls().len()
            if non_null == 0:
                continue
            if _looks_like_date_column(_standardize_column_name(column), series):
                continue
            values = series.to_list()
            parsed_values = [_parse_numeric_text_value(value) for value in values]
            numeric_count = sum(value is not None for value in parsed_values)
            # Rows whose value was withheld ("Exempt under Section 43 of the
            # Freedom of Information Act 2000") carry a missing number, not a
            # category, so they must not count against the column being numeric.
            withheld_count = sum(
                1
                for value, parsed in zip(values, parsed_values, strict=True)
                if parsed is None and value is not None and _looks_like_withheld_value(str(value))
            )
            candidates = non_null - withheld_count
            numeric_share = numeric_count / candidates if candidates else 0.0
            # The floor keeps a mostly-prose column from converting on the back
            # of a handful of numbers.
            numeric_enough = numeric_share >= 0.85 and numeric_count >= 0.2 * non_null
            if numeric_enough:
                expressions.append(pl.Series(column, parsed_values, dtype=pl.Float64).alias(column))
                converted.append(
                    {
                        "column": column,
                        "converted_values": numeric_count,
                        "total_non_null": non_null,
                        "detected_currency": _looks_like_currency_column(column, series),
                        "detected_percent": _looks_like_percentage_column(column, series),
                        "withheld_values": withheld_count,
                    }
                )
                continue
            cleaned = (
                series.str.strip_chars()
                .str.replace_all(r"^\((.*)\)$", r"-${1}")
                .str.replace_all(r"[$£€¥,\s%]", "")
            )
            numeric = cleaned.cast(pl.Float64, strict=False)
            numeric_count = numeric.drop_nulls().len()
            numeric_share = numeric_count / candidates if candidates else 0.0
            if numeric_share >= 0.85 and numeric_count >= 0.2 * non_null:
                expressions.append(
                    pl.col(column)
                    .str.strip_chars()
                    .str.replace_all(r"^\((.*)\)$", r"-${1}")
                    .str.replace_all(r"[$£€¥,\s%]", "")
                    .cast(pl.Float64, strict=False)
                    .alias(column)
                )
                converted.append(
                    {
                        "column": column,
                        "converted_values": numeric_count,
                        "total_non_null": non_null,
                        "detected_currency": _looks_like_currency_column(column, series),
                        "detected_percent": _looks_like_percentage_column(column, series),
                        "withheld_values": withheld_count,
                    }
                )
        if expressions:
            df = df.with_columns(expressions)
        return df, converted

    def _handle_missing_values(
        self, df: pl.DataFrame, withheld_columns: set[str] | None = None
    ) -> tuple[pl.DataFrame, dict[str, Any]]:
        # Columns whose gaps are withheld values ("Exempt under Section 43 of the
        # Freedom of Information Act 2000") are left exactly as they are: the
        # number exists but was not published, so filling it fabricates data and
        # dropping its row loses the project entirely.
        protected = withheld_columns or set()
        report: dict[str, Any] = {
            "strategy": "smart",
            "steps": [],
            "numeric_imputations": [],
            "categorical_imputations": [],
            "withheld_columns_left_empty": sorted(protected),
        }
        if df.is_empty():
            return df, report

        # Only treat a numeric column as a "required metric" for the
        # any-metric-present check below if it's actually populated across
        # most rows. A sparsely-filled numeric column (e.g. an optional
        # "hours logged" field on a task tracker) isn't a core metric —
        # using it here would drop nearly every row just for lacking a
        # field most rows were never expected to have.
        numeric_metric_columns = [
            column
            for column in df.columns
            if _is_numeric_dtype(df[column].dtype)
            and column not in protected
            and not _looks_like_identifier_column(column)
            and not _looks_like_year_column(column)
            and (df[column].null_count() / df.height) <= _SPARSE_NUMERIC_METRIC_NULL_RATIO
        ]
        if numeric_metric_columns:
            before_rows = df.height
            df = df.filter(
                pl.any_horizontal([pl.col(column).is_not_null() for column in numeric_metric_columns])
            )
            dropped = before_rows - df.height
            if dropped:
                report["steps"].append("dropped_rows_missing_all_numeric_metrics")
                report["dropped_rows_missing_all_numeric_metrics"] = dropped

        expressions = []
        has_date_column = any(_is_date_dtype(df[column].dtype) for column in df.columns)
        for column in df.columns:
            null_count = df[column].null_count()
            if null_count == 0:
                continue

            if column in protected:
                continue

            dtype = df[column].dtype
            if _is_numeric_dtype(dtype) and not _looks_like_identifier_column(column):
                # A sparse numeric column (e.g. an optional "hours logged"
                # field where most rows never had a value) isn't missing
                # data to reconstruct — its nulls are real absences. Filling
                # them with a median/interpolated guess fabricates values
                # that never existed and silently inflates sums/averages.
                if (null_count / df.height) > _SPARSE_NUMERIC_METRIC_NULL_RATIO:
                    continue
                median = df[column].median()
                if median is None:
                    continue
                expr = pl.col(column).cast(pl.Float64)
                method = "median"
                if has_date_column and df.height >= 3:
                    expr = expr.interpolate().fill_null(strategy="forward")
                    method = "interpolate_forward_fill_median"
                expressions.append(expr.fill_null(median).alias(column))
                report["numeric_imputations"].append(
                    {"column": column, "method": method, "filled": null_count, "value": median}
                )
                continue

            if dtype == pl.String:
                fill_value = "Unknown"
                expressions.append(pl.col(column).fill_null(fill_value).alias(column))
                report["categorical_imputations"].append(
                    {"column": column, "method": "unknown_label", "filled": null_count}
                )

        if expressions:
            df = df.with_columns(expressions)
            report["steps"].append("imputed_missing_values")
        return df, report

    def _remove_fuzzy_duplicate_rows(self, df: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, Any]]:
        report: dict[str, Any] = {
            "enabled": True,
            "method": "normalized_text_signature_similarity",
            "threshold": 0.94,
            "candidate_rows": min(df.height, 5000),
            "removed_rows": 0,
            "examples": [],
        }
        if df.height < 2 or df.height > 5000:
            if df.height > 5000:
                report["skipped"] = "Dataset too large for bounded fuzzy deduplication"
            return df, report

        text_columns = [
            column
            for column in df.columns
            if df[column].dtype == pl.String
            and not _looks_like_identifier_column(column)
        ][:8]
        if not text_columns:
            return df, report

        rows = df.to_dicts()
        non_text_columns = [column for column in df.columns if column not in text_columns]
        kept_indexes: list[int] = []
        signatures: list[tuple[str, str]] = []
        dropped_indexes: set[int] = set()

        for index, row in enumerate(rows):
            text_signature = _row_text_signature(row, text_columns)
            exact_signature = _row_exact_signature(row, non_text_columns)
            signature = (exact_signature, text_signature)
            if not text_signature:
                kept_indexes.append(index)
                signatures.append(signature)
                continue

            duplicate_of: int | None = None
            for kept_position, kept_signature in enumerate(signatures):
                if not kept_signature[1] or exact_signature != kept_signature[0]:
                    continue
                if SequenceMatcher(None, text_signature, kept_signature[1]).ratio() >= 0.94:
                    duplicate_of = kept_indexes[kept_position]
                    break

            if duplicate_of is None:
                kept_indexes.append(index)
                signatures.append(signature)
            else:
                dropped_indexes.add(index)
                if len(report["examples"]) < 5:
                    report["examples"].append(
                        {
                            "dropped_row": index,
                            "matched_row": duplicate_of,
                            "text_signature": text_signature,
                        }
                    )

        if not dropped_indexes:
            return df, report

        report["removed_rows"] = len(dropped_indexes)
        return df.with_row_index("_row_index").filter(
            ~pl.col("_row_index").is_in(sorted(dropped_indexes))
        ).drop("_row_index"), report

    def _normalize_date_columns(
        self,
        df: pl.DataFrame,
    ) -> tuple[pl.DataFrame, list[str], dict[str, Any]]:
        expressions = []
        converted: list[str] = []
        report: dict[str, Any] = {"columns": []}
        for column in df.columns:
            if df[column].dtype != pl.String:
                continue
            normalized_name = _standardize_column_name(column)
            if not _looks_like_date_column(normalized_name, df[column]):
                continue

            non_null = df[column].drop_nulls().len()
            if non_null == 0:
                continue

            parsed_series, parsed_report = _parse_mixed_datetime_series(df[column], column)
            parsed_count = parsed_series.drop_nulls().len() if parsed_series is not None else 0
            if parsed_count / non_null >= 0.7:
                expressions.append(parsed_series.alias(column))
                converted.append(column)
                report["columns"].append(parsed_report)

        if expressions:
            df = df.with_columns(expressions)
        return df, converted, report

    def _exclude_outlier_rows(self, df: pl.DataFrame) -> pl.DataFrame:
        numeric_columns = _outlier_candidate_columns(df)
        if not numeric_columns or df.is_empty():
            return df

        predicates = []
        for column in numeric_columns:
            series = df[column].drop_nulls()
            if series.len() < 8:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            if q1 is None or q3 is None:
                continue
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            predicates.append(
                pl.col(column).is_null() | pl.col(column).is_between(lower, upper)
            )

        if not predicates:
            return df
        return df.filter(pl.all_horizontal(predicates))

    def _cap_outlier_values(self, df: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, Any]]:
        report: dict[str, Any] = {
            "enabled": True,
            "method": "iqr_winsorization",
            "lower_percentile": 0.01,
            "upper_percentile": 0.99,
            "columns": [],
            "capped_values": 0,
        }
        expressions = []
        for column in _outlier_candidate_columns(df):
            series = df[column].drop_nulls()
            if series.len() < 8:
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            if q1 is None or q3 is None:
                continue

            iqr = q3 - q1
            if iqr <= 0:
                continue

            lower_fence = q1 - 1.5 * iqr
            upper_fence = q3 + 1.5 * iqr
            lower_quantile = series.quantile(0.01)
            upper_quantile = series.quantile(0.99)
            lower_cap = (
                max(float(lower_quantile), float(lower_fence))
                if lower_quantile is not None
                else float(lower_fence)
            )
            upper_cap = (
                min(float(upper_quantile), float(upper_fence))
                if upper_quantile is not None
                else float(upper_fence)
            )
            low_count = int(df.filter(pl.col(column) < lower_fence).height)
            high_count = int(df.filter(pl.col(column) > upper_fence).height)
            capped_count = low_count + high_count
            if capped_count == 0:
                continue

            expressions.append(
                pl.when(pl.col(column) < lower_fence)
                .then(lower_cap)
                .when(pl.col(column) > upper_fence)
                .then(upper_cap)
                .otherwise(pl.col(column))
                .alias(column)
            )
            report["columns"].append(
                {
                    "column": column,
                    "lower_fence": float(lower_fence),
                    "upper_fence": float(upper_fence),
                    "lower_cap": float(lower_cap),
                    "upper_cap": float(upper_cap),
                    "capped_values": capped_count,
                }
            )
            report["capped_values"] += capped_count

        if expressions:
            df = df.with_columns(expressions)
        return df, report

    def _normalize_report_table(self, df: pl.DataFrame) -> pl.DataFrame:
        """Promote a detected table header row and remove report title rows."""
        if df.is_empty() or df.height < 2:
            return df

        header_index = self._detect_header_row(df)
        if header_index is None:
            return self._cast_numeric_like_columns(df)

        header_values = df.row(header_index)
        names = self._make_column_names(header_values)
        normalized = df.slice(header_index + 1)
        normalized.columns = names
        normalized = normalized.filter(
            pl.any_horizontal([pl.col(col).is_not_null() for col in normalized.columns])
        )
        return self._cast_numeric_like_columns(normalized)

    def _normalize_excel_sheets(
        self, sheets: pl.DataFrame | dict[str, pl.DataFrame]
    ) -> pl.DataFrame:
        if isinstance(sheets, pl.DataFrame):
            return self._normalize_report_table(sheets)

        frames: list[pl.DataFrame] = []
        for _sheet_name, raw_sheet in sheets.items():
            normalized = self._normalize_report_table(raw_sheet)
            if normalized.is_empty():
                continue
            frames.append(normalized)

        if not frames:
            return pl.DataFrame()
        if len(frames) == 1:
            return frames[0]
        joined = self._join_sheets_by_common_dimensions(frames)
        if joined is not None:
            return joined
        frames = [
            frame.with_columns(pl.lit(sheet_name).alias("Sheet"))
            for sheet_name, frame in zip(sheets.keys(), frames, strict=False)
        ]
        return pl.concat(frames, how="diagonal_relaxed")

    def _join_sheets_by_common_dimensions(self, frames: list[pl.DataFrame]) -> pl.DataFrame | None:
        common_columns = set(frames[0].columns)
        for frame in frames[1:]:
            common_columns &= set(frame.columns)

        join_columns = [
            column
            for column in frames[0].columns
            if column in common_columns and not _is_numeric_dtype(frames[0][column].dtype)
        ]
        if not join_columns:
            return None

        numeric_sets = [
            {column for column in frame.columns if _is_numeric_dtype(frame[column].dtype)}
            for frame in frames
        ]
        unique_numeric_columns = set().union(*numeric_sets)
        if not unique_numeric_columns:
            return None

        # If every sheet has the same metric columns, keep the sheets as separate
        # observations. If sheets expose different metric columns keyed by the same
        # dimensions, merge them side-by-side.
        if all(metric_columns == numeric_sets[0] for metric_columns in numeric_sets[1:]):
            return None

        prepared_frames = [self._aggregate_sheet(frame, join_columns) for frame in frames]
        combined = prepared_frames[0]
        for frame in prepared_frames[1:]:
            combined = combined.join(
                frame,
                on=join_columns,
                how="full",
                coalesce=True,
            )

        fill_expressions = [
            pl.col(column).fill_null(0).alias(column)
            for column in combined.columns
            if column not in join_columns and _is_numeric_dtype(combined[column].dtype)
        ]
        if fill_expressions:
            combined = combined.with_columns(fill_expressions)
        return combined

    def _aggregate_sheet(self, frame: pl.DataFrame, join_columns: list[str]) -> pl.DataFrame:
        expressions = []
        for column in frame.columns:
            if column in join_columns:
                continue
            if _is_numeric_dtype(frame[column].dtype):
                expressions.append(pl.col(column).sum().alias(column))
            else:
                expressions.append(pl.col(column).drop_nulls().first().alias(column))

        if not expressions:
            return frame.unique(subset=join_columns, keep="first")
        return frame.group_by(join_columns).agg(expressions)

    def _detect_header_row(self, df: pl.DataFrame) -> int | None:
        best_index = 0
        best_score = self._header_score(df, 0)
        scan_limit = min(df.height - 1, self.HEADER_SCAN_ROWS)

        for row_index in range(scan_limit):
            score = self._header_score(df, row_index)
            if score > best_score:
                best_score = score
                best_index = row_index

        if best_score < 4:
            return None
        return best_index

    def _header_score(self, df: pl.DataFrame, row_index: int) -> float:
        row = df.row(row_index)
        next_row = df.row(row_index + 1) if row_index + 1 < df.height else ()
        values = [_clean_cell(value) for value in row]
        next_values = [_clean_cell(value) for value in next_row]

        non_empty = [value for value in values if value]
        if len(non_empty) < 2:
            return -10.0

        density = len(non_empty) / max(len(values), 1)
        next_density = len([value for value in next_values if value]) / max(len(next_values), 1)
        grid_score = self._grid_continuity_score(df, row_index)
        numeric_cells = sum(_is_numeric_text(value) for value in non_empty)
        unnamed_cells = sum(value.lower().startswith("__unnamed__") for value in non_empty)
        header_words = sum(_looks_like_header(value) for value in non_empty)
        next_numeric = sum(_is_numeric_text(value) for value in next_values if value)
        next_non_empty = sum(1 for value in next_values if value)

        score = len(non_empty) * 2
        score += header_words * 3
        score += min(next_numeric, 3) * 2
        score += min(next_non_empty, len(non_empty))
        score += density * 4
        score += next_density * 3
        score += grid_score * 3
        score -= numeric_cells * 2
        score -= unnamed_cells * 4
        score -= row_index * 0.05
        return score

    def _grid_continuity_score(self, df: pl.DataFrame, row_index: int) -> float:
        widths: list[int] = []
        scan_end = min(df.height, row_index + 6)
        for index in range(row_index, scan_end):
            values = [_clean_cell(value) for value in df.row(index)]
            widths.append(sum(1 for value in values if value))
        if len(widths) < 2 or widths[0] < 2:
            return 0.0

        similar_rows = sum(1 for width in widths[1:] if width >= max(2, widths[0] - 1))
        return similar_rows / max(len(widths) - 1, 1)

    def _make_column_names(self, values: tuple[Any, ...]) -> list[str]:
        names: list[str] = []
        seen: dict[str, int] = {}
        for index, value in enumerate(values, start=1):
            base = _clean_cell(value) or f"column_{index}"
            base = " ".join(base.split())
            count = seen.get(base, 0)
            seen[base] = count + 1
            names.append(base if count == 0 else f"{base}_{count + 1}")
        return names

    def _cast_numeric_like_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        expressions = []
        for column in df.columns:
            series = df[column]
            if series.dtype != pl.String:
                continue

            cleaned = series.str.replace_all(",", "").str.strip_chars()
            numeric = cleaned.cast(pl.Float64, strict=False)
            non_null = series.drop_nulls().len()
            numeric_count = numeric.drop_nulls().len()
            # Leave columns whose non-numeric cells say the value was withheld
            # ("Exempt under Section 43 of the Freedom of Information Act
            # 2000"). Casting here would turn them into anonymous nulls before
            # cleaning can record them, and those rows then look like ordinary
            # gaps: imputed, or enough to drop the row entirely.
            if _has_withheld_values(series):
                continue
            if non_null and numeric_count / non_null >= 0.85:
                # Whole-number columns become integers so codes and counts
                # don't render as "2.0" in labels, charts, and stats.
                values = numeric.drop_nulls()
                if values.len() and (values % 1 == 0).all():
                    numeric = numeric.cast(pl.Int64)
                expressions.append(numeric.alias(column))

        if not expressions:
            return df
        return df.with_columns(expressions)

    async def read_to_duckdb(
        self, conn: duckdb.DuckDBPyConnection, file_path: str, extension: str, table_name: str = "data"
    ) -> int:
        """Load file into DuckDB table, return row count. Deprecated in favor
        of read_to_duckdb_ex, which also reports whether the source was
        truncated at SAMPLE_ROWS; kept for callers that only need the count.
        """
        row_count, _truncated = await self.read_to_duckdb_ex(conn, file_path, extension, table_name)
        return row_count

    async def read_to_duckdb_ex(
        self, conn: duckdb.DuckDBPyConnection, file_path: str, extension: str, table_name: str = "data"
    ) -> tuple[int, bool]:
        """Load file into DuckDB table. Returns (row_count, truncated).

        Every format is capped at SAMPLE_ROWS so a given file size behaves
        consistently regardless of format, instead of CSV/Excel being sampled
        while JSON/Parquet loaded in full.
        """
        return await asyncio.to_thread(
            self._load_duckdb_sync, conn, file_path, extension, table_name
        )

    def _load_duckdb_sync(
        self, conn: duckdb.DuckDBPyConnection, file_path: str, extension: str, table_name: str
    ) -> tuple[int, bool]:
        ext = extension.lower()
        truncated = False
        if ext == ".csv" or ext == ".tsv":
            df, truncated = self._read_file_ex(file_path, ext)
            conn.register("_temp_df", df.to_pandas())
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df")
        elif ext in (".xlsx", ".xls"):
            # DuckDB doesn't support Excel natively; load via polars first.
            df, truncated = self._read_file_ex(file_path, ext)
            conn.register("_temp_df", df.to_pandas())
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df")
        elif ext == ".json":
            json_count_row = conn.execute(
                f"SELECT COUNT(*) FROM read_json_auto('{file_path}')"
            ).fetchone()
            total = json_count_row[0] if json_count_row is not None else 0
            conn.execute(f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT * FROM read_json_auto('{file_path}') LIMIT {self.SAMPLE_ROWS}
            """)
            truncated = total > self.SAMPLE_ROWS
        elif ext == ".parquet":
            parquet_count_row = conn.execute(
                f"SELECT COUNT(*) FROM read_parquet('{file_path}')"
            ).fetchone()
            total = parquet_count_row[0] if parquet_count_row is not None else 0
            conn.execute(f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT * FROM read_parquet('{file_path}') LIMIT {self.SAMPLE_ROWS}
            """)
            truncated = total > self.SAMPLE_ROWS
        else:
            raise ValueError(f"Unsupported extension: {ext}")

        result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        row_count = result[0] if result else 0
        return row_count, truncated

    async def combine_uploaded_files(
        self,
        uploaded_files: list[Any],
        output_path: str,
        relationship_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._combine_uploaded_files_sync,
            uploaded_files,
            output_path,
            relationship_context or {},
        )

    def _combine_uploaded_files_sync(
        self,
        uploaded_files: list[Any],
        output_path: str,
        relationship_context: dict[str, Any],
    ) -> dict[str, Any]:
        frames = []
        for uploaded_file in uploaded_files:
            extension = Path(uploaded_file.storage_path).suffix.lower()
            frame = self._read_file(uploaded_file.storage_path, extension)
            if frame.is_empty():
                continue
            frame = frame.with_columns(
                pl.lit(uploaded_file.original_filename).alias("Source file")
            )
            frames.append(frame)

        if not frames:
            combined = pl.DataFrame()
        else:
            combined = self._combine_frames(frames, relationship_context)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        combined.write_parquet(output_path)
        return self._profile_dataframe(combined)

    def _combine_frames(
        self,
        frames: list[pl.DataFrame],
        relationship_context: dict[str, Any],
    ) -> pl.DataFrame:
        combine_strategy = relationship_context.get("combine_strategy", "portfolio")
        if combine_strategy != "join":
            return pl.concat(frames, how="diagonal_relaxed")

        suggestion = _top_relationship_suggestion(relationship_context)
        suggestion_type = suggestion.get("type") if suggestion else None

        if suggestion_type == "join":
            suggested_columns = suggestion.get("columns", [])
            join_columns = _matching_join_columns(
                frames,
                suggested_columns if isinstance(suggested_columns, list) else [],
            )
            if join_columns:
                prepared = self._prepare_join_frames(frames, join_columns)
                combined = prepared[0]
                for frame in prepared[1:]:
                    combined = combined.join(
                        frame,
                        on=join_columns,
                        how="full",
                        coalesce=True,
                        suffix="_related",
                    )
                return combined

        return pl.concat(frames, how="diagonal_relaxed")

    def _prepare_join_frames(
        self,
        frames: list[pl.DataFrame],
        join_columns: list[str],
    ) -> list[pl.DataFrame]:
        prepared: list[pl.DataFrame] = []
        seen_columns = set(join_columns)

        for index, frame in enumerate(frames, start=1):
            if "Source file" in frame.columns:
                frame = frame.drop("Source file")

            aggregated = self._aggregate_sheet(frame, join_columns)
            rename_map: dict[str, str] = {}
            for column in aggregated.columns:
                if column in join_columns:
                    continue
                if column in seen_columns:
                    rename_map[column] = f"{column} related {index}"
                seen_columns.add(rename_map.get(column, column))

            if rename_map:
                aggregated = aggregated.rename(rename_map)
            prepared.append(aggregated)

        return prepared

    def _profile_dataframe(self, df: pl.DataFrame) -> dict[str, Any]:
        columns = []
        for col in df.columns:
            series = df[col]
            null_count = series.null_count()
            non_null_count = len(series) - null_count
            try:
                unique_count = series.n_unique()
            except Exception:
                unique_count = 0
            sample_raw = series.drop_nulls().head(5).to_list()
            sample_values = [str(value) for value in sample_raw]
            columns.append({
                "name": col,
                "dtype": str(series.dtype),
                "non_null_count": non_null_count,
                "null_count": null_count,
                "unique_count": unique_count,
                "sample_values": sample_values,
            })
        return {
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": columns,
        }


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_numeric_text(value: str) -> bool:
    if not value:
        return False
    normalized = value.replace(",", "").replace("£", "").replace("$", "").strip()
    try:
        float(normalized)
    except ValueError:
        return False
    return True


def _parse_numeric_text_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _MISSING_TEXT_VALUES:
        return None

    lower = text.lower().strip()
    negative = lower.startswith("-") or (
        lower.startswith("(") and lower.endswith(")")
    )
    lower = lower.strip("()")

    multiplier = 1.0
    if re.search(r"\b(bn|billion)\b", lower) or re.search(r"\d\s*b$", lower):
        multiplier = 1_000_000_000.0
    elif re.search(r"\b(m|mn|million)\b", lower) or re.search(r"\d\s*m$", lower):
        multiplier = 1_000_000.0
    elif re.search(r"\b(k|thousand)\b", lower) or re.search(r"\d\s*k$", lower):
        multiplier = 1_000.0

    cleaned = lower
    cleaned = re.sub(r"\b(usd|eur|gbp|cad|aud|ngn|jpy|cny|inr|zar)\b", "", cleaned)
    cleaned = re.sub(r"[,$£€¥₹₦%]", "", cleaned)
    cleaned = re.sub(r"\b(bn|billion|mn|million|thousand|k|m|b)\b", "", cleaned)
    cleaned = cleaned.replace(" ", "")
    # A magnitude suffix stuck to the digits ("1.2k") isn't caught by the word
    # boundary above; its multiplier was already read from the raw text.
    cleaned = re.sub(r"(?<=\d)(bn|mn|[kmb])$", "", cleaned)

    # Fullmatch, not search: the cell must *be* a number once symbols, separators
    # and magnitude words are stripped. Searching pulled the first number out of
    # prose — "Compared to financial year 22/23-Q4, ..." became 22.0, and with
    # enough such rows a narrative column was rewritten as a numeric metric.
    match = re.fullmatch(r"[-+]?\d*\.?\d+", cleaned)
    if not match:
        return None
    try:
        parsed = float(match.group(0)) * multiplier
    except ValueError:
        return None
    return -abs(parsed) if negative else parsed


CURRENCY_BY_SYMBOL = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY", "₹": "INR", "₦": "NGN"}
SYMBOL_BY_CURRENCY = {code: symbol for symbol, code in CURRENCY_BY_SYMBOL.items()}
_CURRENCY_CODE_RE = re.compile(r"\b(gbp|usd|eur|jpy|inr|ngn|cad|aud)\b", re.IGNORECASE)


def detect_currency_in_text(text: str) -> dict[str, str] | None:
    """Currency named by a header or cell, as `{"code", "symbol"}`, else None."""
    for symbol, code in CURRENCY_BY_SYMBOL.items():
        if symbol in text:
            return {"code": code, "symbol": symbol}
    match = _CURRENCY_CODE_RE.search(text)
    if match:
        code = match.group(1).upper()
        return {"code": code, "symbol": SYMBOL_BY_CURRENCY.get(code, "")}
    return None


def _detect_currency(df: pl.DataFrame) -> dict[str, Any] | None:
    """Which currency this file's money columns are in.

    Headers carry it far more often than cells ("Financial Year Baseline (£m)"),
    so they are checked first. Without this every amount was formatted as US
    dollars, which turned UK government £m figures into "$23,078,507,463.50".
    """
    for column in df.columns:
        found = detect_currency_in_text(str(column))
        if found:
            return {**found, "evidence": f"column header {str(column)[:60]!r}"}
    for column in df.columns:
        if df[column].dtype != pl.String:
            continue
        for value in df[column].drop_nulls().head(20).to_list():
            found = detect_currency_in_text(str(value))
            if found:
                return {**found, "evidence": f"value in {str(column)[:40]!r}: {str(value)[:30]!r}"}
    return None


_WITHHELD_VALUE_RE = re.compile(
    r"\b(exempt|redacted|withheld|confidential|commercially\s+sensitive|"
    r"not\s+(available|applicable|disclosed|reported|published)|tbc|tbd)\b",
    re.IGNORECASE,
)


def _has_withheld_values(series: pl.Series) -> bool:
    """Whether any sampled cell says its value was withheld rather than absent."""
    return any(
        _looks_like_withheld_value(str(value))
        for value in series.drop_nulls().head(200).to_list()
    )


def _looks_like_withheld_value(text: str) -> bool:
    """Whether a cell says the number was withheld rather than giving a category.

    Government publications routinely carry "Exempt under Section 43 of the
    Freedom of Information Act 2000" inside otherwise numeric money columns —
    15 of 49 rows in the GMPP data. Counting those as non-numeric evidence kept
    genuine metric columns as text; counting them as missing keeps the metric.
    """
    return bool(_WITHHELD_VALUE_RE.search(text))


def _looks_like_currency_column(column: str, series: pl.Series) -> bool:
    normalized = _standardize_column_name(column)
    if any(term in normalized for term in ("price", "revenue", "sales", "cost", "amount", "value", "income", "spend")):
        return True
    sample = [str(value) for value in series.drop_nulls().head(30).to_list()]
    return any(
        re.search(r"[$£€¥₹₦]|\b(usd|eur|gbp|cad|aud|ngn|jpy|cny|inr|zar)\b", value, re.IGNORECASE)
        for value in sample
    )


def _looks_like_percentage_column(column: str, series: pl.Series) -> bool:
    normalized = _standardize_column_name(column)
    if any(term in normalized for term in ("pct", "percent", "percentage", "rate", "margin")):
        return True
    sample = [str(value) for value in series.drop_nulls().head(30).to_list()]
    return any("%" in value for value in sample)


def _is_numeric_dtype(dtype: pl.DataType) -> bool:
    return dtype.is_numeric()


def _is_date_dtype(dtype: pl.DataType) -> bool:
    dtype_name = str(dtype).lower()
    return "date" in dtype_name or "time" in dtype_name


def _outlier_candidate_columns(df: pl.DataFrame) -> list[str]:
    return [
        column
        for column in df.columns
        if _is_numeric_dtype(df[column].dtype)
        and not _looks_like_identifier_column(column)
        and not _looks_like_year_column(column)
    ][:20]


def _cleaning_options(options: dict[str, Any]) -> dict[str, Any]:
    outlier_policy = str(options.get("outlier_policy") or "keep").lower()
    if outlier_policy not in {"keep", "cap", "exclude"}:
        outlier_policy = "keep"
    missing_data_strategy = str(options.get("missing_data_strategy") or "smart").lower()
    if missing_data_strategy not in {"smart", "none"}:
        missing_data_strategy = "smart"

    return {
        "remove_duplicates": bool(options.get("remove_duplicates", True)),
        "fuzzy_deduplicate": bool(options.get("fuzzy_deduplicate", False)),
        "standardize_columns": bool(options.get("standardize_columns", True)),
        "normalize_dates": bool(options.get("normalize_dates", True)),
        "clean_text": bool(options.get("clean_text", True)),
        "parse_currency_percent": bool(options.get("parse_currency_percent", True)),
        "drop_empty": bool(options.get("drop_empty", True)),
        "missing_data_strategy": missing_data_strategy,
        "outlier_policy": outlier_policy,
        "semantic_categorical_merging": bool(options.get("semantic_categorical_merging", True)),
    }


def _standardize_column_names(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    standardized: list[str] = []
    for index, column in enumerate(columns, start=1):
        base = _standardize_column_name(column) or f"column_{index}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        standardized.append(base if count == 0 else f"{base}_{count + 1}")
    return standardized


def _standardize_column_name(column: str) -> str:
    name = str(column).strip().lower()
    name = name.replace("&", " and ")
    name = re.sub(r"[%]+", " pct ", name)
    name = re.sub(r"[$£€¥]+", " currency ", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def _looks_like_identifier_column(column: str) -> bool:
    normalized = _standardize_column_name(column)
    return (
        normalized == "id"
        or normalized.endswith("_id")
        or normalized.startswith("id_")
        or normalized.endswith("_uuid")
        or normalized.endswith("_guid")
    )


def _looks_like_year_column(column: str) -> bool:
    normalized = _standardize_column_name(column)
    return normalized == "year" or normalized.endswith("_year")


def _looks_like_date_column(normalized_name: str, series: pl.Series) -> bool:
    """A date column needs date-looking *values*; the name only lowers the bar.

    Name alone used to be enough, so a prose column name containing the word
    "time" ("...assessment of the project at a fixed point in time...") was
    treated as a date column even though its values were Red/Amber/Green.
    """
    tokens = set(re.split(r"[^a-z0-9]+", normalized_name.lower()))
    name_hint = bool(
        tokens & {"date", "time", "timestamp", "datetime", "month", "period"}
        or normalized_name.endswith("_at")
    )

    sample = [str(value).strip() for value in series.drop_nulls().head(20).to_list()]
    if not sample:
        return False
    date_like = sum(_looks_like_date_value(value) for value in sample)
    return date_like / len(sample) >= (0.5 if name_hint else 0.7)


def _looks_like_date_value(value: str) -> bool:
    if len(value) < 6 or len(value) > 64:
        return False
    return bool(
        re.search(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", value)
        or re.search(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}", value)
        or re.search(r"\d{4}-\d{2}-\d{2}T", value)
    )


def _parse_mixed_datetime_series(
    series: pl.Series,
    column: str,
) -> tuple[pl.Series | None, dict[str, Any]]:
    raw_values = [
        None if value is None else str(value).strip()
        for value in series.to_list()
    ]
    normalized_values = [
        None if value is None or value.lower() in _MISSING_TEXT_VALUES else value
        for value in raw_values
    ]
    pandas_series = pd.Series(normalized_values, dtype="object")

    candidates = [
        ("month_first", _to_datetime_mixed(pandas_series, dayfirst=False)),
        ("day_first", _to_datetime_mixed(pandas_series, dayfirst=True)),
    ]
    strategy, parsed = max(candidates, key=lambda item: int(item[1].notna().sum()))
    parsed_count = int(parsed.notna().sum())
    has_time_or_timezone = any(
        _has_time_or_timezone(value)
        for value in normalized_values
        if value
    )

    report = {
        "column": column,
        "strategy": strategy,
        "parsed_values": parsed_count,
        "failed_values": int(len([value for value in normalized_values if value]) - parsed_count),
        "standard": "UTC datetime" if has_time_or_timezone else "YYYY-MM-DD",
    }
    if parsed_count == 0:
        return None, report

    if has_time_or_timezone:
        datetimes = [
            None if pd.isna(value) else value.to_pydatetime().replace(tzinfo=None)
            for value in parsed
        ]
        return pl.Series(column, datetimes, dtype=pl.Datetime("us")), report

    dates = [
        None if pd.isna(value) else value.date()
        for value in parsed
    ]
    return pl.Series(column, dates, dtype=pl.Date), report


def _to_datetime_mixed(values: pd.Series, *, dayfirst: bool) -> pd.Series:
    try:
        return pd.to_datetime(
            values,
            errors="coerce",
            utc=True,
            format="mixed",
            dayfirst=dayfirst,
        )
    except TypeError:
        return pd.to_datetime(
            values,
            errors="coerce",
            utc=True,
            dayfirst=dayfirst,
        )


def _has_time_or_timezone(value: str) -> bool:
    stripped = value.strip()
    has_time = bool(re.search(r"\d{1,2}:\d{2}", stripped))
    has_timezone = bool(re.search(r"(Z|[+-]\d{2}:?\d{2})$", stripped, re.IGNORECASE))
    has_timezone_word = "utc" in stripped.lower() or "gmt" in stripped.lower()
    return has_time or ((has_timezone or has_timezone_word) and ("T" in stripped or has_time))


def _row_text_signature(row: dict[str, Any], text_columns: list[str]) -> str:
    parts = []
    for column in text_columns:
        value = row.get(column)
        if value is None:
            continue
        normalized = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
        if normalized:
            parts.append(normalized)
    return " | ".join(parts)


def _row_exact_signature(row: dict[str, Any], columns: list[str]) -> str:
    parts = []
    for column in columns:
        value = row.get(column)
        if value is None:
            parts.append("<null>")
        else:
            parts.append(str(value).strip().lower())
    return "|".join(parts)


def _looks_like_header(value: str) -> bool:
    normalized = value.lower()
    header_terms = (
        "name",
        "organisation",
        "organization",
        "count",
        "total",
        "date",
        "year",
        "month",
        "amount",
        "value",
        "category",
        "type",
        "status",
        "number",
        "id",
    )
    return any(term in normalized for term in header_terms)


def _top_relationship_suggestion(context: dict[str, Any]) -> dict[str, Any]:
    suggestions = context.get("suggestions", [])
    if not isinstance(suggestions, list) or not suggestions:
        return {}
    first = suggestions[0]
    return first if isinstance(first, dict) else {}


def _matching_join_columns(
    frames: list[pl.DataFrame],
    suggested_columns: list[Any],
) -> list[str]:
    if not frames:
        return []

    common = set(frames[0].columns)
    for frame in frames[1:]:
        common &= set(frame.columns)

    suggested = [
        str(column)
        for column in suggested_columns
        if str(column) in common
    ]
    if suggested:
        return suggested

    return [
        column
        for column in frames[0].columns
        if column in common
        and column != "Source file"
        and not _is_numeric_dtype(frames[0][column].dtype)
    ][:3]
