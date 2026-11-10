import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.analytics.live_filter import validate_filters
from app.services.file_processor import FileProcessor
from app.services.investigation import (
    ComparisonPlan,
    ComparisonUnavailable,
    EntryRequest,
    compare,
    entries,
    validate_plan,
)


@pytest.fixture
def sales(tmp_path):
    frame = pl.DataFrame({"customer_id": ["001", "001", "1", "D0001", "D0001"],
                          "amount": [10., 20., 50., 4., 6.]})
    path = tmp_path / "sales.parquet"
    frame.write_parquet(path)
    return SimpleNamespace(id=uuid4(), row_count=5, file=SimpleNamespace(storage_path=str(path)), metadata_={"schema": [
        {"name": "customer_id", "analysis_role": "identifier", "is_numeric": False},
        {"name": "amount", "analysis_role": "metric", "is_numeric": True},
    ]}, insights=[])


async def test_customer_id_groups_answer_who_spent_most_and_preserve_drilldowns(sales):
    original = deepcopy(sales.metadata_)
    plan = ComparisonPlan(aggregation="sum", column="amount", group_by="customer_id")
    result = await compare(sales, plan)
    assert result["groups"][0]["group_value"] == "1" and result["groups"][0]["value"] == 50
    zero_padded = next(g for g in result["groups"] if g["group_value"] == "001")
    assert zero_padded["value"] == 30
    linked = await entries(sales, EntryRequest(kind="comparison", comparison=plan, group_value="001"))
    assert linked["matched_entries"] == 2
    assert {row["values"]["customer_id"] for row in linked["entries"]} == {"001"}
    assert sales.metadata_ == original


@pytest.mark.parametrize(("code", "expected"), [("001", 30), ("1", 50), ("D0001", 10)])
async def test_exact_identifier_filters_keep_codes_separate(sales, code, expected):
    plan = ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "customer_id", "op": "in", "values": [code]}])
    for use_model_resolution in (False, True):
        result = await compare(sales, plan, resolve_categories=use_model_resolution)
        assert result["groups"][0]["value"] == expected
        assert result["plan"]["filters"][0]["values"] == [code]
        linked = await entries(sales, EntryRequest(kind="comparison", comparison=ComparisonPlan(**result["plan"])))
        assert linked["matched_entries"] == (1 if code == "1" else 2)


async def test_identifier_matching_never_case_folds_or_treats_values_as_sql(sales):
    for code in ("d0001", "D0001' OR 1=1 --"):
        plan = ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "customer_id", "op": "in", "values": [code]}])
        result = await compare(sales, plan)
        assert result["matched_entries"] == 0
        with pytest.raises(ComparisonUnavailable, match="exact code"):
            await compare(sales, plan, resolve_categories=True)
    assert (await compare(sales, ComparisonPlan(aggregation="count")))["groups"][0]["value"] == 5


@pytest.mark.parametrize("requested", [1, 1.0, "1", "1.0"])
async def test_numeric_identifier_filters_use_native_parameterised_equality(tmp_path, requested):
    path = tmp_path / "numbers.parquet"
    pl.DataFrame({"customer_id": [1, 1, 2], "amount": [10., 20., 50.]}).write_parquet(path)
    item = SimpleNamespace(id=uuid4(), row_count=3, file=SimpleNamespace(storage_path=str(path)), metadata_={"schema": [
        {"name": "customer_id", "is_numeric": True, "analysis_role": "identifier"},
        {"name": "amount", "is_numeric": True, "analysis_role": "metric"},
    ]})
    plan = ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "customer_id", "op": "in", "values": [requested]}])
    result = await compare(item, plan, resolve_categories=True)
    assert result["groups"][0]["value"] == 30
    linked = await entries(item, EntryRequest(kind="comparison", comparison=plan))
    assert linked["matched_entries"] == 2


def test_identifier_comparisons_do_not_relax_dashboard_filters_or_id_measures(sales):
    selected = [{"column": "customer_id", "op": "in", "values": ["001"]}]
    with pytest.raises(ValueError, match="not filterable"):
        validate_filters(selected, sales.metadata_["schema"])
    with pytest.raises(ValueError, match="measurable number"):
        validate_plan(ComparisonPlan(aggregation="sum", column="customer_id"), sales.metadata_)


async def test_assistant_uses_owner_scoped_customer_groups(sales, monkeypatch):
    from app.services import ai_service

    async def create(**kwargs):
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "answer_kind": "calculated", "plan": {"aggregation": "sum", "column": "amount", "group_by": "customer_id"},
        })))])
    monkeypatch.setattr(ai_service, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = await ai_service.AIService().chat(sales, [], "Which customer spent the most?")
    assert result["metadata"]["status"] == "succeeded"
    assert result["metadata"]["comparison"]["groups"][0]["value"] == 50
    assert "Customer ID 1" in result["content"]


async def test_raw_join_distinct_groups_filters_and_drilldowns_share_id_whitespace_rules(tmp_path):
    raw_ids = [" \t\u00a0001\u00a0\t ", "001", "1", "0 01", " 0 01 "]
    facts = pl.DataFrame({"customer_id": raw_ids, "amount": [10., 20., 50., 2., 3.]})
    lookup = pl.DataFrame({"customer_id": ["001", "1", "0 01"], "region": ["UK", "US", "CA"]})
    context = {"combine_strategy": "portfolio"}
    joined = FileProcessor()._combine_frames([lookup, facts], context)
    assert context["combine_strategy"] == "relational"
    assert joined["customer_id"].to_list() == raw_ids
    assert joined["region"].to_list() == ["UK", "UK", "US", "CA", "CA"]
    path = tmp_path / "raw-joined.parquet"
    joined.write_parquet(path)
    item = SimpleNamespace(id=uuid4(), row_count=5, file=SimpleNamespace(storage_path=str(path)), metadata_={"schema": [
        {"name": "customer_id", "analysis_role": "identifier", "is_numeric": False},
        {"name": "amount", "analysis_role": "metric", "is_numeric": True},
        {"name": "region", "analysis_role": "dimension", "is_numeric": False},
    ], "upload_context": context}, insights=[])
    distinct = await compare(item, ComparisonPlan(aggregation="distinct_count", column="customer_id"))
    assert distinct["groups"][0]["value"] == 3
    grouped = await compare(item, ComparisonPlan(aggregation="sum", column="amount", group_by="customer_id"))
    assert {g["group_value"]: g["value"] for g in grouped["groups"]} == {"001": 30, "1": 50, "0 01": 5}
    for requested in ("001", " 001 ", raw_ids[0]):
        plan = ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "customer_id", "op": "in", "values": [requested]}])
        result = await compare(item, plan, resolve_categories=True)
        assert result["groups"][0]["value"] == 30
        assert "start or end of IDs" in result["scope"]
        linked = await entries(item, EntryRequest(kind="comparison", comparison=plan))
        assert linked["matched_entries"] == 2
        assert {r["values"]["customer_id"] for r in linked["entries"]} == {raw_ids[0], "001"}
    grouped_entries = await entries(item, EntryRequest(kind="comparison", comparison=ComparisonPlan(**grouped["plan"]), group_value="001"))
    assert grouped_entries["matched_entries"] == 2
