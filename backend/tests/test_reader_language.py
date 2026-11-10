from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.analytics.labels import reader_label
from app.analytics.record_context import record_context
from app.services.chat_evidence import explain_fact
from app.services.investigation import ComparisonPlan, compare
from app.services.report_language import present_insight, present_metadata


@pytest.fixture
def gifts(tmp_path):
    frame = pl.DataFrame({
        "gift_id": ["G1", "G2", "G3", "G4"],
        "donor_id": ["D1", "D1", "D2", "D1"],
        "gift_date": [date(2024, 1, 1)] * 3 + [date(2025, 1, 1)],
        "amount_usd": [10., 20., 30., 40.], "status": ["Completed"] * 4,
    })
    path = tmp_path / "gifts.parquet"
    frame.write_parquet(path)
    schema = [
        {"name": name, "analysis_role": "identifier"} for name in ("gift_id", "donor_id")
    ] + [
        {"name": "gift_date", "is_date": True, "analysis_role": "temporal_dimension"},
        {"name": "amount_usd", "is_numeric": True, "analysis_role": "metric"},
        {"name": "status", "analysis_role": "dimension"},
    ]
    return SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)), row_count=4,
        metadata_={"schema": schema, "upload_context": {"combined": True, "combine_strategy": "relational"}}, insights=[])


@pytest.mark.parametrize(("column", "expected"), [
    ("amount_usd", "amount (US dollars)"), ("revenue_gbp", "revenue (British pounds)"),
    ("donor_id", "donor ID"), ("avg_order_value", "average order value"),
])
def test_readable_labels_explain_only_units_supplied_by_the_header(column, expected):
    assert reader_label(column) == expected


@pytest.mark.parametrize("operation", ["total", "mean", "weighted_mean", "min", "max"])
def test_calculation_explanations_use_short_sentences(operation):
    text = explain_fact({"values": {"column": "revenue", "operation": operation, "weighted_by": "quantity"}})
    assert all(len(sentence.split()) <= 22 for sentence in text.split(".") if sentence.strip())
    assert "SUM(" not in text and "AVG(" not in text


def test_verified_summary_uses_real_record_names_and_keeps_its_evidence(gifts):
    facts = [
        {"id": "records", "text": "Four rows.", "calculation": "COUNT(*)", "scope": "analysed file", "values": {"records": 4}},
        {"id": "identity_0", "text": "Four gift IDs.", "calculation": "COUNT(DISTINCT gift_id)", "scope": "analysed file",
         "values": {"column": "gift_id", "distinct_values": 4, "repeated_records": 0}},
        {"id": "metric_0", "text": "Amount sums to 100.", "calculation": "SUM(amount_usd)", "scope": "analysed file",
         "values": {"column": "amount_usd", "operation": "total", "value": 100}},
    ]
    metadata = {**gifts.metadata_, "analysis_evidence": {"summary_checks": {"method": "measured_facts_v1", "facts": facts}}}
    original = deepcopy(metadata)
    shown, summary = present_metadata(metadata, "\n".join(fact["text"] for fact in facts))
    assert "4 gifts" in summary
    visible = shown["analysis_evidence"]["summary_checks"]["facts"]
    assert "\n".join(fact["text"] for fact in visible) == summary
    assert all(fact.get("explanation") and fact.get("scope_explanation") for fact in visible)
    assert visible[-1]["calculation"] == "SUM(amount_usd)"
    assert visible[-1]["values"] == facts[-1]["values"]
    assert metadata == original


def test_old_stacked_report_is_not_described_as_all_gifts(gifts):
    assert record_context(gifts.metadata_)["plural"] == "gifts"
    gifts.metadata_["upload_context"]["combine_strategy"] = "portfolio"
    assert record_context(gifts.metadata_) is None


async def test_retention_explains_counts_percentage_and_dates_without_jargon(gifts):
    plan = ComparisonPlan(aggregation="retention", column="donor_id",
        filters=[{"column": "status", "op": "in", "values": ["Completed"]}],
        cohort_filters=[{"column": "gift_date", "op": "date_between", "values": ["2024-01-01", "2024-12-31"]}],
        return_filters=[{"column": "gift_date", "op": "date_between", "values": ["2025-01-01", "2025-12-31"]}])
    result = await compare(gifts, plan)
    assert "1 of 2 donor IDs" in result["answer"] and "50.0%" in result["answer"]
    assert "in 2024 also appear in 2025" in result["answer"]
    assert "50 out of every 100" in result["answer"]
    assert "divided 1 by 2 and multiplied by 100" in result["scope"]
    assert "1 Jan 2024" in result["scope"] and "31 Dec 2025" in result["scope"]
    prose = result["answer"] + result["scope"]
    assert all(word not in prose for word in ("cohort", "distinct entities", "denominator", "date_between", "donor_id"))
    assert result["cohort"] == {"baseline_entities": 2, "returning_entities": 1}
    assert result["plan"]["column"] == "donor_id"


async def test_average_explains_the_method_and_preserves_the_measured_value(gifts):
    result = await compare(gifts, ComparisonPlan(aggregation="average", column="amount_usd"))
    assert result["groups"][0]["value"] == 25
    assert "US dollars" in result["answer"]
    assert "divided by how many numbers there were" in result["scope"]


def test_kpi_explanation_preserves_values_and_defines_the_average():
    insight = {"type": "summary", "title": "Average amount", "description": "",
               "data": {"column": "amount_usd", "is_total": False, "value": 25}}
    shown = present_insight(insight)
    assert "divided the total" in shown["data"]["calculation_explanation"]
    assert shown["data"]["value"] == 25


def test_legacy_admission_percentage_is_explained_as_an_average():
    insight = {"type": "summary", "title": "Admission chance", "description": "",
               "data": {"column": "chance_of_admit", "is_percent": True, "value": 75}}
    shown = present_insight(insight)
    assert "divided the total" in shown["data"]["calculation_explanation"]
    assert "marked 1" not in shown["data"]["calculation_explanation"]
