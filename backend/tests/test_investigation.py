from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import polars as pl
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.analyses import _investigation_analysis
from app.services.investigation import (
    ComparisonPlan,
    EntryRequest,
    compare,
    entries,
    evidence_spec,
    supporting_figures,
    validate_plan,
)


@pytest.fixture
def analysis(tmp_path):
    frame = pl.DataFrame({"id": [1, 2, 3, 4], "region": ["North-America", " North America ", "South", None],
        "revenue": [10., 20., 100., None], "weight": [1., 3., 0., -1.],
        "date": [date(2025, 1, 1), date(2025, 1, 2), date(2025, 2, 1), date(2025, 2, 2)]})
    path = tmp_path / "source.parquet"
    frame.write_parquet(path)
    schema = [{"name": "id", "is_numeric": True, "analysis_role": "identifier"},
              {"name": "region", "is_numeric": False, "analysis_role": "dimension"},
              *[{"name": name, "is_numeric": True, "analysis_role": "metric"} for name in ["revenue", "weight"]],
              {"name": "date", "is_date": True, "analysis_role": "temporal_dimension"}]
    return SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)), row_count=4,
        metadata_={"schema": schema, "data_quality": {"issues": [{"type": "outliers", "column": "revenue",
        "affected_rows": 2, "bounds": {"lower": 15., "upper": 50.}}]}}, insights=[])


async def test_group_totals_and_drilldown_use_the_same_normalized_groups(analysis):
    plan = ComparisonPlan(aggregation="sum", column="revenue", group_by="region")
    result = await compare(analysis, plan)
    assert result["groups"][0]["group"] == "South" and result["groups"][0]["value"] == 100
    north = next(group for group in result["groups"] if group["group"] == "North America")
    assert north["value"] == 30 and north["entries"] == 2
    found = await entries(analysis, EntryRequest(kind="comparison", comparison=plan, group_value=north["group_value"]))
    assert found["matched_entries"] == 2
    assert [e["entry_number"] for e in found["entries"]] == [1, 2]
    assert result["answer"].startswith("South has the highest total revenue, at 100. That is 70 more than North America.")


async def test_affected_entries_match_saved_strict_bounds_and_paginate(analysis):
    first = await entries(analysis, EntryRequest(kind="quality", issue_index=0, limit=1))
    second = await entries(analysis, EntryRequest(kind="quality", issue_index=0, limit=1, offset=1))
    assert first["matched_entries"] == 2 and first["has_more"]
    assert first["entries"][0]["values"]["revenue"] == 10
    assert second["entries"][0]["entry_number"] == 3
    assert second["entries"][0]["values"]["revenue"] == 100
    assert not second["has_more"]


async def test_changed_saved_count_does_not_silently_show_different_entries(analysis):
    analysis.metadata_["data_quality"]["issues"][0]["affected_rows"] = 13
    with pytest.raises(ValueError, match="no longer matches"):
        await entries(analysis, EntryRequest(kind="quality", issue_index=0))


async def test_recommendation_links_to_its_own_measured_entry(analysis):
    anomaly = {"column": "revenue", "value": 100, "context": {"region": "South", "date": "2025-02-01"}}
    analysis.metadata_["anomalies"] = [anomaly]
    insight = SimpleNamespace(id=uuid4(), type="recommendation", data={"confidence_source": "rule:anomaly"})
    analysis.insights = [insight]
    result = await entries(analysis, EntryRequest(kind="insight", insight_id=str(insight.id)))
    assert result["matched_entries"] == 1 and result["entries"][0]["entry_number"] == 3
    with pytest.raises(ValueError, match="saved entry link"):
        await entries(analysis, EntryRequest(kind="insight", insight_id=str(uuid4())))


async def test_filters_are_values_not_sql(analysis):
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", filters=[{
        "column": "region", "op": "in", "values": ["South' OR 1=1 --"]}]))
    assert result["matched_entries"] == 0 and result["groups"][0]["value"] is None
    assert "No entries match" in result["answer"]


@pytest.mark.parametrize("plan", [
    {"aggregation": "sum", "column": "id"},
    {"aggregation": "average", "column": "region"},
    {"aggregation": "sum", "column": 'revenue"; DROP TABLE data; --'},
    {"aggregation": "sum", "column": "revenue", "group_by": "missing"},
    {"aggregation": "count", "column": "id"},
    {"aggregation": "sum", "column": "revenue", "group_by": "region", "date_bucket": "month"},
])
def test_only_valid_source_roles_and_operations_are_calculated(analysis, plan):
    with pytest.raises(ValueError):
        validate_plan(ComparisonPlan(**plan), analysis.metadata_)


def test_rates_are_not_added_as_if_they_were_amounts(analysis):
    analysis.metadata_["schema"].append({"name": "discount_pct", "is_numeric": True, "analysis_role": "metric"})
    with pytest.raises(ValueError, match="rate or average"):
        validate_plan(ComparisonPlan(aggregation="sum", column="discount_pct"), analysis.metadata_)


async def test_weights_dates_missing_groups_and_sampling_are_explicit(analysis):
    analysis.metadata_["data_profile"] = {"dataset": {"sample_truncated": True}}
    weighted = await compare(analysis, ComparisonPlan(aggregation="weighted_average", column="revenue", weight_column="weight"))
    assert weighted["groups"][0]["value"] == 17.5
    assert weighted["groups"][0]["supplied_values"] == 2
    assert "positive weights" in weighted["scope"] and "not the whole file" in weighted["scope"]
    monthly = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", group_by="date", date_bucket="month"))
    assert sorted(group["value"] for group in monthly["groups"]) == [30, 100]
    missing = await entries(analysis, EntryRequest(kind="comparison", comparison=ComparisonPlan(aggregation="count", group_by="region"), group_value=None))
    assert missing["matched_entries"] == 1 and missing["entries"][0]["entry_number"] == 4


async def test_owner_check_happens_before_any_file_is_opened():
    owner = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await _investigation_analysis(uuid4(), owner, db)
    assert error.value.status_code == 404
    statement = db.execute.call_args.args[0]
    assert owner.id in statement.compile().params.values()


def test_original_source_gap_without_matching_analysed_check_has_no_false_link(analysis):
    assert evidence_spec(analysis.metadata_, {"type": "recommendation", "data": {
        "confidence_source": "rule:data_quality", "column": "region", "evidence": "Original region had 50 blanks"}}) is None


async def test_old_supporting_link_cannot_silently_follow_a_new_report(analysis):
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", group_by="region"))
    analysis.metadata_["data_profile"] = {"generated_at": "a later run"}
    with pytest.raises(ValueError, match="report has changed"):
        await entries(analysis, EntryRequest(kind="comparison", comparison=ComparisonPlan(**result["plan"]), evidence_revision=result["evidence_revision"]))


async def test_exact_duplicates_exclude_the_first_copy_and_do_not_duplicate_source_aliases(analysis):
    frame = pl.DataFrame({"id": [1, 1, 2], "revenue": [10., 10., 20.], "__zephyr_entry": [7, 7, 8]})
    frame.write_parquet(analysis.file.storage_path)
    analysis.row_count = 3
    analysis.metadata_["schema"] = [c for c in analysis.metadata_["schema"] if c["name"] in {"id", "revenue"}] + [{"name": "__zephyr_entry", "analysis_role": "identifier"}]
    analysis.metadata_["data_quality"]["issues"] = [{"type": "duplicates", "affected_rows": 1}]
    result = await entries(analysis, EntryRequest(kind="quality", issue_index=0))
    assert result["matched_entries"] == 1
    assert result["entries"][0]["entry_number"] == 2
    assert result["entries"][0]["values"]["__zephyr_entry"] == 7


async def test_chat_executes_a_valid_plan_and_ignores_model_authored_numbers(analysis, monkeypatch):
    import json

    from app.services import ai_service
    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "answer_kind": "calculated", "answer": "Profit is 999", "plan": {
                "aggregation": "sum", "column": "revenue", "group_by": "region"}})))])
    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    analysis.insights = []
    result = await ai_service.AIService().chat(analysis, [], "Which region has the most revenue?")
    assert "South" in result["content"] and "100" in result["content"] and "999" not in result["content"]
    assert result["metadata"]["method"] == "measured_chat_queries_v1"
    assert result["metadata"]["comparison"]["groups"][0]["value"] == 100


async def test_invalid_model_plan_does_not_count_as_a_success(analysis, monkeypatch):
    import json

    from app.services import ai_service
    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "answer_kind": "calculated", "plan": {"aggregation": "sum", "column": "id"}})))])
    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = await ai_service.AIService().chat(analysis, [], "Sum the IDs")
    assert result["metadata"]["status"] == "unsupported" and not result["metadata"]["free_form_used"]


def test_recommendation_figures_use_the_saved_forecast_not_an_invented_benefit():
    forecast = {"metric": "revenue", "latest_value": 100, "observations": 18,
                "change_percent_next_month": 50, "predictions": {"next_month": {"value": 150, "lower": 120, "upper": 180}}}
    figures = supporting_figures({"forecasts": [forecast]}, {"type": "recommendation",
        "title": "Prepare for Revenue increase", "data": {"confidence_source": "rule:forecast"}})
    assert [f["value"] for f in figures["figures"]] == [100, 150, 120, 180]
    assert "18 months" in figures["basis"] and "not a promise" in figures["basis"]


async def test_legacy_full_file_count_does_not_override_a_known_sample_count(analysis):
    analysis.row_count = 10000
    analysis.metadata_["data_profile"] = {"dataset": {"sample_truncated": True, "row_count": 4}}
    result = await compare(analysis, ComparisonPlan(aggregation="count"))
    assert result["groups"][0]["value"] == 4
    assert "first 4 imported entries, not the whole file" in result["scope"]


async def test_nonfinite_results_are_not_presented_as_verified_totals(analysis):
    frame = pl.read_parquet(analysis.file.storage_path)
    frame.with_columns(pl.when(pl.col("id") == 1).then(float("inf")).otherwise(pl.col("revenue")).alias("revenue")).write_parquet(analysis.file.storage_path)
    with pytest.raises(ValueError, match="cannot be used as numbers"):
        await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue"))


async def test_ranking_does_not_invent_a_winner_when_ties_are_hidden_by_limit(analysis):
    frame = pl.read_parquet(analysis.file.storage_path).with_columns(
        pl.when(pl.col("id") == 3).then(30.).otherwise(pl.col("revenue")).alias("revenue"))
    frame.write_parquet(analysis.file.storage_path)
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", group_by="region", limit=1))
    assert result["answer"] == "2 groups tie for the highest total revenue at 30 each."
    assert len(result["groups"]) == 1 and result["ranking"]["tied"] == 2


async def test_lowest_averages_and_negative_totals_keep_their_actual_meaning(analysis):
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="revenue", group_by="region", order="asc", limit=1))
    assert result["answer"].startswith("North America has the lowest average revenue per entry, at 15.")
    assert "85 less than South" in result["answer"]
    frame = pl.read_parquet(analysis.file.storage_path).with_columns((-pl.col("revenue")).alias("revenue"))
    frame.write_parquet(analysis.file.storage_path)
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", group_by="region"))
    assert result["answer"].startswith("North America has the highest total revenue, at -30.")
    assert "70 more than South" in result["answer"]


async def test_missing_group_and_single_group_are_not_claimed_as_business_leaders(analysis):
    result = await compare(analysis, ComparisonPlan(aggregation="count", group_by="region", filters=[{
        "column": "region", "op": "in", "values": ["South"]}]))
    assert "only group in this comparison" in result["answer"] and "highest" not in result["answer"]
    frame = pl.read_parquet(analysis.file.storage_path).with_columns(
        pl.when(pl.col("id") == 4).then(200.).otherwise(pl.col("revenue")).alias("revenue"))
    frame.write_parquet(analysis.file.storage_path)
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", group_by="region"))
    assert result["answer"].startswith("Entries without region have the highest total revenue, at 200.")


def test_saved_chat_ranking_gets_the_new_headline_without_rewriting_history():
    from copy import deepcopy
    from datetime import UTC, datetime

    from app.schemas.chat import ChatMessageResponse
    comparison = {"answer": "Old list", "scope": "Based on 4 entries.", "matched_entries": 4, "group_count": 2,
        "plan": {"aggregation": "sum", "column": "revenue", "group_by": "region"},
        "groups": [{"group": "South", "value": 100}, {"group": "North", "value": 30}]}
    original = {"id": uuid4(), "session_id": uuid4(), "role": "assistant", "content": "Old list",
        "chart_config": None, "created_at": datetime.now(UTC), "internal_metadata": {
        "method": "measured_chat_queries_v1", "status": "succeeded", "comparison": comparison}}
    before = deepcopy(original)
    shown = ChatMessageResponse.model_validate(original)
    assert shown.content.startswith("South has the highest total revenue, at 100.")
    assert "70 more than North" in shown.content and original == before


async def test_numbered_groups_are_identified_by_their_field(analysis):
    frame = pl.read_parquet(analysis.file.storage_path).with_columns(
        pl.when(pl.col("id") == 3).then(pl.lit("20")).otherwise(pl.col("region")).alias("region"))
    frame.write_parquet(analysis.file.storage_path)
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="revenue", group_by="region"))
    assert result["answer"].startswith("Region 20 has the highest total revenue")
