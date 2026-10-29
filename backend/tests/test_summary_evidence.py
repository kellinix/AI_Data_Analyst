from __future__ import annotations

import json
from unittest.mock import AsyncMock

import polars as pl

from app.analytics.summary_evidence import build_summary_facts, render_summary
from app.services import analysis_engine
from app.services.ai_service import _coerce_analysis_json
from app.services.file_processor import FileProcessor
from app.services.report_language import present_metadata


def _sales():
    return {
        "row_count": 936, "column_count": 4,
        "schema": [{"name": "revenue", "analysis_role": "metric", "display_label": "Revenue"},
                   {"name": "region", "analysis_role": "dimension", "display_label": "Region"},
                   {"name": "sr", "analysis_role": "identifier"}],
        "numeric_stats": {"revenue": {"total": 12000, "mean": 12.820512820512821, "count": 936},
                          "sr": {"total": 438516, "mean": 468.5, "count": 936}},
        "categorical_stats": {"region": {"unique_count": 3, "top_values": [
            {"value": "North", "count": 400}, {"value": "South", "count": 300},
            {"value": "West", "count": 236}]}},
        "date_range": {"date": {"min": "2025-01-01", "max": "2025-12-31"}},
    }


def test_sales_total_uses_a_meaningful_name_without_repeating_total():
    stats = {
        "row_count": 2, "column_count": 3,
        "schema": [
            {"name": "date", "is_date": True, "analysis_role": "temporal_dimension"},
            {"name": "total", "is_numeric": True, "analysis_role": "metric"},
            {"name": "payment", "analysis_role": "dimension"},
        ],
        "numeric_stats": {"total": {"total": 50, "count": 2}},
        "categorical_stats": {}, "date_range": {"date": {"min": "2025-01-01", "max": "2025-01-02"}},
    }
    facts = build_summary_facts(stats, [{"column": "total", "is_total": True, "value": 50}])
    summary, checks = render_summary(facts, ["metric_0"])
    _, shown = present_metadata({**stats, "analysis_evidence": {"summary_checks": checks}}, summary)
    assert "Total sales amount is 50." in shown
    assert "Total total" not in shown


def test_sales_cash_type_summary_says_payment_method():
    stats = {
        "row_count": 10, "column_count": 3,
        "schema": [
            {"name": "date", "is_date": True, "analysis_role": "temporal_dimension"},
            {"name": "money", "is_numeric": True, "analysis_role": "metric"},
            {"name": "cash_type", "analysis_role": "dimension"},
        ],
        "numeric_stats": {"money": {"total": 100, "count": 10}},
        "categorical_stats": {"cash_type": {"top_values": [
            {"value": "card", "count": 9}, {"value": "cash", "count": 1}]}},
        "date_range": {"date": {"min": "2025-01-01", "max": "2025-01-10"}},
    }
    facts = build_summary_facts(stats, [{"column": "money", "is_total": True, "value": 100}])
    summary, checks = render_summary(facts, ["category_0"])
    _, shown = present_metadata({**stats, "analysis_evidence": {"summary_checks": checks}}, summary)
    assert "for payment method" in shown


def test_freeform_equal_representation_claim_is_never_used():
    stats = _sales()
    result = _coerce_analysis_json('{"executive_summary":"Regions are equally represented with 936 records.",'
                                   '"summary_fact_ids":["category_0","invented_fact"]}')
    facts = build_summary_facts(stats, [])
    summary, audit = render_summary(facts, result["summary_fact_ids"])
    assert "equally" not in summary
    assert "400 records labelled 'North' (42.7% of all 936 analysed records)" in summary
    assert not audit["free_form_used"]
    assert audit["rejected_fact_ids"] == ["invented_fact"]
    assert all(fact["source"] and fact["calculation"] for fact in audit["facts"])


def test_figures_must_match_their_own_field_and_aggregation():
    facts = build_summary_facts(_sales(), [
        {"column": "revenue", "value": 438516, "is_total": True},
        {"column": "sr", "value": 438516, "is_total": True},
        {"column": "revenue", "value": 12000, "is_total": True},
    ])
    metrics = [fact for fact in facts if fact["id"].startswith("metric_")]
    assert len(metrics) == 1
    assert metrics[0]["values"]["operation"] == "total"
    assert "12,000 across 936 supplied values" in metrics[0]["text"]


def test_weighted_average_keeps_weight_and_does_not_invent_eligible_count():
    stats = _sales()
    stats["schema"].append({"name": "variance_pct", "analysis_role": "metric"})
    stats["numeric_stats"]["variance_pct"] = {"mean": 80, "weighted_mean": 24, "count": 936}
    facts = build_summary_facts(stats, [{"column": "variance_pct", "value": 24,
                                       "is_total": False, "weighted_by": "revenue"}])
    metric = next(fact for fact in facts if fact["id"] == "metric_0")
    assert "24% when weighted by Revenue" in metric["text"]
    assert "936" not in metric["text"]
    assert "positive supplied weights" in metric["calculation"]


def test_sample_and_imputation_caveats_survive_model_selection():
    stats = _sales()
    stats["sample_truncated"] = True
    stats["analysis_evidence"] = {"cleaning": {"input_rows": 1000, "output_rows": 936,
                                               "removed_rows": 64, "reconciled": True}}
    context = {"cleaning": {"report": {"missing_values": {"numeric_imputations": [
        {"column": "revenue", "filled": 8, "method": "median"}]}}}}
    summary, audit = render_summary(build_summary_facts(stats, [], upload_context=context), ["category_0"])
    assert "rather than its full contents" in summary
    assert "1,000 input records to 936" in summary
    assert "8 missing cells" in summary
    assert all(fact["scope"] == "analysed sample" for fact in audit["facts"])


def test_serial_and_entirely_empty_fields_do_not_become_headline_quality_failures():
    stats = _sales()
    stats["data_quality"] = {"issues": [
        {"type": "missing_values", "column": "sr", "affected_rows": 500},
        {"type": "empty_field", "column": "unused", "affected_rows": 936},
        {"type": "missing_values", "column": "region", "affected_rows": 100},
    ]}
    facts = build_summary_facts(stats, [])
    missing = next(fact for fact in facts if fact["id"] == "missing")
    assert missing["values"]["column"] == "region"
    assert "100 missing values" in missing["text"]


def test_forecast_claim_checks_actual_interval_even_if_direction_flag_is_wrong():
    facts = build_summary_facts(_sales(), [], [{
        "metric": "revenue", "latest_value": 100, "change_direction_supported": True,
        "predictions": {"next_month": {"value": 110, "lower": 80, "upper": 140}},
        "method": "linear_regression_monthly", "observations": 12,
    }])
    summary, audit = render_summary(facts, ["forecast_0"])
    assert "direction of change is uncertain" in summary
    assert "80 to 140" in summary
    forecast = next(fact for fact in audit["facts"] if fact["id"] == "forecast_0")
    assert forecast["values"]["latest"] == 100


def test_zero_is_a_real_measure_and_nonfinite_values_are_omitted():
    stats = _sales()
    stats["numeric_stats"]["revenue"]["total"] = 0
    facts = build_summary_facts(stats, [{"column": "revenue", "is_total": True, "value": 0},
                                       {"column": "revenue", "is_total": True, "value": float("nan")}])
    metrics = [fact for fact in facts if fact["id"].startswith("metric_")]
    assert len(metrics) == 1
    assert "sums to 0" in metrics[0]["text"]


def test_only_known_unique_fact_ids_are_selected_and_missing_ids_fall_back():
    facts = build_summary_facts(_sales(), [])
    summary, audit = render_summary(facts, ["category_0", "category_0", {"id": "records"}, None])
    assert summary.count("records labelled") == 1
    assert len(audit["rejected_fact_ids"]) == 2
    assert audit["facts"][0]["id"] == "records"
    _, fallback = render_summary(facts, "category_0")
    assert fallback["selection"] == "deterministic"


def test_display_labels_cannot_change_measure_meaning_or_round_tiny_values_to_zero():
    stats = _sales()
    stats["schema"][0]["display_label"] = "Profit"
    stats["numeric_stats"]["revenue"]["total"] = .00012
    facts = build_summary_facts(stats, [{"column": "revenue", "value": .00012, "is_total": True}])
    metric = next(fact for fact in facts if fact["id"] == "metric_0")
    assert "Revenue sums to 0.00012" in metric["text"]
    assert "Profit" not in metric["text"]


async def test_pipeline_replaces_unsupported_model_prose_and_saves_the_evidence(tmp_path, monkeypatch):
    source = tmp_path / "sales.parquet"
    pl.DataFrame({"revenue": [10., 20., 30.], "region": ["North", "North", "South"]}).write_parquet(source)
    monkeypatch.setattr(analysis_engine.SemanticWrangler, "build_display_metadata", AsyncMock(return_value={}))
    ai = AsyncMock()
    ai.generate_analysis.return_value = {
        "executive_summary": "Regions are equal. Profit increased by 999%.",
        "summary_fact_ids": ["category_0"], "recommendation_ids": ["fake"],
        "recommendations": [{"title": "Profit is 999", "evidence": "Revenue is 60"}], "insights": [],
    }
    result = await analysis_engine.compute_analysis(
        file_processor=FileProcessor(), ai_service=ai, storage_path=str(source),
        file_name="sales.parquet", analysis_id="summary-regression",
    )
    summary = result["ai_result"]["executive_summary"]
    assert "999" not in summary and "equal" not in summary and "Profit" not in summary
    assert "66.7% of all 3 analysed records" in summary
    sent_profile = ai.generate_analysis.call_args.kwargs["statistics"]["profile_json"]
    assert sent_profile["analysis_evidence"]["summary_fact_catalogue"]
    saved = json.loads((tmp_path / "summary-regression.profile.json").read_text())
    assert saved["analysis_evidence"]["summary_checks"]["method"] == "measured_facts_v1"
    assert saved["analysis_evidence"]["recommendation_checks"]["rejected_free_form_count"] == 1
    assert all("999" not in rec["title"] for rec in result["recommendations"])
