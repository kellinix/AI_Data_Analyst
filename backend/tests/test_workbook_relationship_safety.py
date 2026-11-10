from itertools import permutations

import polars as pl
import pytest
from openpyxl import Workbook

from app.services.file_processor import FileProcessor


def write_workbook(path, sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, data in sheets:
        sheet = workbook.create_sheet(name)
        sheet.append(list(data))
        for row in zip(*data.values(), strict=True):
            sheet.append(list(row))
    workbook.save(path)
    return str(path)


@pytest.mark.parametrize("data_rows", [2, 3, 4])
@pytest.mark.parametrize("title_rows", [0, 3])
def test_actual_workbook_limit_counts_data_after_title_and_header(tmp_path, data_rows, title_rows):
    workbook = Workbook()
    sheet = workbook.active
    for index in range(title_rows):
        sheet.append([f"Sales report title line {index + 1}", None])
    sheet.append(["item_id", "amount"])
    for index in range(data_rows):
        sheet.append([f"I{index + 1}", index + 1])
    path = tmp_path / "boundary.xlsx"
    workbook.save(path)
    processor = FileProcessor()
    processor.SAMPLE_ROWS = 3
    frame, truncated = processor._read_file_ex(str(path), ".xlsx")
    assert frame.height == min(data_rows, 3)
    assert frame["item_id"].to_list() == [f"I{index + 1}" for index in range(min(data_rows, 3))]
    assert truncated is (data_rows > 3)


def bridge_sheets(conflicting):
    return [
        ("Facts", {"employee_id": ["U1", "U2", "U3"], "department_code": ["A", "B", "C"],
                   "team_id": ["T1", "T1", "T2"], "amount": [10, 20, 30]}),
        ("Employees", {"employee_id": ["U1", "U2", "U3"],
                       "department_code": ["B", "C", "A"] if conflicting else ["A", "B", "C"],
                       "name": ["e1", "e2", "e3"]}),
        ("Departments", {"department_code": ["A", "B", "C"],
                         "department_name": ["First", "Second", "Third"]}),
        ("Teams", {"team_id": ["T1", "T2"], "team_name": ["One", "Two"]}),
    ]


@pytest.mark.parametrize("order", list(permutations(range(4))))
def test_actual_workbook_rejects_conflicting_identifier_bridge_in_every_sheet_order(tmp_path, order):
    sheets = bridge_sheets(conflicting=True)
    path = write_workbook(tmp_path / "conflicting.xlsx", [sheets[index] for index in order])
    with pytest.raises(ValueError, match="IDs disagree"):
        FileProcessor()._read_file(path, ".xlsx")


@pytest.mark.parametrize("order", [[0, 1, 2, 3], [3, 2, 1, 0]])
def test_actual_workbook_accepts_consistent_identifier_bridge(tmp_path, order):
    sheets = bridge_sheets(conflicting=False)
    path = write_workbook(tmp_path / "consistent.xlsx", [sheets[index] for index in order])
    processor = FileProcessor()
    frame, truncated = processor._read_file_ex(path, ".xlsx")
    assert not truncated
    assert frame.height == 3 and frame["amount"].sum() == 60
    assert frame["name"].to_list() == ["e1", "e2", "e3"]
    assert processor._parser_metadata(path, ".xlsx")["relationship_resolution"]["status"] == "enriched"


def test_actual_workbook_keeps_lookup_reached_through_another_lookup(tmp_path):
    path = write_workbook(tmp_path / "chain.xlsx", [
        ("Items", {"item_id": ["I1", "I2", "I3"], "order_id": ["O1", "O1", "O2"], "amount": [10, 20, 30]}),
        ("Orders", {"order_id": ["O1", "O2"], "customer_id": ["C1", "C2"]}),
        ("Customers", {"customer_id": ["C1", "C2"], "region": ["North", "South"]}),
    ])
    processor = FileProcessor()
    frame = processor._read_file(path, ".xlsx")
    assert frame.height == 3 and frame["amount"].sum() == 60
    assert frame["region"].to_list() == ["North", "North", "South"]
    parser = processor._parser_metadata(path, ".xlsx")
    assert parser["included_sheets"] == ["Items", "Orders", "Customers"]
    assert parser["excluded_sheets"] == []


def test_actual_workbook_rejects_heterogeneous_sheets_that_would_be_stacked(tmp_path):
    path = write_workbook(tmp_path / "many_to_many.xlsx", [
        ("Sales", {"customer_id": ["C1", "C1", "C2"], "amount": [10, 20, 30]}),
        ("Contacts", {"customer_id": ["C1", "C1", "C2"], "channel": ["Email", "Phone", "Email"]}),
    ])
    with pytest.raises(ValueError, match="different types of records"):
        FileProcessor()._read_file(path, ".xlsx")


def test_actual_workbook_cleaning_refuses_unsafe_sheets_before_writing_derived_files(tmp_path):
    path = write_workbook(tmp_path / "unsafe.xlsx", bridge_sheets(conflicting=True))
    parquet, csv = tmp_path / "clean.parquet", tmp_path / "clean.csv"
    with pytest.raises(ValueError, match="IDs disagree"):
        FileProcessor()._clean_file_sync(path, ".xlsx", str(parquet), str(csv), {})
    assert not parquet.exists() and not csv.exists()


def test_actual_workbook_appends_same_schema_periods(tmp_path):
    path = write_workbook(tmp_path / "periods.xlsx", [
        ("January", {"product_id": ["P1", "P2"], "amount": [10, 20]}),
        ("February", {"product_id": ["P1"], "amount": [30]}),
    ])
    processor = FileProcessor()
    frame = processor._read_file(path, ".xlsx")
    assert frame.height == 3 and frame["amount"].sum() == 60
    assert frame["Sheet"].to_list() == ["January", "January", "February"]
    assert processor._parser_metadata(path, ".xlsx")["relationship_resolution"]["status"] == "stacked"


def test_actual_workbook_aligns_distinct_measures_by_unique_shared_dimension(tmp_path):
    path = write_workbook(tmp_path / "unique.xlsx", [
        ("Sales", {"Organisation": ["Acme", "Beta"], "sales": [10, 20]}),
        ("Costs", {"Organisation": ["Acme", "Gamma"], "cost": [3, 4]}),
    ])
    processor = FileProcessor()
    frame = processor._read_file(path, ".xlsx")
    assert frame.height == 3
    assert frame["sales"].sum() == 30 and frame["cost"].sum() == 7
    assert processor._parser_metadata(path, ".xlsx")["relationship_resolution"]["status"] == "aligned"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("conflicting", [False, True])
def test_actual_workbook_checks_multiple_unique_ids_before_legacy_alignment(tmp_path, reverse, conflicting):
    sheets = [
        ("Facts", {"employee_id": [" U1", "U2", "U3"], "department_code": ["A", "B", "C"],
                   "amount": [10, 20, 30]}),
        ("Employees", {"employee_id": ["U1", "U2", "U3"],
                       "department_code": ["B", "C", "A"] if conflicting else ["A", "B", "C"],
                       "cost": [1, 2, 3]}),
    ]
    path = write_workbook(tmp_path / "unique_ids.xlsx", list(reversed(sheets)) if reverse else sheets)
    processor = FileProcessor()
    if conflicting:
        with pytest.raises(ValueError, match="IDs disagree"):
            processor._read_file(path, ".xlsx")
    else:
        frame = processor._read_file(path, ".xlsx")
        assert frame.height == 3 and frame["amount"].sum() == 60 and frame["cost"].sum() == 6
        assert processor._parser_metadata(path, ".xlsx")["relationship_resolution"]["status"] == "aligned"


def test_actual_workbook_primary_fallback_preserves_facts_and_audits_excluded_support(tmp_path):
    path = write_workbook(tmp_path / "primary.xlsx", [
        ("Facts", {"item_id": [f"I{index}" for index in range(10)], "category": ["A"] * 10,
                   "amount": [10] * 10}),
        ("Notes", {"category": ["A", "A"], "note": ["First", "Second"]}),
    ])
    processor = FileProcessor()
    frame = processor._read_file(path, ".xlsx")
    assert frame.height == 10 and frame["amount"].sum() == 100
    parser = processor._parser_metadata(path, ".xlsx")
    assert parser["included_sheets"] == ["Facts"]
    assert parser["excluded_sheets"][0]["name"] == "Notes"
    assert parser["relationship_resolution"]["status"] == "primary_only"


def test_failed_workbook_resolution_is_recorded_before_rejection():
    frames = {
        name: pl.DataFrame({f"column_{index + 1}": [column, *values]
                            for index, (column, values) in enumerate(data.items())}, strict=False)
        for name, data in bridge_sheets(conflicting=True)
    }
    report = {}
    with pytest.raises(ValueError, match="IDs disagree"):
        FileProcessor()._normalize_excel_sheets(frames, report)
    assert report["relationship_resolution"]["status"] == "unresolved"
    assert report["relationship_resolution"]["reason_code"] == "conflicting_identifiers"
