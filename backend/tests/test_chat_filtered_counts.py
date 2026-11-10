import json
from types import SimpleNamespace

import polars as pl
import pytest

from app.services import ai_service
from app.services.ai_service import AIService, _normalise_filtered_count
from app.services.investigation import ComparisonPlan


@pytest.mark.parametrize(("operation", "values"), [
    ("in", [1]), ("in", [0, 1]), ("between", [0, 1]), ("gt", [0]),
    ("gte", [1]), ("lt", [2]), ("lte", [1]),
])
def test_numeric_predicate_makes_counted_column_non_null(operation, values):
    plan = ComparisonPlan(aggregation="count", column="reading", filters=[
        {"column": "reading", "op": operation, "values": values}])
    result = _normalise_filtered_count(plan, {"reading": {"is_numeric": True}})
    assert result.column is None
    assert result.filters == plan.filters
    assert plan.column == "reading"


@pytest.mark.parametrize(("column", "schema", "filters"), [
    ("reading", {"reading": {"is_numeric": True}}, []),
    ("reading", {"reading": {"is_numeric": True}}, [{"column": "other", "op": "in", "values": [1]}]),
    ("reading", {"reading": {"is_numeric": True}}, [{"column": "reading", "op": "in", "values": ["unknown"]}]),
    ("label", {"label": {"is_numeric": False}}, [{"column": "label", "op": "in", "values": [1]}]),
    ("missing", {}, [{"column": "missing", "op": "in", "values": [1]}]),
])
def test_ambiguous_nonblank_counts_keep_strict_validation(column, schema, filters):
    plan = ComparisonPlan(aggregation="count", column=column, filters=filters)
    assert _normalise_filtered_count(plan, schema) is plan


@pytest.mark.parametrize(("operation", "values", "expected"), [
    ("in", [1], 2), ("gte", [1], 3),
])
async def test_live_planner_count_shape_runs_the_actual_filtered_query(tmp_path, monkeypatch, operation, values, expected):
    parquet = tmp_path / "readings.parquet"
    pl.DataFrame({"reading": [None, 0, 1, 1, 2]}).write_parquet(parquet)
    payload = {"answer_kind": "calculated", "plan": {"aggregation": "count", "column": "reading",
        "filters": [{"column": "reading", "op": operation, "values": values}]}}

    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    analysis = SimpleNamespace(id="count-test", row_count=5, column_count=1, insights=[],
        file=SimpleNamespace(storage_path=str(parquet)), metadata_={"schema": [
            {"name": "reading", "is_numeric": True, "analysis_role": "metric"}]})
    answer = await AIService().chat(analysis, [], "How many readings match this numeric condition?")
    assert answer["metadata"]["status"] == "succeeded"
    comparison = answer["metadata"]["comparison"]
    assert comparison["groups"][0]["value"] == expected
    assert comparison["plan"]["column"] is None
