from types import SimpleNamespace
from uuid import uuid4

import duckdb
import polars as pl
import pytest

from app.analytics.live_filter import build_where_clause, populate_chart_option
from app.analytics.statistics import StatisticsEngine
from app.analytics.summary_evidence import build_summary_facts
from app.analytics.text_matching import is_unreported_category
from app.services.file_processor import FileProcessor
from app.services.investigation import ComparisonPlan, compare


@pytest.mark.parametrize(("header", "values"), [
    ("test_preparation_course", ["none", "completed", "none"]),
    ("hormone_treatment", ["None", "Yes", "None"]),
    ("country_code", ["NA", "US", "NA"]),
    ("product_code", ["NA", "001", "nil"]),
])
def test_literal_negative_answers_and_codes_survive_cleaning(header, values):
    raw = pl.DataFrame({"entry_id": ["E1", "E2", "E3"], header: values, "amount": [10, 20, 30]})
    cleaned, report = FileProcessor().clean_dataframe(raw)
    assert cleaned[header].to_list() == values
    assert cleaned[header].null_count() == 0
    assert not any(issue["column"] == header for issue in report["source_quality"]["issues"])
    assert all(not is_unreported_category(value) for value in values)


@pytest.mark.parametrize("extension", [".csv", ".json", ".parquet", ".xlsx"])
def test_literal_categories_and_actual_blanks_stay_separate_across_formats(tmp_path, extension):
    raw = pl.DataFrame({"entry_id": [f"E{index}" for index in range(6)],
                        "answer": ["none", "None", "NA", "nil", None, ""],
                        "amount": [10, 20, 30, 40, 50, 60]})
    source = tmp_path / f"source{extension}"
    if extension == ".csv":
        raw.write_csv(source)
    elif extension == ".json":
        raw.write_json(source)
    elif extension == ".parquet":
        raw.write_parquet(source)
    else:
        import pandas as pd

        pd.DataFrame(raw.to_dict(as_series=False)).to_excel(source, index=False)
    path = tmp_path / "cleaned.parquet"
    profile = FileProcessor()._clean_file_sync(str(source), extension, str(path), str(tmp_path / "cleaned.csv"), {})
    cleaned = pl.read_parquet(path)
    assert cleaned["answer"].to_list()[:4] == ["none", "None", "NA", "nil"]
    assert cleaned["answer"].null_count() == 2
    issues = profile["cleaning_report"]["source_quality"]["issues"]
    assert next(item for item in issues if item["type"] == "missing_values")["affected_rows"] == 2
    assert not any(item["type"] == "missing_value_markers" for item in issues)


def test_explicit_markers_and_failed_numeric_conversions_keep_separate_audits():
    raw = pl.DataFrame({"entry_id": [f"E{index}" for index in range(22)],
                        "amount": ["10"] * 18 + ["N/A", "none", "bad-number", None]})
    cleaned, report = FileProcessor().clean_dataframe(raw)
    assert cleaned["amount"].null_count() == 4
    issues = report["source_quality"]["issues"]
    assert next(item for item in issues if item["type"] == "missing_values")["affected_rows"] == 1
    marker = next(item for item in issues if item["type"] == "missing_value_markers")
    assert marker["markers"] == [{"value": "N/A", "count": 1}]
    invalid = next(item for item in issues if item["type"] == "invalid_numeric_values")
    assert invalid["affected_rows"] == 2
    assert {item["value"] for item in invalid["examples"]} == {"none", "bad-number"}


async def test_none_category_is_available_to_statistics_sql_filters_and_assistant(tmp_path):
    raw = pl.DataFrame({"entry_id": [f"E{index}" for index in range(7)],
                        "test_preparation_course": ["none"] * 4 + ["completed"] * 3,
                        "score": [40, 50, 60, 70, 80, 90, 100]})
    cleaned, report = FileProcessor().clean_dataframe(raw)
    path = tmp_path / "students.parquet"
    cleaned.write_parquet(path)
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM read_parquet(?)", [str(path)])
        statistics = StatisticsEngine(conn).describe_all()
        assert statistics["categorical_stats"]["test_preparation_course"]["top_values"] == [
            {"value": "none", "count": 4}, {"value": "completed", "count": 3}]
        fact = next(fact for fact in build_summary_facts(statistics, [])
                    if fact["values"].get("column") == "test_preparation_course")
        assert fact["values"]["category"] == "none" and fact["values"]["count"] == 4
        where, params = build_where_clause([{"column": "test_preparation_course", "op": "in", "values": ["none"]}])
        assert conn.execute("SELECT COUNT(*) FROM data WHERE " + where, params).fetchone()[0] == 4
    analysis = SimpleNamespace(id=uuid4(), row_count=7, file=SimpleNamespace(storage_path=str(path)),
        metadata_={**statistics, "upload_context": {"cleaning": {"report": report}}}, insights=[])
    result = await compare(analysis, ComparisonPlan(aggregation="count", filters=[{
        "column": "test_preparation_course", "op": "in", "values": ["none"]}]), resolve_categories=True)
    assert result["matched_entries"] == 4 and result["groups"][0]["value"] == 4


def test_chart_series_do_not_hide_literal_none_or_na_categories(tmp_path):
    raw = pl.DataFrame({"region": ["A"] * 6,
                        "treatment_status": ["None", "Treated", "NA", "nil", "unknown", None],
                        "amount": [10, 20, 30, 40, 50, 60]})
    cleaned, _ = FileProcessor().clean_dataframe(raw)
    path = tmp_path / "categories.parquet"
    cleaned.write_parquet(path)
    chart = {"type": "bar", "echarts_option": {"xAxis": {}, "series": [], "_columns": {
        "x": "region", "y": "amount", "series_by": "treatment_status", "aggregation": "sum"}}}
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM read_parquet(?)", [str(path)])
        assert populate_chart_option(conn, chart)
    values = {series["name"]: series["data"] for series in chart["echarts_option"]["series"]}
    assert values == {"None": [10.0], "Treated": [20.0], "NA": [30.0], "nil": [40.0]}


@pytest.mark.parametrize("value", ["N/A", "#N/A", "unknown", "NULL"])
def test_unambiguous_source_markers_remain_audited(value):
    cleaned, report = FileProcessor().clean_dataframe(pl.DataFrame({"entry_id": ["E1", "E2"], "answer": [value, "given"]}))
    assert cleaned["answer"].null_count() == 1
    assert next(item for item in report["source_quality"]["issues"] if item["type"] == "missing_value_markers")["affected_rows"] == 1
