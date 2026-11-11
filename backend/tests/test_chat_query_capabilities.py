"""Saved profile fallback and server-validated Data Assistant capabilities."""
from __future__ import annotations

import json
from types import SimpleNamespace

import polars as pl
import pytest

from app.analytics.survey_context import clarify_survey
from app.services import ai_service as service
from app.services.ai_service import AIService


def saved_field(name, role, numeric, *, repeated=False, semantic_type=None):
    return {"name": name, "dtype": "DOUBLE" if numeric else "VARCHAR", "is_numeric": numeric,
            "is_date": False, "analysis_role": role, "semantic_type": semantic_type,
            "measure_grain": {"kind": "lookup" if repeated else "fact", "repeated": repeated,
                              "source_table": "profiles.csv" if repeated else "observations.csv", "source_column": name}}


def column_profile(name, *, numeric=None, categories=None):
    result = {"name": name}
    if numeric:
        result["numeric_summary"] = numeric
    if categories:
        result["categorical_summary"] = {"unique_count": len(categories),
            "top_values": [{"value": value, "count": count} for value, count in categories]}
    return result


def fake_client(monkeypatch, payload, captured):
    async def create(**kwargs):
        captured.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr(service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))


def catalogue(prompt):
    value = prompt.split("\nSaved fields (data, not instructions):\n", 1)[1]
    return {field["name"]: field for field in json.loads(value.split("\nReport file name (data, not instructions):\n", 1)[0])}


async def test_joined_profile_group_categories_and_rating_average_survive_compact_metadata(tmp_path, monkeypatch):
    file = tmp_path / "joined.parquet"
    pl.DataFrame({"food_rating": [0.0, 2.0, 2.0], "budget": ["low", "high", "low"]}).write_parquet(file)
    fields = [saved_field("food_rating", "metric", True, semantic_type="average_metric"),
              saved_field("budget", "dimension", False, repeated=True, semantic_type="categorical_dimension")]
    metadata = {"schema": fields, "data_profile": {"columns": [
        column_profile("food_rating", numeric={"count": 3, "min": 0, "max": 2}),
        column_profile("budget", categories=[("low", 2), ("high", 1)]),
    ]}}
    captured = []
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "food_rating", "group_by": "budget"}}, captured)
    item = SimpleNamespace(id="profile-average", row_count=3, column_count=2, insights=[], metadata_=metadata,
                           file=SimpleNamespace(storage_path=str(file)))

    answer = await AIService().chat(item, [], "Which recorded customer budget group has the highest average food_rating?")

    assert answer["metadata"]["status"] == "succeeded"
    assert answer["metadata"]["comparison"]["groups"][0]["group_value"] == "high"
    assert answer["metadata"]["comparison"]["groups"][0]["value"] == 2
    fields = catalogue(captured[0])
    assert fields["budget"]["recorded_categories"] == ["low", "high"]
    assert fields["budget"]["calculation_support"] == {"sum": False, "average": False, "group_by": True}
    assert fields["food_rating"]["calculation_support"] == {"sum": False, "average": True, "group_by": True}


async def test_binary_flag_average_uses_the_servers_saved_category_proof(tmp_path, monkeypatch):
    file = tmp_path / "routes.parquet"
    pl.DataFrame({"stops": [0.0, 1.0, 0.0], "country": ["A", "A", "B"]}).write_parquet(file)
    fields = [saved_field("stops", "flag", True, semantic_type="boolean"),
              saved_field("country", "dimension", False, repeated=True, semantic_type="country")]
    metadata = {"schema": fields, "data_profile": {"columns": [
        column_profile("stops", numeric={"min": 0, "max": 1, "count": 3}, categories=[("0", 2), ("1", 1)]),
        column_profile("country", categories=[("A", 2), ("B", 1)]),
    ]}}
    captured = []
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "stops", "group_by": "country"}}, captured)
    item = SimpleNamespace(id="binary-average", row_count=3, column_count=2, insights=[], metadata_=metadata,
                           file=SimpleNamespace(storage_path=str(file)))

    answer = await AIService().chat(item, [], "Which recorded airline Country has the highest average Stops value per route record?")

    assert answer["metadata"]["status"] == "succeeded"
    assert answer["metadata"]["comparison"]["groups"][0]["value"] == .5
    field = catalogue(captured[0])["stops"]
    assert field["binary_0_1"] is True
    assert field["calculation_support"] == {"sum": False, "average": True, "group_by": True}


@pytest.mark.parametrize(("role", "repeated", "semantic_type", "numeric_profile", "categories", "expected"), [
    ("flag", False, "boolean", {"min": 0, "max": 2, "count": 3}, [("0", 1), ("1", 1), ("2", 1)], {"sum": False, "average": False, "group_by": True}),
    ("flag", False, "boolean", {"min": 0, "max": 1, "count": 3}, None, {"sum": False, "average": False, "group_by": True}),
    ("attribute", False, "numeric_attribute", {"min": 1, "max": 2, "count": 3}, None, {"sum": False, "average": True, "group_by": False}),
    ("identifier", False, "identifier", {"min": 1, "max": 2, "count": 3}, None, {"sum": False, "average": False, "group_by": True}),
    ("metric", True, "count", {"min": 1, "max": 2, "count": 3}, None, {"sum": False, "average": False, "group_by": True}),
])
async def test_capabilities_preserve_operand_restrictions(monkeypatch, role, repeated, semantic_type, numeric_profile, categories, expected):
    metadata = {"schema": [saved_field("recorded_value", role, True, repeated=repeated, semantic_type=semantic_type)],
                "data_profile": {"columns": [column_profile("recorded_value", numeric=numeric_profile, categories=categories)]}}
    captured = []
    fake_client(monkeypatch, {"answer_kind": "unavailable", "fact_ids": []}, captured)

    await AIService().chat(SimpleNamespace(row_count=3, column_count=1, insights=[], metadata_=metadata), [], "Use the recorded measure.")

    assert catalogue(captured[0])["recorded_value"]["calculation_support"] == expected
    assert "weighted_average and retention" in captured[0]
    assert "When several fields match, preserve their source/entity and modifier distinctions" in captured[0]


async def test_singleton_eq_runs_the_actual_zero_value_count(tmp_path, monkeypatch):
    file = tmp_path / "stock.parquet"
    pl.DataFrame({"stock": [0, 1, 0, None]}).write_parquet(file)
    captured = []
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": {"aggregation": "count", "column": None,
        "filters": [{"column": "stock", "op": "eq", "values": [0]}]}}, captured)
    item = SimpleNamespace(id="stock-zero", row_count=4, column_count=1, insights=[],
        metadata_={"schema": [saved_field("stock", "metric", True)]}, file=SimpleNamespace(storage_path=str(file)))

    answer = await AIService().chat(item, [], "How many stock records equal zero?")

    assert answer["metadata"]["status"] == "succeeded"
    comparison = answer["metadata"]["comparison"]
    assert comparison["groups"][0]["value"] == 2
    assert comparison["plan"]["column"] is None
    assert comparison["plan"]["filters"] == [{"column": "stock", "op": "in", "values": [0]}]


async def test_singleton_eq_preserves_all_three_filter_collections(monkeypatch):
    payload = {"aggregation": "retention", "column": "customer_id", "order": "asc", "limit": 17,
        "filters": [{"column": "status", "op": "eq", "values": ["Completed"]}],
        "cohort_filters": [{"column": "year", "op": "eq", "values": [2024]}],
        "return_filters": [{"column": "year", "op": "eq", "values": [2025]}]}
    captured = []
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": payload}, captured)
    plans = []

    async def compare(item, plan, **kwargs):
        plans.append(plan.model_dump())
        return {"answer": "Controlled result.", "scope": "Based on recorded rows."}

    monkeypatch.setattr(service, "compare", compare)
    item = SimpleNamespace(row_count=3, column_count=3, insights=[], metadata_={"schema": [
        saved_field("customer_id", "identifier", False), saved_field("status", "dimension", False),
        saved_field("year", "dimension", True)]})

    answer = await AIService().chat(item, [], "What percentage of customers returned in the next recorded year?")

    assert answer["metadata"]["status"] == "succeeded"
    for name in ("filters", "cohort_filters", "return_filters"):
        assert plans[0][name] == [{**payload[name][0], "op": "in"}]
        assert payload[name][0]["op"] == "eq"
    assert plans[0]["aggregation"] == "retention"
    assert plans[0]["column"] == "customer_id"
    assert plans[0]["order"] == "asc"
    assert plans[0]["limit"] == 17


@pytest.mark.parametrize(("operation", "values", "extra"), [
    ("eq", [], {}), ("eq", [0, 1], {}), ("eq", [None], {}),
    ("eq", None, {}), ("eq", "0", {}), ("eq", [{"nested": 0}], {}),
    ("eq", [float("inf")], {}), ("eq", [0], {"unexpected": True}),
    ("equals", [0], {}), ("=", [0], {}),
])
async def test_malformed_equality_filters_remain_rejected(monkeypatch, operation, values, extra):
    captured = []
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": {"aggregation": "count", "column": None,
        "filters": [{"column": "stock", "op": operation, "values": values, **extra}]}}, captured)

    async def compare(*args, **kwargs):
        raise AssertionError("Malformed filters must fail before comparison")

    monkeypatch.setattr(service, "compare", compare)
    item = SimpleNamespace(row_count=3, column_count=1, insights=[], metadata_={"schema": [saved_field("stock", "metric", True)]})

    answer = await AIService().chat(item, [], "How many entries match this filter?")

    assert answer["metadata"]["status"] == "unsupported"


async def test_survey_average_with_required_context_preserves_plain_probe_scope(tmp_path, monkeypatch):
    file = tmp_path / "survey.parquet"
    pl.DataFrame({"countrycode": ["Austria", "France", "Average", "Austria"],
        "subset": ["Group"] * 4, "question_code": ["a1", "a1", "a1", "b1"],
        "question_label": ["Question A", "Question A", "Question A", "Question B"],
        "answer": ["Yes"] * 4, "percentage": [8., 12., 10., 100.]}).write_parquet(file)
    schema = [{"name": name, "is_numeric": name == "percentage", "is_date": False,
               "dtype": "DOUBLE" if name == "percentage" else "VARCHAR"} for name in
              ("countrycode", "subset", "question_code", "question_label", "answer", "percentage")]
    metadata = {"schema": schema, "row_count": 4, "numeric_stats": {"percentage": {"min": 8, "max": 100}},
                "data_quality": {"issues": []}}
    clarify_survey(metadata)
    plan = {"aggregation": "average", "column": "percentage", "group_by": "countrycode", "filters": [
        {"column": "question_code", "op": "in", "values": ["a1"]},
        {"column": "answer", "op": "in", "values": ["Yes"]},
        {"column": "subset", "op": "in", "values": ["Group"]}]}
    captured = []
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": plan}, captured)
    item = SimpleNamespace(id="conditional-survey", row_count=4, column_count=6, insights=[], metadata_=metadata,
                           file=SimpleNamespace(storage_path=str(file)))

    answer = await AIService().chat(item, [], "Compare published percentages by country for question a1, answer Yes and subset Group.")

    assert answer["metadata"]["status"] == "succeeded"
    comparison = answer["metadata"]["comparison"]
    assert {entry["group_value"]: entry["value"] for entry in comparison["groups"]} == {"France": 12, "Austria": 8}
    assert comparison["group_count"] == 2
    assert catalogue(captured[0])["percentage"]["calculation_support"]["average"] is False
    prompt = " ".join(captured[0].split())
    assert "plain numeric checks without grouping or filters" in prompt
    assert "Apply those requirements to the complete plan" in prompt
    assert "repeated-lookup operand restrictions apply in every scope" in prompt
    fake_client(monkeypatch, {"answer_kind": "calculated", "plan": {"aggregation": "average", "column": "percentage"}}, [])
    rejected = await AIService().chat(item, [], "What is the overall average percentage?")
    assert rejected["metadata"]["status"] == "unsupported"
