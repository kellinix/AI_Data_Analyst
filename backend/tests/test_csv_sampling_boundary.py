import csv

import polars as pl
import pytest

from app.services.file_processor import FileProcessor


@pytest.mark.parametrize("row_count", [2, 3, 4, 30])
def test_csv_limit_counts_data_entries_after_the_header(tmp_path, row_count):
    path = tmp_path / "amounts.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item_id", "amount"])
        writer.writerows((f"I{index}", index * 10) for index in range(1, row_count + 1))
    processor = FileProcessor()
    processor.SAMPLE_ROWS = 3
    frame, truncated = processor._read_file_ex(str(path), ".csv")
    assert frame.height == min(row_count, 3)
    assert frame["item_id"].to_list() == [f"I{index}" for index in range(1, min(row_count, 3) + 1)]
    assert frame["amount"].sum() == sum(index * 10 for index in range(1, min(row_count, 3) + 1))
    assert truncated is (row_count > 3)


@pytest.mark.parametrize("data_rows", [3, 4])
def test_header_at_the_last_scanned_row_does_not_reduce_the_data_limit(tmp_path, data_rows):
    path = tmp_path / "titled.csv"
    processor = FileProcessor()
    processor.SAMPLE_ROWS = 3
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows([[f"Report line {index}"] for index in range(processor.HEADER_SCAN_ROWS - 1)])
        writer.writerow(["item_id", "amount"])
        writer.writerows((f"I{index}", index * 10) for index in range(1, data_rows + 1))
    frame, truncated = processor._read_file_ex(str(path), ".csv")
    assert frame.height == 3
    assert frame["item_id"].to_list() == ["I1", "I2", "I3"]
    assert truncated is (data_rows > 3)


def test_quoted_newlines_and_blank_lines_do_not_use_up_the_data_limit(tmp_path):
    path = tmp_path / "quoted.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item_id", "description", "amount"])
        for index in range(1, 4):
            writer.writerow([])
            writer.writerow([f"I{index}", "First line\nSecond line", index * 10])
    processor = FileProcessor()
    processor.SAMPLE_ROWS = 3
    frame, truncated = processor._read_file_ex(str(path), ".csv")
    assert frame.height == 3 and frame["amount"].sum() == 60
    assert frame["description"].to_list() == ["First line\nSecond line"] * 3
    assert not truncated


def test_empty_delimited_records_do_not_hide_later_data_or_truncation(tmp_path):
    path = tmp_path / "empty_records.csv"
    path.write_text("item_id,amount\nI1,10\n" + ",\n" * 40 + "I2,20\nI3,30\nI4,40\n")
    processor = FileProcessor()
    processor.SAMPLE_ROWS = 3
    frame, truncated = processor._read_file_ex(str(path), ".csv")
    assert frame["item_id"].to_list() == ["I1", "I2", "I3"]
    assert frame["amount"].sum() == 60
    assert truncated


@pytest.mark.parametrize(("header", "cleaned_header"), [
    ("product_key", "product_key"), ("CustomerKey", "customer_key"),
    ("DonorID", "donor_id"), ("customer_id", "customer_id"),
    ("CustomerCode", "customer_code"), ("customer_code", "customer_code"),
    ("Flight #", "flight_id"), ("Invoice#", "invoice_id"),
])
def test_numeric_looking_identifier_strings_survive_import_and_cleaning(tmp_path, header, cleaned_header):
    path = tmp_path / "identifiers.csv"
    path.write_text(f"{header},amount\n001,10\n1,20\n002,30\n")
    processor = FileProcessor()
    frame, truncated = processor._read_file_ex(str(path), ".csv")
    assert not truncated and frame[header].dtype == pl.String
    assert frame[header].to_list() == ["001", "1", "002"]
    cleaned, _ = processor.clean_dataframe(frame)
    assert cleaned[cleaned_header].dtype == pl.String
    assert cleaned[cleaned_header].to_list() == ["001", "1", "002"]
    assert cleaned["amount"].sum() == 60


def test_amount_headers_that_end_in_lowercase_id_are_still_numeric(tmp_path):
    path = tmp_path / "measure.csv"
    path.write_text("item_id,paid,fluid\nI1,10,2\nI2,20,3\n")
    frame = FileProcessor()._read_file(str(path), ".csv")
    assert frame["paid"].sum() == 30 and frame["fluid"].sum() == 5


def test_related_and_disambiguated_identifier_columns_keep_their_codes():
    frame = pl.DataFrame({"Customer ID": ["001", "1"], "customer_id": ["004", "4"],
                          "external_id related 3": ["009", "9"], "amount": [10, 20]})
    cleaned, _ = FileProcessor().clean_dataframe(frame)
    assert cleaned["customer_id"].to_list() == ["001", "1"]
    assert cleaned["customer_id_2"].to_list() == ["004", "4"]
    assert cleaned["external_id_related_3"].to_list() == ["009", "9"]
    assert cleaned["amount"].sum() == 30


def test_number_sign_prefix_is_a_quantity_rather_than_an_identifier(tmp_path):
    path = tmp_path / "quantities.csv"
    path.write_text("item_id,# of items\nI1,10\nI2,20\n")
    processor = FileProcessor()
    frame = processor._read_file(str(path), ".csv")
    assert frame["# of items"].sum() == 30
    cleaned, _ = processor.clean_dataframe(frame)
    assert cleaned["of_items"].sum() == 30
