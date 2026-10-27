from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.analysis import InsightResponse
from app.services.report_language import forecast_wording, present_insight, present_metadata


def test_forecast_explains_uncertainty_without_a_confidence_claim():
    data = {"metric": "revenue", "latest_value": 100, "confidence": .99,
            "change_direction_supported": True,
            "predictions": {"next_month": {"value": 120, "lower": 80, "upper": 160}}}
    title, text = forecast_wording(data)
    assert title == "What may happen next for revenue"
    assert "estimate is about 120" in text and "roughly 80 to 160" in text
    assert "too early to say whether it will rise or fall" in text
    assert "planning guide, not a promise" in text
    assert "99%" not in text and "regression" not in text and "observed" not in text


def test_forecast_keeps_zero_and_does_not_invent_missing_bounds():
    _, text = forecast_wording({"metric": "sales", "predictions": {"next_month": {"value": 0}}})
    assert "estimate is about 0" in text and "No usable range is available" in text
    assert forecast_wording({"metric": "sales", "predictions": {"next_month": {}}}) is None


def test_unusual_value_stays_attached_to_one_entry_not_its_group():
    result = present_insight({"type": "anomaly", "title": "Outlier", "description": "z=5",
        "data": {"column": "avg_order_value", "value": 89.45, "score": 5.68,
                 "context": {"region": "North America"}}})
    assert result["title"] == "Entries worth a closer look"
    assert "One entry lists average order value as 89.45" in result["description"]
    assert "region: North America" in result["description"]
    assert "does not automatically mean a mistake" in result["description"]
    assert result["data"]["score"] == 5.68


@pytest.mark.parametrize("source", ["rule:anomaly", "rule:data_quality", "rule:tracking", "rule:forecast"])
def test_actions_are_plain_and_keep_the_original_evidence(source):
    original = {"type": "recommendation", "title": "Review source coverage",
                "description": "Improved KPIs", "importance": "high", "confidence": .8,
                "data": {"evidence": "Region: 40 records have missing values",
                         "confidence_source": source, "financial_opportunity": None}}
    before = deepcopy(original)
    presented = present_insight(original)
    assert original == before
    assert "40 entries" in presented["data"]["evidence"]
    assert "source coverage" not in presented["title"]
    assert "KPIs" not in presented["description"]
    assert presented["confidence"] == .8
    assert presented["data"]["financial_opportunity"] is None
    assert present_insight(presented) == presented


def test_quality_checks_preserve_scores_and_counts_without_calling_unusual_values_errors():
    metadata = {"data_quality": {"score": 99, "scoring_method": "internal penalty formula",
        "issues": [{"type": "outliers", "affected_rows": 18, "column": "units_sold", "severity": "medium"},
                   {"type": "missing_values", "affected_rows": 40, "column": "region", "severity": "high"}],
        "source_quality": {"score": 100, "issues": []}}}
    before = deepcopy(metadata)
    presented, _ = present_metadata(metadata, None)
    quality = presented["data_quality"]
    assert metadata == before and quality["score"] == 99
    assert "18 entries were flagged for review of units sold" in quality["issues"][0]["description"]
    assert "comparison limits were not saved" in quality["issues"][0]["description"]
    assert "differences are expected" in quality["issues"][0]["description"]
    assert "40 entries" in quality["issues"][1]["description"]
    assert "confirm that every entry is correct" in quality["scope"]
    assert quality["scoring_method"] == "internal penalty formula"
    assert present_metadata(presented, None)[0] == presented


def test_old_audited_summary_gets_plain_wording_and_matching_disclosures():
    summary = "Revenue sums to 60 across 3 supplied values."
    metadata = {"analysis_evidence": {"summary_checks": {
        "method": "measured_facts_v1", "facts": [{"id": "metric_0", "text": summary,
        "calculation": "SUM(revenue)", "scope": "analysed file", "values": {
            "column": "revenue", "value": 60, "operation": "total"}}]}}}
    presented, text = present_metadata(metadata, summary)
    fact = presented["analysis_evidence"]["summary_checks"]["facts"][0]
    assert text == "Total revenue is 60." and fact["text"] == text
    assert fact["calculation"] == "SUM(revenue)"
    assert metadata["analysis_evidence"]["summary_checks"]["facts"][0]["text"] == summary


def test_unknown_or_mismatched_summary_is_not_rewritten_as_a_verified_answer():
    original = "Unsupported narrative"
    presented, summary = present_metadata({"analysis_evidence": {"summary_checks": {
        "method": "measured_facts_v1", "facts": ["bad legacy value"]}}}, original)
    assert summary == original


def test_response_keeps_feedback_identity_and_measurements_for_old_reports():
    original = SimpleNamespace(id=uuid4(), analysis_id=uuid4(), type="forecast", title="Revenue forecast",
        description="Linear regression", importance="medium", confidence=.83,
        data={"metric": "revenue", "predictions": {"next_month": {"value": 120}}},
        chart_config=None, created_at=datetime.now(UTC), user_feedback="helpful")
    response = InsightResponse.model_validate(original)
    assert response.title == "What may happen next for revenue"
    assert response.user_feedback == "helpful" and response.id == original.id
    assert response.data["predictions"] == original.data["predictions"]
    assert original.description == "Linear regression"


def test_readable_dates_and_average_labels_do_not_change_the_underlying_values():
    data = {"column": "avg_order_value", "value": 89.45,
            "context": {"week_start_date": "2025-11-17"}}
    presented = present_insight({"type": "anomaly", "title": "Unusual", "description": "", "data": data})
    assert "week beginning: 17 Nov 2025" in presented["description"]
    assert presented["data"]["context"] == data["context"]
    metric = present_insight({"type": "summary", "title": "Avg Avg Order Value", "description": "",
                             "data": {"column": "avg_order_value", "value": 50.1, "is_total": False}})
    assert metric["title"] == "Average Order Value"
    assert metric["description"] == "Average across the entries in this file."
    assert metric["data"]["value"] == 50.1


@pytest.mark.parametrize(("kind", "extra", "expected"), [
    ("outliers", {"below_range_rows": 12, "above_range_rows": 1},
     "12 entries have revenue below about 5,415.3; 1 entry has revenue above about 20,504.43."),
    ("wide_spread", {}, "13 entries have revenue above about 20,504.43."),
    ("outliers", {}, "13 entries have revenue below about 5,415.3 or above about 20,504.43."),
])
def test_unusual_amounts_name_the_measure_limits_and_only_known_direction(kind, extra, expected):
    issue = {"type": kind, "column": "revenue", "affected_rows": 13,
             "bounds": {"lower": 5415.30, "upper": 20504.43}, **extra}
    metadata, _ = present_metadata({"data_quality": {"issues": [issue]}}, None)
    text = metadata["data_quality"]["issues"][0]["description"]
    assert text.startswith(expected)
    assert "13 numbers" not in text and "much higher or lower" not in text
    assert "before correcting anything" in text
    assert "not business targets" in metadata["data_quality"]["scope"]


def test_forecast_gives_a_baseline_range_and_practical_caution_for_short_history():
    title, text = forecast_wording({"metric": "weekly_sales", "latest_value": 100, "observations": 3,
        "predictions": {"next_month": {"value": 120, "lower": 20, "upper": 220}}})
    assert title == "Too little history to forecast weekly sales"
    assert "only 3 months" in text and "dependable estimate" in text
    assert "120" not in text and "20 to 220" not in text


def test_identical_displayed_forecast_bounds_are_not_reported_as_certain():
    title, text = forecast_wording({"metric": "sales", "latest_value": 100,
        "observations": 12, "predictions": {"next_month": {
            "value": 15080, "lower": 15079.99, "upper": 15080.01}}})
    assert title == "No dependable forecast range for sales"
    assert "15,080 to 15,080" not in text and "possible rise" not in text


@pytest.mark.parametrize(("latest", "direction"), [(100, "rise"), (200, "fall")])
def test_forecast_direction_requires_a_range_outside_the_latest_value(latest, direction):
    _, text = forecast_wording({"metric": "sales", "latest_value": latest,
        "predictions": {"next_month": {"value": 150, "lower": 120, "upper": 180}}})
    assert f"possible {direction}" in text and "result may differ" in text
    _, text = forecast_wording({"metric": "sales", "latest_value": latest, "change_direction_supported": False,
        "predictions": {"next_month": {"value": 150, "lower": 120, "upper": 180}}})
    assert "possible rise" not in text and "possible fall" not in text


def test_invalid_forecast_range_does_not_create_direction_or_planning_bounds():
    _, text = forecast_wording({"metric": "sales", "latest_value": 100,
        "predictions": {"next_month": {"value": 150, "lower": 180, "upper": 120}}})
    assert "No usable range" in text and "possible rise" not in text and "both ends" not in text


def test_recommendation_names_the_actual_measure_and_keeps_source_unchanged():
    anomaly = {"column": "avg_order_value", "value": 89.45, "context": {"region": "North America"}}
    original = {"type": "recommendation", "title": "Look into unusual values", "description": "Review",
        "data": {"confidence_source": "rule:anomaly"}}
    metadata = {"anomalies": [anomaly]}
    before = deepcopy(metadata)
    shown = present_insight(original, metadata)
    assert shown["title"] == "Review the average order value entry of 89.45"
    assert "original file" in shown["description"] and "similar dates or groups" in shown["description"]
    assert "North America" in shown["data"]["evidence"]
    assert metadata == before and original["title"] == "Look into unusual values"
    assert present_insight(shown, metadata) == shown


def test_missing_identifier_details_are_optional_not_automatically_an_error():
    issue = {"column": "Site Name", "type": "missing_values", "affected_rows": 193,
             "description": "43.8% of values are missing"}
    original = {"type": "recommendation", "title": "Review quality", "description": "Review",
        "data": {"confidence_source": "rule:data_quality", "column": "Site Name", "evidence": issue["description"]}}
    metadata = {"data_quality": {"issues": [issue]}}
    shown = present_insight(original, metadata)
    assert "blank site name" in shown["title"]
    assert "193 entries" in shown["data"]["evidence"]
    assert "optional" in shown["description"] and "rather than guessing" in shown["description"]
    assert "increase revenue" not in shown["description"]
    assert present_insight(shown, metadata) == shown


def test_contextual_wording_keeps_owner_entry_links_and_export_figures():
    from app.api.v1.endpoints.analyses import _insight_dicts
    from app.schemas.analysis import AnalysisDetailResponse

    issue = {"column": "Site Name", "type": "missing_values", "affected_rows": 1,
             "description": "50.0% of values are missing"}
    metadata = {"data_quality": {"issues": [issue]}}
    now, analysis_id = datetime.now(UTC), uuid4()
    insight = SimpleNamespace(id=uuid4(), analysis_id=analysis_id, type="recommendation", title="Review quality",
        description="Review", importance="high", confidence=.8, chart_config=None, created_at=now,
        sort_order=200, user_feedback="helpful", data={"confidence_source": "rule:data_quality",
        "column": "Site Name", "evidence": issue["description"]})
    report = AnalysisDetailResponse(id=analysis_id, name="Orders", status="completed", file_id=uuid4(),
        filename="orders.csv", row_count=2, column_count=1, created_at=now, updated_at=now,
        summary=None, metadata=metadata, insights=[InsightResponse.model_validate(insight)])
    shown = report.insights[0]
    assert "blank site name" in shown.title and shown.user_feedback == "helpful"
    assert shown.data["evidence_link"]["insight_id"] == str(insight.id)
    exported = _insight_dicts(SimpleNamespace(insights=[insight], metadata_=metadata))[0]
    assert exported["title"] == shown.title
    assert exported["data"]["supporting_figures"]["figures"][0]["value"] == 1
    assert insight.title == "Review quality"


def test_monthly_forecast_is_not_described_as_a_single_week_or_entry():
    _, text = forecast_wording({"metric": "Weekly_Sales", "method": "linear_regression_monthly",
        "latest_value": 100, "predictions": {"next_month": {"value": 120, "lower": 80, "upper": 160}}})
    assert "next month's total is estimated" in text and "latest month's total was 100" in text
    assert "totals across the entries dated in each month" in text


def test_legacy_forecast_action_keeps_its_measured_context_on_repeated_reads():
    forecast = {"metric": "revenue", "latest_value": 100, "observations": 18,
                "change_percent_next_month": 50, "predictions": {"next_month": {"value": 150, "lower": 120, "upper": 180}}}
    original = {"type": "recommendation", "title": "Prepare for Revenue increase", "description": "Review",
                "data": {"confidence_source": "rule:forecast"}}
    metadata = {"forecasts": [forecast]}
    shown = present_insight(original, metadata)
    assert shown["title"] == "Check next month's plans for revenue"
    assert "possible rise" in shown["description"] and shown["data"]["column"] == "revenue"
    assert present_insight(shown, metadata) == shown


@pytest.mark.parametrize(("forecast", "title"), [
    ({"metric": "weekly_sales", "latest_value": 14_700, "observations": 3,
      "predictions": {"next_month": {"value": 15_080, "lower": 15_080, "upper": 15_080}}},
     "Wait for more history before forecasting weekly sales"),
    ({"metric": "weekly_sales", "latest_value": 14_700, "observations": 12,
      "predictions": {"next_month": {"value": 15_080, "lower": 15_079.99, "upper": 15_080.01}}},
     "Wait for a usable range before forecasting weekly sales"),
])
def test_saved_unsupported_forecast_action_does_not_recommend_the_estimate(forecast, title):
    from app.api.v1.endpoints.analyses import _insight_dicts

    original = {"type": "recommendation", "title": "Prepare for Weekly Sales increase",
                "description": "Plan around 15,080", "data": {"confidence_source": "rule:forecast",
                    "column": "weekly_sales", "problem": "Sales may rise to 15,080",
                    "evidence": "3 months support a forecast of 15,080"}}
    metadata = {"forecasts": [forecast]}
    shown = present_insight(original, metadata)
    assert shown["title"] == title
    assert "15,080" not in shown["description"]
    assert "15,080" not in shown["data"]["evidence"]
    assert "15,080" not in str(shown["data"]["supporting_figures"])
    assert "15,080" not in shown["data"]["problem"]
    assert present_insight(shown, metadata) == shown

    insight = SimpleNamespace(**original, sort_order=0, importance="medium")
    exported = _insight_dicts(SimpleNamespace(insights=[insight], metadata_=metadata))[0]
    assert exported["title"] == shown["title"]
    assert "15,080" not in exported["description"]
