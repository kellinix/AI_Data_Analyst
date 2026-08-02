#!/usr/bin/env python
"""
Standalone Data Quality Report CLI.

Runs the reusable validation framework in
`app/analytics/data_quality_checks.py` against any CSV file and writes a
Markdown (and optionally JSON) report. Deliberately dependency-free (stdlib
csv/json/argparse only) so it runs with a bare `python`, no virtualenv setup
required -- point it at a file and read the result.

Usage:
    python backend/scripts/data_quality_report.py path/to/file.csv
    python backend/scripts/data_quality_report.py path/to/file.csv \
        --id-column order_id \
        --date-column week_start_date \
        --outlier-column revenue --outlier-column units_sold \
        --required-column region --required-column category \
        --output report.md --json-output report.json

Run against this repo's own demo dataset:
    python backend/scripts/data_quality_report.py \
        backend/scripts/demo_data/northwind_outfitters_sales.csv \
        --date-column week_start_date \
        --outlier-column revenue --outlier-column marketing_spend \
        --required-column region --required-column category
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics.data_quality_checks import (  # noqa: E402
    QualitySuiteConfig,
    render_markdown_report,
    run_quality_suite,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _result_to_dict(result) -> dict:
    return {
        "check": result.check,
        "column": result.column,
        "passed": result.passed,
        "severity": result.severity.value,
        "message": result.message,
        "affected_count": result.affected_count,
        "total_count": result.total_count,
        "affected_ratio": round(result.affected_ratio, 4),
        "details": result.details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Data Quality Report for a CSV file.")
    parser.add_argument("csv_path", type=Path, help="Path to the CSV file to validate")
    parser.add_argument("--id-column", action="append", default=[], dest="id_columns",
                         help="Column to validate as an identifier (repeatable)")
    parser.add_argument("--date-column", action="append", default=[], dest="date_columns",
                         help="Column to validate as a date (repeatable)")
    parser.add_argument("--outlier-column", action="append", default=[], dest="outlier_columns",
                         help="Numeric column to scan for statistical outliers (repeatable)")
    parser.add_argument("--required-column", action="append", default=[], dest="required_columns",
                         help="Column that must never be null (repeatable)")
    parser.add_argument("--duplicate-key", action="append", default=[], dest="duplicate_keys",
                         help="Column that forms part of the duplicate-record key (repeatable; "
                              "omit to check whole-row duplicates instead)")
    parser.add_argument("--dataset-name", default=None, help="Label for the report (defaults to the filename)")
    parser.add_argument("--output", type=Path, default=None, help="Markdown output path (defaults to stdout)")
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args()

    if not args.csv_path.exists():
        parser.error(f"File not found: {args.csv_path}")

    rows = _read_csv(args.csv_path)
    config = QualitySuiteConfig(
        id_columns=args.id_columns,
        date_columns=args.date_columns,
        outlier_columns=args.outlier_columns,
        required_columns=args.required_columns,
        duplicate_key_columns=args.duplicate_keys or None,
    )
    report = run_quality_suite(rows, config, dataset_name=args.dataset_name or args.csv_path.name)

    markdown = render_markdown_report(report)
    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Wrote Markdown report to {args.output}", file=sys.stderr)
    else:
        print(markdown)

    if args.json_output:
        payload = {
            "dataset_name": report.dataset_name,
            "row_count": report.row_count,
            "column_count": report.column_count,
            "score": report.score,
            "generated_at": report.generated_at,
            "results": [_result_to_dict(r) for r in report.results],
        }
        args.json_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON report to {args.json_output}", file=sys.stderr)

    return 0 if report.score >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
