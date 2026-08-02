"""
Tests for the standalone data quality validation framework
(`app/analytics/data_quality_checks.py`). This module is intentionally
independent of `app/analytics/data_quality.py` (the DuckDB-backed detector
wired into the live pipeline, covered by `test_data_quality.py`) -- these
tests exercise the general-purpose, dependency-free version instead.
"""

from __future__ import annotations

from datetime import date

from app.analytics.data_quality_checks import (
    QualitySuiteConfig,
    Severity,
    check_date_validity,
    check_duplicate_records,
    check_invalid_ids,
    check_missing_values,
    check_outliers,
    check_referential_integrity,
    check_schema,
    check_unexpected_nulls,
    render_markdown_report,
    run_quality_suite,
    score_report,
)


def test_missing_values_flags_blank_sentinels_not_just_none():
    rows = [{"a": "1"}, {"a": "N/A"}, {"a": ""}, {"a": None}, {"a": "5"}]
    results = check_missing_values(rows, ["a"])
    assert len(results) == 1
    assert results[0].affected_count == 3
    # 3/5 = 60% missing, above the default 50% critical threshold.
    assert results[0].severity == Severity.CRITICAL


def test_missing_values_all_present_passes():
    rows = [{"a": "1"}, {"a": "2"}]
    result = check_missing_values(rows, ["a"])[0]
    assert result.passed
    assert result.affected_count == 0


def test_duplicate_records_full_row():
    rows = [{"a": 1, "b": 2}, {"a": 1, "b": 2}, {"a": 3, "b": 4}]
    result = check_duplicate_records(rows)
    assert result.affected_count == 1
    assert not result.passed


def test_duplicate_records_by_key_ignores_other_columns():
    rows = [{"id": 1, "v": "x"}, {"id": 1, "v": "y"}, {"id": 2, "v": "z"}]
    result = check_duplicate_records(rows, key_columns=["id"])
    assert result.affected_count == 1


def test_invalid_ids_detects_blank_malformed_and_duplicate():
    rows = [
        {"order_id": "ORD-000001"},
        {"order_id": "ORD-000001"},  # duplicate
        {"order_id": "bad-id"},      # malformed
        {"order_id": ""},            # blank
        {"order_id": "ORD-000002"},
    ]
    result = check_invalid_ids(rows, "order_id", pattern=r"^ORD-\d{6}$")
    assert not result.passed
    assert result.details["blank"] == 1
    assert result.details["malformed"] == 1
    assert result.details["duplicate_values"] == 1


def test_invalid_ids_clean_column_passes():
    rows = [{"order_id": f"ORD-{i:06d}"} for i in range(5)]
    result = check_invalid_ids(rows, "order_id", pattern=r"^ORD-\d{6}$")
    assert result.passed
    assert result.affected_count == 0


def test_outliers_iqr_detects_extreme_low_value():
    normal = [{"revenue": 1000 + i} for i in range(20)]
    rows = normal + [{"revenue": 5}]
    result = check_outliers(rows, "revenue", method="iqr")
    assert not result.passed
    assert result.affected_count >= 1


def test_outliers_zscore_matches_iqr_direction_on_obvious_case():
    normal = [{"x": 50 + (i % 5)} for i in range(30)]
    rows = normal + [{"x": 10_000}]
    result = check_outliers(rows, "x", method="zscore", z_threshold=3.0)
    assert not result.passed


def test_outliers_insufficient_data_passes_without_error():
    result = check_outliers([{"x": 1}, {"x": 2}], "x")
    assert result.passed


def test_schema_validation_flags_missing_and_mismatched_columns():
    rows = [{"revenue": "100"}, {"revenue": "abc"}, {"revenue": "not-a-number"}]
    result = check_schema(rows, {"revenue": "numeric", "region": "text"})
    assert not result.passed
    assert "region" in result.details["missing_columns"]
    assert any(m["column"] == "revenue" for m in result.details["type_mismatches"])


def test_schema_validation_passes_clean_data():
    rows = [{"revenue": "100", "region": "APAC"}, {"revenue": "200", "region": "EU"}]
    result = check_schema(rows, {"revenue": "numeric", "region": "text"})
    assert result.passed


def test_referential_integrity_finds_orphans():
    parent = [{"category_id": "A"}, {"category_id": "B"}]
    child = [{"category_id": "A"}, {"category_id": "Z"}, {"category_id": None}]
    result = check_referential_integrity(child, "category_id", parent, "category_id")
    assert not result.passed
    assert result.affected_count == 1  # "Z" is the only orphan; null is excluded
    assert result.details["blank_child_keys"] == 1


def test_referential_integrity_all_matched_passes():
    parent = [{"id": 1}, {"id": 2}]
    child = [{"id": 1}, {"id": 2}, {"id": 1}]
    result = check_referential_integrity(child, "id", parent, "id")
    assert result.passed


def test_unexpected_nulls_flags_required_column():
    rows = [{"region": "EU"}, {"region": None}, {"region": "APAC"}]
    result = check_unexpected_nulls(rows, ["region"])[0]
    assert not result.passed
    assert result.affected_count == 1
    assert result.severity == Severity.CRITICAL


def test_date_validity_parses_multiple_formats():
    rows = [{"d": "2025-01-15"}, {"d": "15/01/2025"}, {"d": "not-a-date"}]
    result = check_date_validity(rows, "d")
    assert result.details["unparseable"] == 1


def test_date_validity_future_dates_flagged_when_disallowed():
    rows = [{"d": "2099-01-01"}, {"d": "2020-01-01"}]
    result = check_date_validity(rows, "d", allow_future=False, reference_date=date(2026, 1, 1))
    assert result.details["future"] == 1


def test_date_validity_out_of_range():
    rows = [{"d": "2010-01-01"}]
    result = check_date_validity(rows, "d", min_date=date(2020, 1, 1))
    assert result.details["out_of_range"] == 1


def test_run_quality_suite_produces_bounded_score_and_markdown():
    rows = [
        {"order_id": f"ORD-{i:06d}", "region": "EU", "revenue": str(100 + i), "order_date": "2025-01-01"}
        for i in range(20)
    ]
    config = QualitySuiteConfig(
        id_columns=["order_id"],
        date_columns=["order_date"],
        outlier_columns=["revenue"],
        required_columns=["region"],
    )
    report = run_quality_suite(rows, config, dataset_name="unit-test")
    assert 0 <= report.score <= 100
    assert report.row_count == 20
    markdown = render_markdown_report(report)
    assert "Data Quality Report" in markdown
    assert "unit-test" in markdown


def test_score_report_perfect_data_scores_high():
    rows = [{"a": str(i), "b": f"row-{i}"} for i in range(10)]
    report = run_quality_suite(rows, dataset_name="clean")
    assert report.score >= 95


def test_score_report_mostly_duplicated_dataset_scores_low():
    rows = [{"a": "1", "b": "x"}] * 9 + [{"a": "2", "b": "y"}]
    result = check_duplicate_records(rows)
    score = score_report([result])
    assert score <= 85
