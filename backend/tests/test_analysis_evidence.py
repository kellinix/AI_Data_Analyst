from __future__ import annotations

import duckdb
import polars as pl

from app.analytics.analysis_evidence import (
    analysis_evidence,
    recommendation_catalogue,
    select_recommendations,
)
from app.analytics.recommendations import generate_recommendations
from app.analytics.statistics import StatisticsEngine
from app.services.ai_service import _fallback_summary
from app.services.file_processor import FileProcessor


def test_repeated_customer_ids_do_not_become_customer_count():
    with duckdb.connect() as conn:
        conn.execute(
            "CREATE TABLE data AS SELECT * FROM (VALUES (1, 'A', 10), (1, 'A', 20), (2, 'B', 30)) t(customer_id, customer_name, revenue)"
        )
        stats = StatisticsEngine(conn).describe_all()
    assert stats["row_count"] == 3
    measure = next(c for c in stats["entity_counts"] if c["column"] == "customer_id")
    assert measure["distinct_values"] == 2
    assert measure["repeated_records"] == 1
    assert "not verified" in measure["count_basis"]


def test_placeholder_names_are_not_counted_as_entities():
    with duckdb.connect() as conn:
        conn.execute(
            "CREATE TABLE data AS SELECT * FROM (VALUES ('A'), ('A'), ('Unknown'), (''), (NULL)) t(organisation_name)"
        )
        stats = StatisticsEngine(conn).describe_all()
    assert stats["entity_counts"][0]["distinct_values"] == 1
    assert stats["entity_counts"][0]["populated_records"] == 2


def test_all_row_removal_reasons_reconcile():
    report = {
        "input_rows": 100,
        "output_rows": 80,
        "dropped_empty_rows": 2,
        "removed_duplicate_rows": 5,
        "removed_fuzzy_duplicate_rows": 3,
        "dropped_rows_missing_critical_metrics": 4,
        "excluded_outlier_rows": 6,
    }
    evidence = analysis_evidence({"schema": []}, {"cleaning": {"enabled": True, "report": report}})
    assert evidence["cleaning"]["reconciled"]
    assert sum(c["rows"] for c in evidence["cleaning"]["row_changes"]) == 20


def test_unexplained_row_changes_are_reported():
    evidence = analysis_evidence(
        {}, {"cleaning": {"enabled": True, "report": {"input_rows": 10, "output_rows": 8}}}
    )
    assert not evidence["cleaning"]["reconciled"]
    assert evidence["cleaning"]["unexplained_row_change"] == 2
    assert any("does not explain" in n for n in evidence["limitations"])


def test_unchanged_cleaning_does_not_claim_a_change_and_excluded_sheets_are_plain():
    stats = {
        "schema": [
            {"name": "shipment_id"}, {"name": "shipdate"},
            {"name": "amount"}, {"name": "boxes"},
        ],
        "parser": {"excluded_sheets": [{"name": "Calendar", "reason": "No shared table fields"}]},
    }
    evidence = analysis_evidence(stats, {"cleaning": {"enabled": True, "report": {
        "input_rows": 20, "output_rows": 20,
    }}})
    assert any("shipment records" in note for note in evidence["limitations"])
    assert any("Worksheet Calendar was kept separate" in note for note in evidence["limitations"])
    assert not any("Cleaning changed" in note for note in evidence["limitations"])


def test_old_file_explains_why_a_current_forecast_is_not_offered():
    evidence = analysis_evidence(
        {"schema": [], "date_range": {"shipdate": {"min": "2023-01-01", "max": "2023-12-31"}}},
        {},
    )
    assert any("too old for a current" in note for note in evidence["limitations"])


def test_cleaning_preserves_source_gaps_even_after_unknown_labels():
    df = pl.DataFrame({"customer_name": ["A", "B", "C", "D"], "region": ["North", None, " ", None]})
    cleaned, report = FileProcessor().clean_dataframe(
        df, {"missing_data_strategy": "smart"}
    )
    assert cleaned["region"].null_count() == 0
    issue = next(i for i in report["source_quality"]["issues"] if i["column"] == "region")
    assert issue["affected_rows"] == 3
    assert report["source_quality"]["score"] < 100
    evidence = analysis_evidence({}, {"cleaning": {"enabled": True, "report": report}})
    assert any("not observed values" in n for n in evidence["limitations"])


def test_model_cannot_attach_a_real_number_to_the_wrong_field_or_action():
    measured = {"title": "Review source coverage", "evidence": "Region has 40 missing values"}
    catalogue = recommendation_catalogue([measured])
    selected, checks = select_recommendations(
        ["action_0", "invented"], catalogue,
        [{"title": "Increase profit", "evidence": "Profit totals 40", "financial_opportunity": 40}],
    )
    assert selected == [measured]
    assert checks["rejected_ids"] == ["invented"]
    assert checks["rejected_free_form_count"] == 1
    assert checks["free_form_used"] is False


def test_ranking_deduplicates_known_ids_and_preserves_other_measured_actions():
    catalogue = recommendation_catalogue([{"title": "Coverage"}, {"title": "Distinct counts"}])
    selected, checks = select_recommendations(["action_1", "action_1", {}], catalogue)
    assert [rec["title"] for rec in selected] == ["Distinct counts", "Coverage"]
    assert checks["rejected_ids"] == [{}]
    assert select_recommendations(None, catalogue)[0] == [item["recommendation"] for item in catalogue]


def test_source_gaps_and_repeated_entities_have_specific_actions_and_fallback():
    stats = {
        "row_count": 10,
        "column_count": 2,
        "entity_counts": [
            {
                "column": "customer_name",
                "distinct_values": 5,
                "populated_records": 10,
                "repeated_records": 5,
            }
        ],
        "data_quality": {
            "score": 100,
            "issues": [],
            "source_quality": {
                "issues": [
                    {
                        "column": "region",
                        "affected_rows": 6,
                        "description": "6 source values are missing",
                    }
                ]
            },
        },
    }
    recs = generate_recommendations(
        kpis=[], data_quality=stats["data_quality"], anomalies=[], forecasts=[], statistics=stats
    )
    assert len(recs) == 2
    assert all(r["evidence"] for r in recs)
    summary = _fallback_summary(stats, [])
    assert "6 source values are missing" in summary
    assert "5 distinct recorded values" in summary


def test_forecast_action_cannot_override_an_interval_including_the_latest_value():
    recommendations = generate_recommendations(
        kpis=[], data_quality={}, anomalies=[], forecasts=[{
            "metric": "revenue", "latest_value": 100, "change_percent_next_month": 50,
            "change_direction_supported": True,
            "predictions": {"next_month": {"value": 150, "lower": 80, "upper": 200}},
        }],
    )
    assert recommendations == []


def test_serial_number_repetition_does_not_create_an_entity_coverage_action():
    recommendations = generate_recommendations(
        kpis=[], data_quality={}, anomalies=[], forecasts=[], statistics={"entity_counts": [{
            "column": "Sr #", "populated_records": 100, "distinct_values": 50, "repeated_records": 50,
        }]},
    )
    assert recommendations == []
