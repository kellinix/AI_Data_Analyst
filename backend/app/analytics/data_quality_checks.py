"""
Reusable data quality validation framework.

This module is deliberately independent of `data_quality.py`, the DuckDB-
backed detector wired into the live analysis pipeline
(`StatisticsEngine.describe_all` -> `analyze_data_quality`). That module is
tuned to one specific contract: it is called with an open DuckDB connection
over a table literally named "data", and its output shape (`score`, `issues`,
`fixes`) is load-bearing for the frontend's data-quality panel and three
pinned regression tests. It must not change.

This module is the general-purpose toolkit: a set of small, composable
checks that operate on plain `list[dict]` rows -- the lowest common
denominator every tabular source can produce (`csv.DictReader`,
`duckdb_relation.fetchall()` zipped with column names, `df.to_dict("records")`,
a REST API response, ...). Stdlib-only on purpose, so it runs anywhere
without pulling in the backend's full dependency stack: in a notebook, a CI
step, or the standalone CLI report at `backend/scripts/data_quality_report.py`.

Each check returns one or more `CheckResult` objects with a consistent shape
(severity, affected count, human-readable message, and a `details` dict for
anything check-specific). `run_quality_suite` runs a configurable subset of
checks and rolls them into a `QualityReport` with a single 0-100 score, using
a severity-weighted penalty formula analogous in spirit to (but not shared
code with) `data_quality.py`'s scorer -- see `score_report` for the exact
formula and why it's intentionally a separate implementation.
"""

from __future__ import annotations

import re
import statistics as _statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

Row = dict[str, Any]

# Values that mean "no data" even though the cell isn't a true null -- the
# same class of sentinel tokens real-world exports use in place of blank.
_BLANK_TOKENS = {"", "n/a", "na", "null", "none", "nan", "unknown", "-", "--"}

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
)


class Severity(str, Enum):
    """Ordered from least to most severe; used both for display and for the
    scoring penalty weights in `score_report`."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of a single validation check.

    `passed` is true when the check found nothing to flag. Even a passing
    check is kept in the report (not just failures) so a Data Quality
    Report can show a clean checklist, not only a list of problems.
    """

    check: str
    column: str | None
    passed: bool
    severity: Severity
    message: str
    affected_count: int = 0
    total_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def affected_ratio(self) -> float:
        return (self.affected_count / self.total_count) if self.total_count else 0.0


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _BLANK_TOKENS
    return False


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned or cleaned.lower() in _BLANK_TOKENS:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or _is_blank(value):
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # ISO 8601 with an offset/'Z' suffix pandas/duckdb commonly emit.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_missing_values(
    rows: Sequence[Row],
    columns: Sequence[str] | None = None,
    *,
    high_ratio: float = 0.2,
    critical_ratio: float = 0.5,
) -> list[CheckResult]:
    """Missing-value rate per column.

    A cell counts as missing if it's `None`/absent or a common blank
    sentinel ("", "N/A", "unknown", ...) -- matching how real exports encode
    missingness, not just Python `None`.
    """
    total = len(rows)
    target_columns = list(columns) if columns is not None else _all_columns(rows)
    results: list[CheckResult] = []
    for column in target_columns:
        missing = sum(1 for row in rows if _is_blank(row.get(column)))
        ratio = missing / total if total else 0.0
        severity = (
            Severity.CRITICAL if ratio >= critical_ratio
            else Severity.HIGH if ratio >= high_ratio
            else Severity.LOW
        )
        results.append(CheckResult(
            check="missing_values",
            column=column,
            passed=missing == 0,
            severity=severity,
            message=f"{missing:,} of {total:,} values missing ({ratio:.1%})" if missing else "No missing values",
            affected_count=missing,
            total_count=total,
        ))
    return results


def check_duplicate_records(
    rows: Sequence[Row],
    key_columns: Sequence[str] | None = None,
) -> CheckResult:
    """Exact duplicate rows, or duplicate keys if `key_columns` is given.

    Without `key_columns`, two rows are duplicates if every field matches.
    With `key_columns`, this checks *key* duplication specifically (e.g. an
    `order_id` that appears twice, regardless of whether the other columns
    also match) -- the more common real-world case, since a truly identical
    full-row duplicate is rarer than a repeated identifier with drifted
    detail columns.
    """
    total = len(rows)
    seen: dict[tuple, int] = {}
    for row in rows:
        key = tuple(row.get(col) for col in key_columns) if key_columns else tuple(sorted(row.items()))
        seen[key] = seen.get(key, 0) + 1
    duplicate_count = sum(count - 1 for count in seen.values() if count > 1)
    ratio = duplicate_count / total if total else 0.0
    label = f"keys ({', '.join(key_columns)})" if key_columns else "full rows"
    return CheckResult(
        check="duplicate_records",
        column=", ".join(key_columns) if key_columns else None,
        passed=duplicate_count == 0,
        severity=_ratio_severity(ratio),
        message=(
            f"{duplicate_count:,} duplicate {label} ({ratio:.1%} of rows)"
            if duplicate_count else f"No duplicate {label}"
        ),
        affected_count=duplicate_count,
        total_count=total,
    )


def check_invalid_ids(
    rows: Sequence[Row],
    id_column: str,
    *,
    pattern: str | None = None,
    require_unique: bool = True,
) -> CheckResult:
    """Validate an identifier column: not blank, optionally matches
    `pattern` (a regex, e.g. `r"^ORD-\\d{6}$"`), and optionally unique.

    Reports the *union* of malformed and (if `require_unique`) duplicate
    IDs as one combined `affected_count`, with a breakdown in `details` --
    an ID can fail for more than one reason and each is worth knowing about
    even though the check reports a single pass/fail.
    """
    total = len(rows)
    compiled = re.compile(pattern) if pattern else None
    blank = 0
    malformed = 0
    seen: dict[Any, int] = {}
    bad_row_indexes: set[int] = set()

    for index, row in enumerate(rows):
        value = row.get(id_column)
        if _is_blank(value):
            blank += 1
            bad_row_indexes.add(index)
            continue
        text = str(value)
        if compiled and not compiled.match(text):
            malformed += 1
            bad_row_indexes.add(index)
        seen[text] = seen.get(text, 0) + 1

    duplicate_ids = sum(1 for count in seen.values() if count > 1) if require_unique else 0
    if require_unique:
        for index, row in enumerate(rows):
            value = row.get(id_column)
            if not _is_blank(value) and seen.get(str(value), 0) > 1:
                bad_row_indexes.add(index)

    affected = len(bad_row_indexes)
    ratio = affected / total if total else 0.0
    parts = []
    if blank:
        parts.append(f"{blank:,} blank")
    if malformed:
        parts.append(f"{malformed:,} malformed")
    if duplicate_ids:
        parts.append(f"{duplicate_ids:,} duplicate values")
    message = f"{id_column}: " + ", ".join(parts) if parts else f"{id_column}: all IDs present, well-formed and unique"

    return CheckResult(
        check="invalid_ids",
        column=id_column,
        passed=affected == 0,
        severity=_ratio_severity(ratio) if affected else Severity.LOW,
        message=message,
        affected_count=affected,
        total_count=total,
        details={"blank": blank, "malformed": malformed, "duplicate_values": duplicate_ids},
    )


def check_outliers(
    rows: Sequence[Row],
    column: str,
    *,
    method: str = "iqr",
    iqr_multiplier: float = 1.5,
    z_threshold: float = 3.0,
) -> CheckResult:
    """Statistical outliers in a numeric column.

    `method="iqr"` (default) flags values outside `Q1 - k*IQR` / `Q3 + k*IQR`
    -- robust to skew, the standard choice for business metrics that are
    rarely symmetric (revenue, order counts). `method="zscore"` flags values
    more than `z_threshold` standard deviations from the mean -- more
    sensitive, but distorted by the very outliers it's looking for on a
    skewed distribution, so prefer IQR unless the column is roughly normal.
    """
    values = [v for v in (_to_float(row.get(column)) for row in rows) if v is not None]
    total = len(rows)
    if len(values) < 4:
        return CheckResult(
            check="outliers", column=column, passed=True, severity=Severity.LOW,
            message="Not enough numeric values to assess outliers",
            affected_count=0, total_count=total,
        )

    if method == "zscore":
        mean = _statistics.fmean(values)
        stdev = _statistics.pstdev(values)
        if stdev == 0:
            affected = 0
            bounds = {"mean": mean, "stdev": stdev}
        else:
            affected = sum(1 for v in values if abs((v - mean) / stdev) >= z_threshold)
            bounds = {"mean": mean, "stdev": stdev, "z_threshold": z_threshold}
    else:
        quantiles = _statistics.quantiles(values, n=4, method="inclusive")
        q1, q3 = quantiles[0], quantiles[2]
        iqr = q3 - q1
        lower, upper = q1 - iqr_multiplier * iqr, q3 + iqr_multiplier * iqr
        affected = sum(1 for v in values if v < lower or v > upper)
        bounds = {"lower": lower, "upper": upper, "q1": q1, "q3": q3}

    return CheckResult(
        check="outliers",
        column=column,
        passed=affected == 0,
        severity=Severity.MEDIUM if affected else Severity.LOW,
        message=f"{affected:,} outlier value(s) in {column} ({method})" if affected else f"No outliers in {column}",
        affected_count=affected,
        total_count=total,
        details=bounds,
    )


def check_schema(
    rows: Sequence[Row],
    expected_columns: dict[str, str],
) -> CheckResult:
    """Validate the row shape against an expected schema.

    `expected_columns` maps column name -> one of `"numeric"`, `"text"`,
    `"date"`, `"boolean"`. A column's actual type is inferred from its
    non-blank values (>=90% must parse as the expected type to pass) -- real
    files routinely have a handful of dirty cells in an otherwise clean
    numeric column, and a schema check that fails on one bad row is too
    brittle to be useful.
    """
    actual_columns = _all_columns(rows)
    missing = [c for c in expected_columns if c not in actual_columns]
    extra = [c for c in actual_columns if c not in expected_columns]
    type_mismatches: list[dict[str, Any]] = []

    for column, expected_type in expected_columns.items():
        if column in missing:
            continue
        values = [row.get(column) for row in rows if not _is_blank(row.get(column))]
        if not values:
            continue
        match_count = sum(1 for v in values if _matches_type(v, expected_type))
        match_ratio = match_count / len(values)
        if match_ratio < 0.9:
            type_mismatches.append({
                "column": column, "expected": expected_type,
                "match_ratio": round(match_ratio, 3),
            })

    affected = len(missing) + len(type_mismatches)
    passed = not missing and not type_mismatches
    message_parts = []
    if missing:
        message_parts.append(f"missing columns: {', '.join(missing)}")
    if type_mismatches:
        message_parts.append(f"type mismatches: {', '.join(m['column'] for m in type_mismatches)}")
    if extra:
        message_parts.append(f"{len(extra)} unexpected column(s) present (not an error)")
    message = "; ".join(message_parts) if message_parts else "Schema matches expectations"

    return CheckResult(
        check="schema_validation",
        column=None,
        passed=passed,
        severity=Severity.CRITICAL if missing else (Severity.HIGH if type_mismatches else Severity.LOW),
        message=message,
        affected_count=affected,
        total_count=len(expected_columns),
        details={"missing_columns": missing, "extra_columns": extra, "type_mismatches": type_mismatches},
    )


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "numeric":
        return _to_float(value) is not None
    if expected_type == "date":
        return _parse_date(value) is not None
    if expected_type == "boolean":
        return str(value).strip().lower() in {"true", "false", "0", "1", "yes", "no"}
    return True  # "text" accepts anything present


def check_referential_integrity(
    child_rows: Sequence[Row],
    child_key: str,
    parent_rows: Sequence[Row],
    parent_key: str,
) -> CheckResult:
    """Foreign-key-style check: every non-blank `child_key` value in
    `child_rows` should exist among `parent_key` values in `parent_rows`.

    Mirrors what a `FOREIGN KEY` constraint enforces in a relational
    database -- useful here precisely because flat file uploads have none.
    Blank child keys are excluded from the orphan count and reported
    separately in `details`, since a missing key is a `check_unexpected_nulls`
    concern, not an orphan-reference concern.
    """
    parent_values = {row.get(parent_key) for row in parent_rows if not _is_blank(row.get(parent_key))}
    total = len(child_rows)
    orphans = 0
    blank_keys = 0
    for row in child_rows:
        value = row.get(child_key)
        if _is_blank(value):
            blank_keys += 1
            continue
        if value not in parent_values:
            orphans += 1

    ratio = orphans / total if total else 0.0
    return CheckResult(
        check="referential_integrity",
        column=child_key,
        passed=orphans == 0,
        severity=_ratio_severity(ratio) if orphans else Severity.LOW,
        message=(
            f"{orphans:,} {child_key} value(s) have no matching {parent_key} in the parent dataset"
            if orphans else f"Every non-blank {child_key} matches a {parent_key} in the parent dataset"
        ),
        affected_count=orphans,
        total_count=total,
        details={"blank_child_keys": blank_keys},
    )


def check_unexpected_nulls(
    rows: Sequence[Row],
    required_columns: Sequence[str],
) -> list[CheckResult]:
    """Nulls in columns that the caller has declared *must* be populated
    (e.g. a primary business key or a required field) -- distinct from
    `check_missing_values`, which reports the missing-rate of every column
    as informational; this treats a null in these specific columns as an
    always-actionable defect regardless of how rare it is.
    """
    total = len(rows)
    results = []
    for column in required_columns:
        missing = sum(1 for row in rows if _is_blank(row.get(column)))
        results.append(CheckResult(
            check="unexpected_nulls",
            column=column,
            passed=missing == 0,
            severity=Severity.CRITICAL if missing else Severity.LOW,
            message=(
                f"{missing:,} unexpected null(s) in required column {column}"
                if missing else f"{column}: no unexpected nulls"
            ),
            affected_count=missing,
            total_count=total,
        ))
    return results


def check_date_validity(
    rows: Sequence[Row],
    column: str,
    *,
    min_date: date | None = None,
    max_date: date | None = None,
    allow_future: bool = True,
    reference_date: date | None = None,
) -> CheckResult:
    """Validate a date column: parseable, within `[min_date, max_date]` if
    given, and not in the future unless `allow_future` is true (most
    business event dates -- order date, signup date -- shouldn't be; a
    target/renewal date legitimately can be, so this defaults to allowing
    it and the caller opts into the stricter check).
    """
    total = len(rows)
    reference = reference_date or datetime.now(UTC).date()
    unparseable = 0
    out_of_range = 0
    future = 0

    for row in rows:
        raw = row.get(column)
        if _is_blank(raw):
            continue
        parsed = _parse_date(raw)
        if parsed is None:
            unparseable += 1
            continue
        if (min_date and parsed < min_date) or (max_date and parsed > max_date):
            out_of_range += 1
        if not allow_future and parsed > reference:
            future += 1

    affected = unparseable + out_of_range + future
    ratio = affected / total if total else 0.0
    parts = []
    if unparseable:
        parts.append(f"{unparseable:,} unparseable")
    if out_of_range:
        parts.append(f"{out_of_range:,} out of range")
    if future:
        parts.append(f"{future:,} in the future")
    message = f"{column}: " + ", ".join(parts) if parts else f"{column}: all dates valid"

    return CheckResult(
        check="date_validity",
        column=column,
        passed=affected == 0,
        severity=_ratio_severity(ratio) if affected else Severity.LOW,
        message=message,
        affected_count=affected,
        total_count=total,
        details={"unparseable": unparseable, "out_of_range": out_of_range, "future": future},
    )


def _ratio_severity(ratio: float) -> Severity:
    if ratio >= 0.5:
        return Severity.CRITICAL
    if ratio >= 0.2:
        return Severity.HIGH
    if ratio >= 0.05:
        return Severity.MEDIUM
    return Severity.LOW


def _all_columns(rows: Sequence[Row]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    return columns


# ---------------------------------------------------------------------------
# Suite orchestration + reporting
# ---------------------------------------------------------------------------


@dataclass
class QualitySuiteConfig:
    """What to check. Every field is optional -- omit a column list and that
    category of check is simply skipped, so the same suite works whether
    you know a lot about the dataset's expected shape or nothing at all."""

    id_columns: Sequence[str] = ()
    id_patterns: dict[str, str] = field(default_factory=dict)
    date_columns: Sequence[str] = ()
    required_columns: Sequence[str] = ()
    outlier_columns: Sequence[str] = ()
    expected_schema: dict[str, str] | None = None
    duplicate_key_columns: Sequence[str] | None = None
    referential_checks: Sequence[tuple[str, Sequence[Row], str]] = ()
    """Each item: (child_key_column, parent_rows, parent_key_column)."""


@dataclass
class QualityReport:
    dataset_name: str
    row_count: int
    column_count: int
    score: int
    generated_at: str
    results: list[CheckResult]

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    @property
    def passed_checks(self) -> list[CheckResult]:
        return [r for r in self.results if r.passed]


def run_quality_suite(
    rows: Sequence[Row],
    config: QualitySuiteConfig | None = None,
    *,
    dataset_name: str = "dataset",
) -> QualityReport:
    """Run every check the config asks for and roll the results into one
    `QualityReport`. Always runs `check_missing_values` and
    `check_duplicate_records` over the full row set -- every other check
    only runs if the caller supplied the columns it needs, since (for
    example) there's no generic way to guess which column is an ID."""
    config = config or QualitySuiteConfig()
    columns = _all_columns(rows)
    results: list[CheckResult] = []

    results.extend(check_missing_values(rows, columns))
    results.append(check_duplicate_records(rows, config.duplicate_key_columns))

    for id_column in config.id_columns:
        results.append(check_invalid_ids(rows, id_column, pattern=config.id_patterns.get(id_column)))

    for column in config.outlier_columns:
        results.append(check_outliers(rows, column))

    if config.expected_schema:
        results.append(check_schema(rows, config.expected_schema))

    if config.required_columns:
        results.extend(check_unexpected_nulls(rows, config.required_columns))

    for column in config.date_columns:
        results.append(check_date_validity(rows, column))

    for child_key, parent_rows, parent_key in config.referential_checks:
        results.append(check_referential_integrity(rows, child_key, parent_rows, parent_key))

    return QualityReport(
        dataset_name=dataset_name,
        row_count=len(rows),
        column_count=len(columns),
        score=score_report(results),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        results=results,
    )


def score_report(results: Sequence[CheckResult]) -> int:
    """Severity-weighted 0-100 score.

    Same *shape* of formula as `data_quality.py`'s internal scorer
    (severity-weighted penalty, floored per-issue impact, doubled weight
    past 50% of rows affected) but intentionally a separate implementation:
    this module has no dependency on, and makes no claim of matching,
    Zephyr's internal pipeline score -- it's meant to be dropped into any
    project. If you want the two to agree exactly, that's a deliberate
    follow-up integration decision, not an accident of shared code.
    """
    severity_weight = {Severity.LOW: 1.5, Severity.MEDIUM: 4.0, Severity.HIGH: 8.0, Severity.CRITICAL: 14.0}
    penalty = 0.0
    for result in results:
        if result.passed:
            continue
        weight = severity_weight[result.severity]
        ratio = max(result.affected_ratio, 0.05)
        if result.affected_ratio > 0.5:
            weight *= 2
        penalty += weight * ratio
    return max(0, min(100, int(round(100 - penalty))))


def render_markdown_report(report: QualityReport) -> str:
    """Render a `QualityReport` as a standalone Markdown document."""
    lines = [
        f"# Data Quality Report — {report.dataset_name}",
        "",
        f"Generated: `{report.generated_at}`  ",
        f"Rows: **{report.row_count:,}** · Columns: **{report.column_count}** · "
        f"Checks run: **{len(report.results)}** · Checks failed: **{len(report.failed)}**",
        "",
        f"## Overall score: {report.score}/100",
        "",
        _score_band(report.score),
        "",
        "## Findings",
        "",
        "| Check | Column | Severity | Result |",
        "|---|---|---|---|",
    ]
    ordered = sorted(
        report.results,
        key=lambda r: (r.passed, -_severity_rank(r.severity)),
    )
    for result in ordered:
        status = "✅ Pass" if result.passed else f"❌ {result.severity.value.upper()}"
        column = result.column or "—"
        lines.append(f"| {result.check} | {column} | {status} | {result.message} |")

    if report.failed:
        lines += ["", "## Details on failed checks", ""]
        for result in report.failed:
            lines.append(f"### {result.check}" + (f" — `{result.column}`" if result.column else ""))
            lines.append(f"- Severity: **{result.severity.value}**")
            lines.append(f"- Affected: **{result.affected_count:,}** of {result.total_count:,} "
                          f"({result.affected_ratio:.1%})" if result.total_count else f"- Affected: **{result.affected_count:,}**")
            lines.append(f"- {result.message}")
            if result.details:
                detail_str = ", ".join(f"{k}={_format_detail_value(v)}" for k, v in result.details.items())
                lines.append(f"- Details: {detail_str}")
            lines.append("")

    return "\n".join(lines)


def _severity_rank(severity: Severity) -> int:
    return {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}[severity]


def _format_detail_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _score_band(score: int) -> str:
    if score >= 90:
        return "**Excellent** — ready for automated / unattended use."
    if score >= 75:
        return "**Good** — safe to use; review flagged issues opportunistically."
    if score >= 50:
        return "**Fair** — recommend resolving high/critical findings before relying on this dataset."
    return "**Poor** — do not use for decision-making until the findings below are addressed."
