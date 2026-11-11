from types import SimpleNamespace

import polars as pl
import pytest
from openpyxl import Workbook

from app.analytics.measure_grain import annotate_measure_grain, is_repeated_lookup
from app.services.file_processor import FileProcessor
from app.services.investigation import ComparisonPlan, ComparisonUnavailable, validate_plan
from app.services.relational_files import enrich_related_files


def related_workbook(path):
    workbook = Workbook()
    details = workbook.active
    details.title = "Details"
    details.append(["item_id", "order_id", "amount"])
    for row in [("I1", "O1", 10), ("I2", "O1", 20), ("I3", "missing", 30)]:
        details.append(row)
    orders = workbook.create_sheet("Orders")
    orders.append(["order_id", "customer_id", "freight"])
    orders.append(["O1", "C1", 10])
    orders.append(["O2", "C2", 20])
    workbook.save(path)


@pytest.mark.parametrize("reverse", [False, True])
def test_combining_enriched_workbook_preserves_sheet_measure_grain(tmp_path, reverse):
    workbook = tmp_path / "orders.xlsx"
    related_workbook(workbook)
    customers = tmp_path / "customers.csv"
    customers.write_text("customer_id,region\nC1,North\nC2,South\n", encoding="utf-8")
    files = [SimpleNamespace(id="orders", original_filename=workbook.name, storage_path=str(workbook)),
             SimpleNamespace(id="customers", original_filename=customers.name, storage_path=str(customers))]
    context = {}
    output = tmp_path / "combined.parquet"
    FileProcessor()._combine_uploaded_files_sync(files[::-1] if reverse else files, str(output), context)
    combined = pl.read_parquet(output)
    origin = context["relationship_resolution"]["field_origins"]["freight"]
    assert origin["source_table"] == origin["source_sheet"] == "Orders"
    assert origin["source_file"] == "orders.xlsx" and origin["source_file_id"] == "orders"
    assert origin["kind"] == "lookup" and origin["repeated"]
    assert combined[origin["entity_key_columns"][0]].to_list() == ["O1", "O1", None]
    assert combined.height == 3 and combined["amount"].sum() == 60
    schema = annotate_measure_grain([{"name": "freight", "is_numeric": True, "analysis_role": "metric"}], context)
    with pytest.raises(ComparisonUnavailable, match="complete source ID"):
        validate_plan(ComparisonPlan(aggregation="sum", column="freight"), {"schema": schema})


def inherited_lookup():
    return {"charge": {"source_table": "Headers", "source_sheet": "Headers", "source_file": "nested.xlsx",
        "source_column": "charge", "kind": "lookup", "repeated": True,
        "entity_key_columns": ["header_id"], "source_rows": 2, "key_basis": "parent_primary"}}


def test_nested_lookup_retains_nullable_parent_keys_through_outer_renames():
    facts = pl.DataFrame({"entry_id": ["E1", "E2", "E3", "E4"], "record_id": ["R1", "R1", "R2", "missing"],
                         "header_id": ["keep"] * 4, "charge": [1, 2, 3, 4]})
    nested = pl.DataFrame({"record_id": ["R1", "R2", "R3"], "header_id": ["H1", "H1", None], "charge": [10, 10, None]})
    joined, report = enrich_related_files([facts, nested], table_origins=[{}, inherited_lookup()])
    renamed_charge = report["joins"][0]["renamed_fields"]["charge"]
    origin = report["field_origins"][renamed_charge]
    assert is_repeated_lookup({"measure_grain": origin})
    assert origin["source_table"] == "Headers" and origin["source_file"] == "nested.xlsx"
    assert origin["source_rows"] == 2 and origin["matched_entries"] == 3
    assert origin["entity_key_columns"] == [report["joins"][0]["renamed_fields"]["header_id"]]
    assert joined[origin["entity_key_columns"][0]].to_list() == ["H1", "H1", "H1", None]
    record_origin = report["field_origins"][report["joins"][0]["renamed_fields"]["record_id"]]
    assert record_origin["entity_key_columns"] == [report["joins"][0]["renamed_fields"]["record_id"]]


@pytest.mark.parametrize("with_lookup", [False, True])
def test_partitioned_sources_preserve_each_inner_origin_and_repeated_flag(with_lookup):
    first = pl.DataFrame({"record_id": ["R1", "R2"], "header_id": ["H1", "H1"], "charge": [10, 10],
                          "customer_id": ["C1", "C1"]})
    second = pl.DataFrame({"record_id": ["R3"], "header_id": ["H2"], "charge": [20], "customer_id": ["C2"]})
    frames = [first, second]
    names = ["nested.xlsx", "plain.csv"]
    origins = [inherited_lookup(), {}]
    if with_lookup:
        frames.append(pl.DataFrame({"customer_id": ["C1", "C2"], "region": ["North", "South"]}))
        names.append("customers.csv")
        origins.append({})
    joined, report = enrich_related_files(frames, table_names=names, table_origins=origins)
    assert report["status"] == ("enriched" if with_lookup else "stacked")
    if with_lookup:
        assert joined.height == 3 and joined["charge"].to_list() == [10, 10, 20]
    origin = report["field_origins"]["charge"]
    assert is_repeated_lookup({"measure_grain": origin})
    assert origin["source_table"] == "Multiple source tables"
    assert {source["source_table"] for source in origin["source_origins"]} == {"Headers", "plain.csv"}
    assert origin["source_origins"][0]["entity_key_columns"] == ["header_id"]
