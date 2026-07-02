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
            df = self._read_file(file_path, extension)
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
            }
        except Exception as exc:
            logger.warning("Profile failed", file_path=file_path, exc=str(exc))
            return {"row_count": None, "column_count": None, "columns": None}

    def _read_file(self, file_path: str, extension: str) -> pl.DataFrame:
        ext = extension.lower()
        if ext == ".csv" or ext == ".tsv":
            return self._read_delimited_file(file_path, ext)
        elif ext in (".xlsx", ".xls"):
            sheets = pl.read_excel(
                file_path,
                sheet_id=0,
                has_header=False,
                read_options={"n_rows": self.SAMPLE_ROWS},
                infer_schema_length=1000,
            )
            return self._normalize_excel_sheets(sheets)
        elif ext == ".json":
            return pl.read_json(file_path)
        elif ext == ".parquet":
            return pl.read_parquet(file_path, n_rows=self.SAMPLE_ROWS)
        else:
            raise ValueError(f"Unsupported extension: {ext}")

    def _read_delimited_file(self, file_path: str, extension: str) -> pl.DataFrame:
        encoding = self._detect_encoding(file_path)
        delimiter = self._detect_delimiter(file_path, encoding, extension)
        rows = self._read_delimited_rows(file_path, encoding, delimiter)
        if not rows:
            return pl.DataFrame()

        width = max(len(row) for row in rows)
        padded_rows = [
            [self._clean_raw_text_cell(value) for value in row] + [None] * (width - len(row))
            for row in rows
        ]
        df = pl.DataFrame(
            {f"column_{index + 1}": [row[index] for row in padded_rows] for index in range(width)}
        )
        return self._normalize_report_table(df)

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
        rows: list[list[str | None]] = []
        try:
            with open(file_path, encoding=encoding, errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                for row in reader:
                    rows.append(row)
                    if len(rows) >= self.SAMPLE_ROWS:
                        break
        except LookupError:
            with open(file_path, encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                for row in reader:
                    rows.append(row)
                    if len(rows) >= self.SAMPLE_ROWS:
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

        if options["parse_currency_percent"]:
            cleaned, converted_numeric = self._parse_numeric_text_columns(cleaned)
            report["converted_numeric_columns"] = converted_numeric
            if converted_numeric:
                report["steps"].append("parsed_currency_percentage_numbers")

        if options["missing_data_strategy"] == "smart":
            before_rows = cleaned.height
            cleaned, missing_report = self._handle_missing_values(cleaned)
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
            parsed_values = [_parse_numeric_text_value(value) for value in series.to_list()]
            numeric_count = sum(value is not None for value in parsed_values)
            if numeric_count / non_null >= 0.85:
                expressions.append(pl.Series(column, parsed_values, dtype=pl.Float64).alias(column))
                converted.append(
                    {
                        "column": column,
                        "converted_values": numeric_count,
                        "total_non_null": non_null,
                        "detected_currency": _looks_like_currency_column(column, series),
                        "detected_percent": _looks_like_percentage_column(column, series),
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
            if numeric_count / non_null >= 0.85:
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
                    }
                )
        if expressions:
            df = df.with_columns(expressions)
        return df, converted

    def _handle_missing_values(self, df: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, Any]]:
        report: dict[str, Any] = {
            "strategy": "smart",
            "steps": [],
            "numeric_imputations": [],
            "categorical_imputations": [],
        }
        if df.is_empty():
            return df, report

        numeric_metric_columns = [
            column
            for column in df.columns
            if _is_numeric_dtype(df[column].dtype)
            and not _looks_like_identifier_column(column)
            and not _looks_like_year_column(column)
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

            dtype = df[column].dtype
            if _is_numeric_dtype(dtype) and not _looks_like_identifier_column(column):
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
            if non_null and numeric_count / non_null >= 0.85:
                expressions.append(numeric.alias(column))

        if not expressions:
            return df
        return df.with_columns(expressions)

    async def read_to_duckdb(
        self, conn: duckdb.DuckDBPyConnection, file_path: str, extension: str, table_name: str = "data"
    ) -> int:
        """Load file into DuckDB table, return row count."""
        return await asyncio.to_thread(
            self._load_duckdb_sync, conn, file_path, extension, table_name
        )

    def _load_duckdb_sync(
        self, conn: duckdb.DuckDBPyConnection, file_path: str, extension: str, table_name: str
    ) -> int:
        ext = extension.lower()
        if ext == ".csv" or ext == ".tsv":
            df = self._read_file(file_path, ext)
            conn.register("_temp_df", df.to_pandas())
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df")
        elif ext in (".xlsx", ".xls"):
            # DuckDB doesn't support Excel natively; load via polars first.
            df = self._read_file(file_path, ext)
            conn.register("_temp_df", df.to_pandas())
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_df")
        elif ext == ".json":
            conn.execute(f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT * FROM read_json_auto('{file_path}')
            """)
        elif ext == ".parquet":
            conn.execute(f"""
                CREATE OR REPLACE TABLE {table_name} AS
                SELECT * FROM read_parquet('{file_path}')
            """)
        else:
            raise ValueError(f"Unsupported extension: {ext}")

        result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return result[0] if result else 0

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

    match = re.search(r"[-+]?\d*\.?\d+", cleaned)
    if not match:
        return None
    try:
        parsed = float(match.group(0)) * multiplier
    except ValueError:
        return None
    return -abs(parsed) if negative else parsed


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
    if (
        "date" in normalized_name
        or "time" in normalized_name
        or normalized_name.endswith("_at")
        or normalized_name in {"month", "period", "timestamp", "datetime"}
    ):
        return True

    sample = [str(value).strip() for value in series.drop_nulls().head(20).to_list()]
    if not sample:
        return False
    date_like = sum(_looks_like_date_value(value) for value in sample)
    return date_like / len(sample) >= 0.7


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
