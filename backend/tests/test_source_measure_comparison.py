"""Repeated lookup measures use their source IDs, never DISTINCT amounts."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import polars as pl
import pytest

from app.services.investigation import (
    ComparisonFilter,
    ComparisonPlan,
    ComparisonUnavailable,
    EntryRequest,
    compare,
    entries,
    validate_plan,
)


def source_fields(keys=("source_id",), *, source="orders.csv", role=None):
    origin = {"kind": "lookup", "repeated": True, "key_basis": "parent_primary",
              "source_table": source, "entity_key_columns": list(keys)}
    if role:
        origin["source_role"] = role
    fields = [{"name": key, "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
               "analysis_role": "identifier", "semantic_type": "identifier",
               "measure_grain": {**origin, "source_column": key}} for key in keys]
    fields += [{"name": "amount", "dtype": "DOUBLE", "is_numeric": True, "is_date": False,
                "analysis_role": "metric", "semantic_type": "numeric_metric",
                "measure_grain": {**origin, "source_column": "amount"}},
               {"name": "region", "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
                "analysis_role": "dimension", "semantic_type": "categorical_dimension"},
               {"name": "item", "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
                "analysis_role": "dimension", "semantic_type": "categorical_dimension"}]
    return fields


def analysis(tmp_path, data=None, fields=None):
    path = tmp_path / "joined.parquet"
    frame = pl.DataFrame(data or {"source_id": ["001", "001", "002", "003", "003"],
                                 "amount": [5., 5., 5., 20., 20.],
                                 "region": ["A", "A", "A", "B", "B"],
                                 "item": ["x", "x", "y", "x", "y"]})
    frame.write_parquet(path)
    return SimpleNamespace(id="source-test", row_count=len(frame), column_count=len(frame.columns), insights=[],
                           metadata_={"schema": fields or source_fields()},
                           file=SimpleNamespace(storage_path=str(path)))


@pytest.mark.parametrize(("operation", "expected"), [("sum", 30.), ("average", 10.)])
async def test_each_source_id_counts_once_even_when_amounts_match(tmp_path, operation, expected):
    item = analysis(tmp_path)
    result = await compare(item, ComparisonPlan(aggregation=operation, column="amount"))
    assert result["groups"][0]["value"] == expected
    assert result["matched_entries"] == 5
    assert result["groups"][0]["entries"] == 5
    assert result["groups"][0]["aggregation_entities"] == 3
    assert result["groups"][0]["supplied_values"] == 3
    assert result["aggregation_basis"]["entities"] == 3
    assert "each matching record from orders.csv once" in result["scope"]


async def test_source_groups_and_supporting_entry_counts_agree(tmp_path):
    item = analysis(tmp_path)
    plan = ComparisonPlan(aggregation="sum", column="amount", group_by="region")
    result = await compare(item, plan)
    groups = {group["group_value"]: group for group in result["groups"]}
    assert (groups["a"]["value"], groups["a"]["aggregation_entities"], groups["a"]["entries"]) == (10., 2, 3)
    rows = await entries(item, EntryRequest(kind="comparison", comparison=plan, group_value="a"))
    assert rows["matched_entries"] == 3
    assert rows["aggregation_basis"]["entities"] == 2
    assert {row["values"]["source_id"] for row in rows["entries"]} == {"001", "002"}
    assert "Each source record was counted once" in rows["scope"]


async def test_wide_report_drilldown_keeps_the_actual_source_keys_visible(tmp_path):
    data = {"source_id": ["001", "001", "002"], "amount": [5., 5., 10.],
            "region": ["A"] * 3, "item": ["x"] * 3}
    unrelated = []
    for number in range(30):
        name = f"other_id_{number}"
        data[name] = [f"other-{number}"] * 3
        unrelated.append({"name": name, "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
                          "analysis_role": "identifier", "semantic_type": "identifier"})
    item = analysis(tmp_path, data, [*unrelated, *source_fields()])
    supporting = await entries(item, EntryRequest(kind="comparison", comparison=ComparisonPlan(aggregation="sum", column="amount")))
    assert [column["name"] for column in supporting["columns"]][:2] == ["amount", "source_id"]
    assert len(supporting["columns"]) == 20
    assert supporting["matched_entries"] == 3
    assert supporting["aggregation_basis"]["entities"] == 2
    assert {row["values"]["source_id"] for row in supporting["entries"]} == {"001", "002"}


async def test_internal_aliases_cannot_collide_with_a_case_variant_source_header(tmp_path):
    name = "__VESQUIRI_SOURCE_ENTRIES"
    fields = source_fields()
    fields[1]["name"] = name
    item = analysis(tmp_path, {"source_id": ["1", "1", "2"], name: [5., 5., 10.],
                              "region": ["A"] * 3, "item": ["x"] * 3}, fields)
    result = await compare(item, ComparisonPlan(aggregation="sum", column=name))
    assert result["groups"][0]["value"] == 15.
    assert result["groups"][0]["entries"] == 3
    assert result["aggregation_basis"]["entities"] == 2


async def test_comparison_and_drilldown_restore_original_column_words_without_changing_keys(tmp_path):
    fields = [
        {"name": "orderquantity", "dtype": "BIGINT", "is_numeric": True, "is_date": False,
         "analysis_role": "metric", "semantic_type": "count",
         "measure_grain": {"kind": "fact", "source_table": "Sales.csv", "source_column": "OrderQuantity"}},
        {"name": "country_related_2", "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
         "analysis_role": "dimension", "semantic_type": "country",
         "measure_grain": {"kind": "lookup", "repeated": True, "source_table": "Customers.csv", "source_column": "Country"}},
    ]
    item = analysis(tmp_path, {"orderquantity": [2, 5], "country_related_2": ["A", "B"]}, fields)
    plan = ComparisonPlan(aggregation="sum", column="orderquantity", group_by="country_related_2",
                          filters=[ComparisonFilter(column="orderquantity", op="gte", values=[1])])
    result = await compare(item, plan)
    assert result["title"] == "Total order quantity by customer country"
    assert result["measure_label"] == "order quantity"
    assert result["group_label"] == "customer country"
    assert "order quantity was at least 1" in result["scope"]
    assert result["plan"]["column"] == "orderquantity"
    assert result["plan"]["group_by"] == "country_related_2"
    supporting = await entries(item, EntryRequest(kind="comparison", comparison=plan, group_value="b"))
    labels = {column["name"]: column["label"] for column in supporting["columns"]}
    assert labels == {"orderquantity": "order quantity", "country_related_2": "customer country"}
    assert supporting["entries"][0]["values"]["orderquantity"] == 5


async def test_retention_restores_the_original_entity_id_words(tmp_path):
    fields = [
        {"name": "donorid", "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
         "analysis_role": "identifier", "semantic_type": "identifier",
         "measure_grain": {"kind": "fact", "source_table": "Gifts.csv", "source_column": "DonorID"}},
        {"name": "period", "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
         "analysis_role": "dimension", "semantic_type": "categorical_dimension"},
    ]
    item = analysis(tmp_path, {"donorid": ["a", "b", "a"], "period": ["before", "before", "after"]}, fields)
    result = await compare(item, ComparisonPlan(aggregation="retention", column="donorid",
        cohort_filters=[ComparisonFilter(column="period", op="in", values=["before"])],
        return_filters=[ComparisonFilter(column="period", op="in", values=["after"])]))
    assert result["groups"][0]["value"] == 50.
    assert "donor IDs" in result["answer"]
    assert "each different donor ID once" in result["scope"]


async def test_fact_filters_select_source_records_without_repeating_their_amount(tmp_path):
    item = analysis(tmp_path)
    plan = ComparisonPlan(aggregation="sum", column="amount", filters=[ComparisonFilter(column="item", op="in", values=["x"])])
    result = await compare(item, plan)
    assert result["groups"][0]["value"] == 25.
    assert result["matched_entries"] == 3
    assert result["aggregation_basis"]["entities"] == 2
    count = await compare(item, plan.model_copy(update={"aggregation": "count", "column": None}))
    assert count["groups"][0]["value"] == 3
    assert "aggregation_basis" not in count


async def test_composite_source_keys_preserve_year_case_and_leading_zeros(tmp_path):
    item = analysis(tmp_path, {"team": ["001", "001", "001", "a", "A"], "year": ["2024", "2024", "2025", "2024", "2024"],
                              "amount": [10., 10., 20., 30., 40.], "region": ["R"] * 5, "item": ["x"] * 5},
                    source_fields(("team", "year"), source="Teams.csv"))
    result = await compare(item, ComparisonPlan(aggregation="sum", column="amount"))
    assert result["groups"][0]["value"] == 100.
    assert result["aggregation_basis"]["entities"] == 4


async def test_inconsistent_source_value_cannot_be_hidden_by_fact_filter(tmp_path):
    item = analysis(tmp_path, {"source_id": ["1", "1"], "amount": [5., 50.], "region": ["A", "A"], "item": ["x", "y"]})
    plan = ComparisonPlan(aggregation="sum", column="amount", filters=[ComparisonFilter(column="item", op="in", values=["x"])])
    with pytest.raises(ComparisonUnavailable, match="different numbers"):
        await compare(item, plan)
    with pytest.raises(ComparisonUnavailable, match="different numbers"):
        await entries(item, EntryRequest(kind="comparison", comparison=plan))


async def test_whole_parent_value_cannot_be_assigned_to_multiple_child_groups(tmp_path):
    item = analysis(tmp_path)
    with pytest.raises(ComparisonUnavailable, match="several selected groups"):
        await compare(item, ComparisonPlan(aggregation="sum", column="amount", group_by="item"))


@pytest.mark.parametrize("missing", [None, "", "  ", "unknown"])
async def test_number_without_complete_parent_id_is_refused(tmp_path, missing):
    item = analysis(tmp_path, {"source_id": ["1", missing], "amount": [5., 6.], "region": ["A", "A"], "item": ["x", "x"]})
    with pytest.raises(ComparisonUnavailable, match="no complete source ID"):
        await compare(item, ComparisonPlan(aggregation="sum", column="amount"))


async def test_unmatched_lookup_rows_have_no_fabricated_source_entity(tmp_path):
    item = analysis(tmp_path, {"source_id": ["1", "1", None], "amount": [5., 5., None], "region": ["A", "A", "B"], "item": ["x"] * 3})
    result = await compare(item, ComparisonPlan(aggregation="sum", column="amount", group_by="region"))
    assert result["matched_entries"] == 3
    assert result["groups"][0]["entries"] == 2
    assert result["aggregation_basis"]["entities"] == 1
    assert result["aggregation_basis"]["entries_without_source_id"] == 1


async def test_blank_source_measure_keeps_support_rows_but_is_left_out_of_average(tmp_path):
    item = analysis(tmp_path, {"source_id": ["1", "1", "2", "3"], "amount": [10., 10., None, 20.],
                              "region": ["A"] * 4, "item": ["x"] * 4})
    plan = ComparisonPlan(aggregation="average", column="amount")
    result = await compare(item, plan)
    assert result["groups"][0]["value"] == 15.
    assert result["groups"][0]["entries"] == 4
    assert result["groups"][0]["aggregation_entities"] == 3
    assert result["groups"][0]["supplied_values"] == 2
    assert result["aggregation_basis"]["supplied_entities"] == 2
    supporting = await entries(item, EntryRequest(kind="comparison", comparison=plan))
    assert supporting["matched_entries"] == 4
    assert supporting["aggregation_basis"]["entities"] == 3


@pytest.mark.parametrize("defect", ["missing_keys", "missing_part", "missing_provenance", "wrong_role", "wrong_table", "duplicate_keys"])
def test_legacy_or_ambiguous_source_identity_remains_friendly_refusal(defect):
    fields = source_fields()
    amount = fields[1]["measure_grain"]
    if defect == "missing_keys":
        amount["entity_key_columns"] = []
    elif defect == "missing_part":
        amount["entity_key_columns"].append("missing_composite_part")
    elif defect == "missing_provenance":
        fields[0].pop("measure_grain")
    elif defect == "wrong_role":
        fields[0]["measure_grain"]["source_role"] = "other role"
    elif defect == "wrong_table":
        fields[0]["measure_grain"]["source_table"] = "other.csv"
    else:
        amount["entity_key_columns"] = ["source_id", "source_id"]
    with pytest.raises(ComparisonUnavailable, match="complete source ID"):
        validate_plan(ComparisonPlan(aggregation="sum", column="amount"), {"schema": fields})


def test_repeated_rates_ids_and_unverified_flags_keep_numeric_restrictions():
    fields = source_fields()
    for changes in ({"analysis_role": "identifier"}, {"semantic_type": "average_metric"},
                    {"analysis_role": "flag", "semantic_type": "boolean"}):
        selected = deepcopy(fields)
        selected[1].update(changes)
        with pytest.raises(ValueError):
            validate_plan(ComparisonPlan(aggregation="sum", column="amount"), {"schema": selected})


def test_weighted_source_average_stays_unavailable_without_source_weight_semantics():
    with pytest.raises(ComparisonUnavailable):
        validate_plan(ComparisonPlan(aggregation="weighted_average", column="amount", weight_column="amount"), {"schema": source_fields()})
