import math
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest
from pydantic import ValidationError

from app.schemas.analysis import FilterSpec
from app.services.investigation import (
    ComparisonFilter,
    ComparisonPlan,
    EntryRequest,
    _comparison_where,
    compare,
    entries,
    validate_plan,
)


@pytest.fixture
def readings(tmp_path):
    path = tmp_path / "readings.parquet"
    pl.DataFrame({"reading_id": ["001", "002", "003", "004", "005"],
                  "aep_mw": [19999., 20000., 20001., None, 20000.]}).write_parquet(path)
    schema = [{"name": "reading_id", "is_numeric": False, "analysis_role": "identifier"},
              {"name": "aep_mw", "is_numeric": True, "analysis_role": "metric"}]
    return SimpleNamespace(id=uuid4(), row_count=5, file=SimpleNamespace(storage_path=str(path)),
                           metadata_={"schema": schema}, insights=[])


@pytest.mark.parametrize(("op", "expected", "words"), [
    ("gt", 1, "greater than"), ("gte", 3, "at least"),
    ("lt", 1, "less than"), ("lte", 3, "at most"),
])
async def test_one_sided_bounds_have_exact_boundaries_and_matching_drilldowns(readings, op, expected, words):
    plan = ComparisonPlan(aggregation="count", filters=[{"column": "aep_mw", "op": op, "values": [20000]}])
    result = await compare(readings, plan)
    assert result["groups"][0]["value"] == expected
    assert f"{words} 20,000" in result["scope"]
    records = await entries(readings, EntryRequest(kind="comparison", comparison=plan, evidence_revision=result["evidence_revision"]))
    assert records["matched_entries"] == expected


@pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
@pytest.mark.parametrize("values", [[], [1, 2], [True], ["20000"], ["20000 OR 1=1"], [math.inf], [-math.inf], [math.nan], [10**400]])
def test_bounds_require_exactly_one_finite_numeric_value(op, values):
    with pytest.raises(ValidationError):
        ComparisonFilter(column="aep_mw", op=op, values=values)


def test_numeric_bounds_stay_comparison_only_and_use_parameters(readings):
    selected = {"column": "aep_mw", "op": "gte", "values": [20000]}
    with pytest.raises(ValidationError):
        FilterSpec.model_validate(selected)
    plan = ComparisonPlan(aggregation="count", filters=[selected])
    _, _, validated = validate_plan(plan, readings.metadata_)
    sql, parameters = _comparison_where(validated, {field["name"]: field for field in readings.metadata_["schema"]})
    assert sql == '"aep_mw" >= ?'
    assert parameters == [20000]
    assert "20000" not in sql


def test_string_identifiers_are_not_coerced_to_numeric_ranges(readings):
    plan = ComparisonPlan(aggregation="count", filters=[{"column": "reading_id", "op": "gte", "values": [1]}])
    with pytest.raises(ValueError, match="numeric column"):
        validate_plan(plan, readings.metadata_)


async def test_one_sided_numeric_bound_combines_with_exact_zero_padded_id_filter(readings):
    plan = ComparisonPlan(aggregation="count", filters=[
        {"column": "aep_mw", "op": "gte", "values": [20000]},
        {"column": "reading_id", "op": "in", "values": ["002"]},
    ])
    result = await compare(readings, plan, resolve_categories=True)
    assert result["groups"][0]["value"] == 1
    records = await entries(readings, EntryRequest(kind="comparison", comparison=plan))
    assert records["entries"][0]["values"]["reading_id"] == "002"


def test_unknown_field_and_injected_operator_are_rejected(readings):
    with pytest.raises(ValidationError):
        ComparisonFilter(column="aep_mw", op="gte; DROP TABLE data", values=[20000])
    with pytest.raises(ValueError, match="not filterable"):
        validate_plan(ComparisonPlan(aggregation="count", filters=[{"column": 'aep_mw"; DROP TABLE data; --', "op": "gte", "values": [20000]}]), readings.metadata_)
