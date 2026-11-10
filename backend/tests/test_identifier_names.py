import csv

import polars as pl
import pytest

from app.analytics.identifier_names import canonical_identifier_name
from app.analytics.kpi_detector import detect_kpis
from app.analytics.semantic_detector import enrich_schema_with_semantics
from app.services.file_processor import FileProcessor, _looks_like_identifier_column


@pytest.mark.parametrize(("left", "right", "expected"), [
    ("id_assessment", "assessment_id", "assessmentid"),
    ("id_student", "StudentID", "studentid"),
    ("code_module", "module_code", "modulecode"),
    ("code_presentation", "presentation_code", "presentationcode"),
    ("IDAssessment", "AssessmentId", "assessmentid"),
    ("idAssessment", "assessment_id", "assessmentid"),
    ("codeModule", "ModuleCode", "modulecode"),
    ("CustomerKey", "key_customer", "customerkey"),
    ("customer_UUID", "uuid_customer", "customeruuid"),
    ("CUSTOMERID", "Customer ID", "customerid"),
    ("customer_id related 3", "id_customer_2", "customerid"),
    ("id_assessment_related_2", "assessment_id_related", "assessmentid"),
])
def test_prefix_and_suffix_names_have_the_same_canonical_identity(left, right, expected):
    assert canonical_identifier_name(left) == expected
    assert canonical_identifier_name(right) == expected


@pytest.mark.parametrize("name", ["fluid", "grid", "valid", "paid", "Fluid", "GRID", "VALID", "amount", "number_of_employees", "number_of_customer_id", "customer_id_count", "id_count"])
def test_ordinary_words_and_explicit_counts_do_not_become_identifiers(name):
    assert canonical_identifier_name(name) is None


@pytest.mark.parametrize("name", ["id", "ID", "code_module", "code_presentation", "id_assessment", "id_student", "IDAssessment", "idStudent", "CodeModule", "codeModule", "CustomerID", "CUSTOMERID", "customer_key", "EmployeeNumber", "id_student_related_2"])
@pytest.mark.parametrize("values", [["001", "1", "002"], ["Ab01", "ab01", "AB02"]])
def test_import_keeps_prefix_codes_and_identifiers_as_recorded_strings(tmp_path, name, values):
    path = tmp_path / "identifiers.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([name, "amount"])
        writer.writerows(zip(values, [10, 20, 30], strict=True))
    processor = FileProcessor()
    frame = processor._read_file(str(path), ".csv")
    assert _looks_like_identifier_column(name)
    assert frame[name].dtype == pl.String
    assert frame[name].to_list() == values
    cleaned, report = processor.clean_dataframe(frame)
    cleaned_name = report["renamed_columns"].get(name, name)
    assert cleaned[cleaned_name].dtype == pl.String
    assert cleaned[cleaned_name].to_list() == values
    assert cleaned["amount"].sum() == 60


@pytest.mark.parametrize("name", ["id", "id_assessment", "id_student", "code_module", "code_presentation", "module_key", "id_date"])
def test_prefix_identifiers_are_excluded_from_numeric_kpis(name):
    numeric = {name: {"min": 1, "max": 3, "count": 5, "unique_count": 3, "total": 9, "mean": 1.8}}
    schema = enrich_schema_with_semantics([{"name": name, "dtype": "BIGINT", "is_numeric": True}], numeric, {})
    assert schema[0]["analysis_role"] == "identifier"
    assert not detect_kpis(schema, numeric)


def test_quantity_and_bounded_categorical_codes_retain_their_roles():
    numeric = {name: {"min": 1, "max": 3, "count": 100, "unique_count": 3, "mean": 2}
               for name in ("number_of_employees", "number_of_customer_id", "number_of_dates", "id_count", "click_code")}
    schema = enrich_schema_with_semantics([{"name": name, "dtype": "BIGINT", "is_numeric": True}
                                          for name in numeric], numeric, {})
    roles = {field["name"]: field["analysis_role"] for field in schema}
    assert roles == {"number_of_employees": "metric", "number_of_customer_id": "metric",
                     "number_of_dates": "metric", "id_count": "metric", "click_code": "dimension"}


def test_numeric_source_warnings_still_apply_to_counts_and_ids_keep_label_roles():
    numeric = {name: {"aggregation_warning": {"description": "Negative elapsed-time codes need source definitions."}}
               for name in ("number_of_days", "id_duration")}
    schema = enrich_schema_with_semantics([{"name": name, "dtype": "BIGINT", "is_numeric": True}
                                          for name in numeric], numeric, {})
    roles = {field["name"]: field["analysis_role"] for field in schema}
    assert roles == {"number_of_days": "unresolved", "id_duration": "identifier"}
