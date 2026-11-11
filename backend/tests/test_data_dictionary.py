from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import duckdb
import polars as pl
import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from pydantic import ValidationError
from starlette.requests import Request

from app.analytics.chart_selector import _horizontal_bar_chart
from app.analytics.data_dictionary import (
    apply_data_dictionary,
    value_aliases,
    value_definition,
    value_display_label,
    value_label,
)
from app.analytics.labels import reader_label, source_column_label
from app.analytics.live_filter import (
    FilterValidationError,
    build_where_clause,
    populate_chart_option,
    requery_chart,
    validate_filters,
)
from app.analytics.measure_grain import annotate_measure_grain
from app.analytics.statistics import StatisticsEngine
from app.api.v1.endpoints import analyses
from app.api.v1.endpoints.analyses import (
    _derive_filterable_columns,
    _dictionary_upload_context,
    _require_analysis_dictionary,
    _require_data_dictionary,
)
from app.core.config import settings
from app.schemas.analysis import CreateAnalysisRequest, CreateCombinedAnalysisRequest
from app.schemas.data_dictionary import DataDictionary
from app.services import analysis_engine, semantic_wrangler
from app.services.file_processor import FileProcessor
from app.services.investigation import ComparisonPlan, compare
from app.services.semantic_wrangler import SemanticWrangler, apply_display_metadata_to_statistics


def guide(*fields):
    return {"data_dictionary": {"version": 1, "fields": list(fields)}}


def definition(column="MaritalStatus", **extra):
    return {"source_table": "customers.csv", "source_column": column,
            "label": "Marital status", "description": "Whether the customer is married or single.",
            "values": [{"value": "M", "label": "Married"}, {"value": "S", "label": "Single"}],
            "source": {"title": "The source's field guide", "url": "https://example.test/guide"}, **extra}


def source_field(name="MaritalStatus", **extra):
    return {"name": name, "dtype": "VARCHAR", "is_numeric": False, "is_date": False,
            "analysis_role": "dimension", "measure_grain": {
                "source_table": "customers.csv", "source_column": name, "kind": "fact"}, **extra}


@pytest.mark.parametrize("request_type", [CreateAnalysisRequest, CreateCombinedAnalysisRequest])
def test_normal_analysis_requests_validate_and_preserve_the_guide(request_type):
    inputs = {"file_id": uuid.uuid4()} if request_type is CreateAnalysisRequest else {"file_ids": [uuid.uuid4(), uuid.uuid4()]}
    request = request_type(**inputs, relationship_context=guide(definition()))
    assert request.relationship_context["data_dictionary"]["fields"][0]["values"][0]["value"] == "M"
    assert request.relationship_context["data_dictionary"]["fields"][0]["source"]["url"] == "https://example.test/guide"


@pytest.mark.parametrize("change", [
    {"source_table": "folder/customers.csv"}, {"source_table": "folder\\customers.csv"},
    {"label": " "}, {"description": " "}, {"label": "x" * 81},
    {"description": "x" * 1001}, {"source_column": "x" * 513},
    {"source": {"url": "javascript:alert(1)"}},
    {"source": {"url": "https://login:secret@example.test/guide"}},
    {"source": {"sha256": "invalid"}}, {"status": "externally_verified"},
    {"values": [{"value": ["M"], "label": "Married"}]},
    {"values": [{"value": "x" * 257, "label": "Long code"}]},
    {"values": [{"value": float("nan"), "label": "Nonfinite"}]},
    {"time_basis": {"kind": "relative_day", "origin": "start", "calendar_origin": "2025-01-01"}},
])
def test_invalid_or_forged_dictionary_input_is_rejected(change):
    with pytest.raises(ValidationError):
        DataDictionary.model_validate(guide(definition(**change))["data_dictionary"])


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_dictionary_version_is_the_integer_one(version):
    with pytest.raises(ValidationError):
        DataDictionary.model_validate({"version": version, "fields": [definition()]})


@pytest.mark.parametrize("fields", [[], [definition()] * 201])
def test_dictionary_field_count_is_bounded(fields):
    with pytest.raises(ValidationError):
        DataDictionary.model_validate({"version": 1, "fields": fields})


def test_dictionary_document_and_category_counts_are_bounded():
    with pytest.raises(ValidationError, match="1 MiB"):
        DataDictionary.model_validate({"version": 1, "fields": [definition(description="x" * 1_048_576)]})
    with pytest.raises(ValidationError):
        DataDictionary.model_validate(guide(definition(values=[{"value": n, "label": str(n)} for n in range(501)]))["data_dictionary"])


def test_same_code_in_different_fields_has_separate_meanings_and_unknown_stays_unknown():
    fields = [source_field(), source_field("Gender"), source_field("ProductSize")]
    result = apply_data_dictionary(fields, guide(definition(), definition("Gender", label="Recorded gender",
        values=[{"value": "M", "label": "Male"}, {"value": "F", "label": "Female"}])))
    assert value_label(result[0], "M") == "Married"
    assert value_label(result[1], "M") == "Male"
    assert value_label(result[1], "NA") is None
    assert value_label(result[2], "M") is None
    assert "data_definition" not in fields[0]
    assert result[0]["data_definition"]["provenance"] == "owner_supplied"
    assert "verified" not in json.dumps(result[0]["data_definition"])


def test_cleaning_renames_bind_the_exact_original_column():
    field = source_field("marital_status", measure_grain={})
    context = {**guide(definition("Marital Status")), "cleaning": {
        "source_filename": "customers.csv", "report": {"renamed_columns": {"Marital Status": "marital_status"}}}}
    bound = apply_data_dictionary([field], context, file_name="customers cleaned.parquet")[0]
    assert bound["data_definition"]["source_column"] == "Marital Status"
    assert bound["name"] == "marital_status"


def test_column_and_file_matching_is_exact():
    with pytest.raises(ValueError, match="does not match"):
        apply_data_dictionary([source_field()], guide(definition("maritalstatus")))
    with pytest.raises(ValueError, match="does not match"):
        apply_data_dictionary([source_field()], guide(definition(source_table="Customers.csv")))


def test_same_physical_guide_can_apply_to_both_lookup_roles():
    fields = [source_field("DST_" + role, measure_grain={"source_table": "airports.csv", "source_column": "DST", "source_role": role})
              for role in ("source_airport", "destination_airport")]
    context = guide(definition("DST", source_table="airports.csv", label="Daylight-saving rule",
        values=[{"value": "E", "label": "Europe rules"}]))
    bound = apply_data_dictionary(fields, context)
    assert [value_label(field, "E") for field in bound] == ["Europe rules", "Europe rules"]
    assert [field["data_definition"]["source_role"] for field in bound] == ["source_airport", "destination_airport"]
    context["data_dictionary"]["fields"][0]["source_role"] = "destination_airport"
    scoped = apply_data_dictionary(fields, context)
    assert "data_definition" not in scoped[0]
    assert value_label(scoped[1], "E") == "Europe rules"


def test_workbook_requires_an_unambiguous_sheet_scope():
    fields = [source_field(sheet, measure_grain={"source_table": sheet, "source_column": "M", "source_file": "book.xlsx", "source_sheet": sheet})
              for sheet in ("People", "Products")]
    entry = definition("M", source_table="book.xlsx")
    with pytest.raises(ValueError, match="ambiguous"):
        apply_data_dictionary(fields, guide(entry))
    bound = apply_data_dictionary(fields, guide({**entry, "source_sheet": "People"}))
    assert "data_definition" in bound[0] and "data_definition" not in bound[1]
    flat = apply_data_dictionary([source_field("M", measure_grain={})], guide({**entry, "source_sheet": "People"}),
                                file_name="book.xlsx", parser={"included_sheets": ["People"]})
    assert flat[0]["data_definition"]["source_sheet"] == "People"


def test_duplicate_names_partial_sources_and_overlapping_definitions_are_rejected():
    duplicate = {**guide(definition()), "source_files": [{"name": "customers.csv", "id": "1"}, {"name": "customers.csv", "id": "2"}]}
    with pytest.raises(ValueError, match="more than one upload"):
        apply_data_dictionary([source_field()], duplicate)
    field = source_field(measure_grain={"source_origins": [{"source_table": "customers.csv", "source_column": "MaritalStatus"},
                                                         {"source_table": "other.csv", "source_column": "MaritalStatus"}]})
    with pytest.raises(ValueError, match="only part"):
        apply_data_dictionary([field], guide(definition()))
    with pytest.raises(ValueError, match="More than one guide entry"):
        apply_data_dictionary([source_field()], guide(definition(), definition(label="Another meaning")))


@pytest.mark.parametrize("values", [
    [{"value": "M", "label": "Married"}, {"value": "M", "label": "Male"}],
    [{"value": "M", "label": "Same meaning"}, {"value": "S", "label": " SAME MEANING "}],
])
def test_conflicting_code_and_label_aliases_are_rejected(values):
    with pytest.raises(ValueError, match="guide"):
        apply_data_dictionary([source_field()], guide(definition(values=values)))


def test_numeric_zero_and_string_identifiers_use_their_existing_value_semantics():
    numeric = apply_data_dictionary([source_field(is_numeric=True)], guide(definition(values=[{"value": "0", "label": "Not transferred"}])))[0]
    assert value_label(numeric, 0.0) == "Not transferred"
    assert value_aliases(numeric, " NOT TRANSFERRED ") == ["0"]
    identifier = apply_data_dictionary([source_field()], guide(definition(values=[{"value": "001", "label": "First"}, {"value": "1", "label": "Second"}])))[0]
    assert value_label(identifier, "001") == "First"
    assert value_label(identifier, "1") == "Second"
    assert value_label(identifier, "m") is None
    assert value_label(identifier, " 001") is None


@pytest.mark.parametrize("raw, label, expected", [
    ("M", "Married", "Married (M)"), (0, "No", "No (0)"),
    (True, "Yes", "Yes (true)"), (None, "Missing", "Missing (null)"),
    ("", "Empty code", 'Empty code ("")'), ("M", "M", "M"),
])
def test_display_label_keeps_the_original_guide_code(raw, label, expected):
    field = apply_data_dictionary([source_field()], guide(definition(values=[{"value": raw, "label": label}])))[0]
    assert value_display_label(field, raw) == expected
    assert value_display_label(field, "unmapped") is None


def test_large_numeric_codes_are_compared_without_decimal_rounding():
    values = [{"value": value, "label": label} for value, label in [
        ("12345678901234567890123456789012345671", "First"), ("12345678901234567890123456789012345672", "Second")]]
    field = apply_data_dictionary([source_field(is_numeric=True)], guide(definition(values=values)))[0]
    assert value_label(field, 12345678901234567890123456789012345671) == "First"
    assert value_label(field, 12345678901234567890123456789012345672) == "Second"


def test_guide_codes_are_typed_and_case_exact_even_for_geographic_fields():
    field = source_field("country")
    bound = apply_data_dictionary([field], guide(definition("country", values=[{"value": "United-States", "label": "US market"}])))[0]
    assert value_label(bound, "United-States") == "US market"
    assert value_label(bound, "united states") is None
    typed = apply_data_dictionary([field], guide(definition("country", values=[{"value": 1, "label": "Numeric code"}, {"value": "1", "label": "Text code"}])))[0]
    assert value_label(typed, 1) == "Numeric code"
    assert value_label(typed, "1") == "Text code"
    with pytest.raises(ValueError, match="same recorded code"):
        apply_data_dictionary([source_field(is_numeric=True)], guide(definition(values=[{"value": 1, "label": "A"}, {"value": "1", "label": "B"}])))


def test_relative_days_are_numeric_attributes_with_an_explicit_origin():
    field = source_field("date", is_numeric=True, is_date=True, analysis_role="temporal_dimension")
    bound = apply_data_dictionary([field], guide(definition("date", values=[], time_basis={"kind": "relative_day", "origin": "the course presentation start"})))[0]
    assert bound["is_numeric"] and not bound["is_date"]
    assert bound["analysis_role"] == "attribute" and bound["semantic_type"] == "relative_day"
    assert "Day 0" in bound["display_description"]
    assert "calendar_origin" not in bound["data_definition"]["time_basis"]
    with pytest.raises(ValueError, match="numeric source field"):
        apply_data_dictionary([source_field("date")], guide(definition("date", time_basis={"kind": "relative_day", "origin": "start"})))


@pytest.mark.parametrize("display_mode", ["disabled", "failed", "conflicting"])
async def test_provided_definitions_win_display_ai_and_saved_labels(monkeypatch, display_mode):
    bound = apply_data_dictionary([source_field(display_label="Profit", display_description="Wrong meaning")], guide(definition()))
    stats = {"schema": bound}
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", display_mode != "disabled")
    completion = AsyncMock()
    if display_mode == "failed":
        completion.side_effect = RuntimeError("unavailable")
    else:
        completion.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "columns": [{"name": "MaritalStatus", "label": "Invented income", "description": "Wrong interpretation"}]})))])
    monkeypatch.setattr(semantic_wrangler.client.chat.completions, "create", completion)
    display = await SemanticWrangler().build_display_metadata(file_name="customers.csv", statistics=stats, charts=[], upload_context={})
    shown = apply_display_metadata_to_statistics(stats, display)["schema"][0]
    assert shown["display_label"] == "Marital status"
    assert shown["display_description"] == "Whether the customer is married or single."
    assert source_column_label(shown) == "Marital status"
    assert value_label(shown, "M") == "Married"
    assert apply_data_dictionary([shown], guide(definition())) == [shown]


def test_route_prevalidation_rejects_a_bad_scope_before_queueing():
    columns = [{"name": "MaritalStatus", "dtype": "String"}]
    _require_data_dictionary(columns, guide(definition()), file_name="customers.csv")
    with pytest.raises(HTTPException) as error:
        _require_data_dictionary(columns, guide(definition()), file_name="products.csv")
    assert error.value.status_code == 422
    assert "original source field" in error.value.detail


def test_request_cannot_forge_an_original_source_or_cleaning_record_for_guide_binding():
    supplied = {**guide(definition(source_table="forged.csv")),
                "relationship_resolution": {"field_origins": {"MaritalStatus": {
                    "source_table": "forged.csv", "source_column": "MaritalStatus"}}},
                "cleaning": {"source_filename": "forged.csv"},
                "source_files": [{"name": "forged.csv"}]}
    actual = SimpleNamespace(id="actual-id", original_filename="customers.csv", row_count=2, column_count=1)
    context = _dictionary_upload_context(supplied, [actual])
    assert "relationship_resolution" not in context and "cleaning" not in context
    assert context["source_files"][0]["name"] == "customers.csv"
    with pytest.raises(HTTPException, match="does not match"):
        _require_data_dictionary([{"name": "MaritalStatus", "dtype": "String"}], context, file_name="customers.csv")


async def test_cleaned_source_prevalidation_uses_original_names_and_leaves_source_unchanged(tmp_path):
    original = tmp_path / "customers.csv"
    original.write_text("Entry ID,Marital Status,Amount\nA,M,2\nB,S,3\n", encoding="utf-8")
    before = original.read_bytes()
    output, export = tmp_path / "cleaned.parquet", tmp_path / "cleaned.csv"
    processor = FileProcessor()
    profile = await processor.clean_file(str(original), ".csv", str(output), str(export), {"standardize_columns": True})
    cleaning = {"source_filename": original.name, "report": profile["cleaning_report"],
                "cleaned_parquet_path": str(output), "cleaned_csv_path": str(export)}
    file = SimpleNamespace(columns=profile["columns"], original_filename="customers cleaned.parquet", storage_path=str(output))
    _require_analysis_dictionary(file, guide(definition("Marital Status")), cleaning, processor)
    assert original.read_bytes() == before
    assert pl.read_parquet(output)["amount"].sum() == 5
    with pytest.raises(HTTPException, match="does not match"):
        _require_analysis_dictionary(file, guide(definition("Unrelated field")), cleaning, processor)
    assert not output.exists() and not export.exists() and original.read_bytes() == before


def test_actual_workbook_dictionary_matches_physical_file_and_original_sheet(tmp_path):
    path = tmp_path / "customers.xlsx"
    workbook = Workbook()
    entries = workbook.active
    entries.title = "Entries"
    entries.append(["entry_id", "customer_id", "amount"])
    for row in [("E1", "C1", 2), ("E2", "C1", 3), ("E3", "C2", 4)]:
        entries.append(row)
    customers = workbook.create_sheet("Customers")
    customers.append(["customer_id", "Marital Status"])
    customers.append(["C1", "M"])
    customers.append(["C2", "S"])
    workbook.save(path)
    before = path.read_bytes()
    processor = FileProcessor()
    frame, _ = processor._read_file_ex(str(path), ".xlsx")
    parser = processor._parser_metadata(str(path), ".xlsx")
    schema = annotate_measure_grain([{"name": name, "is_numeric": frame[name].dtype.is_numeric()} for name in frame.columns], {}, parser)
    context = guide(definition("Marital Status", source_table=path.name, source_sheet="Customers"))
    fields = apply_data_dictionary(schema, context, file_name=path.name, parser=parser)
    field = next(field for field in fields if field.get("data_definition"))
    assert field["data_definition"]["source_sheet"] == "Customers"
    assert [value_label(field, value) for value in frame[field["name"]].to_list()] == ["Married", "Married", "Single"]
    assert frame.height == 3 and frame["amount"].sum() == 9
    assert path.read_bytes() == before


async def test_normal_pipeline_keeps_offsets_and_figures_unchanged(tmp_path, monkeypatch):
    source = tmp_path / "records.csv"
    source.write_text("id,date_submitted,score\nA,-30,40\nB,0,60\nC,15,80\n", encoding="utf-8")
    original = source.read_bytes()
    context = guide(definition("date_submitted", source_table=source.name, label="Submission day", values=[],
                               description="Day of submission.", time_basis={"kind": "relative_day", "origin": "course start"}))
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", False)
    ai = AsyncMock()
    ai.generate_analysis.return_value = {"executive_summary": "", "insights": [], "recommendation_ids": [], "summary_fact_ids": []}
    result = await analysis_engine.compute_analysis(file_processor=FileProcessor(), ai_service=ai, storage_path=str(source),
        file_name=source.name, analysis_id="guided", upload_context=context)
    field = next(field for field in result["statistics"]["schema"] if field["name"] == "date_submitted")
    assert field["analysis_role"] == "attribute" and not field["is_date"]
    assert result["statistics"]["numeric_stats"]["date_submitted"]["min"] == -30
    assert result["statistics"]["numeric_stats"]["score"]["total"] == 180
    assert result["forecasts"] == []
    assert all(kpi.get("column") != "date_submitted" for kpi in result["kpis"])
    assert source.read_bytes() == original


def test_combined_two_role_source_guide_preserves_source_rows_and_joined_values(tmp_path):
    routes = tmp_path / "routes.csv"
    routes.write_text("route_id,source_airport_id,destination_airport_id,quantity\nR1,A1,A2,5\nR2,A2,A1,7\n", encoding="utf-8")
    airports = tmp_path / "airports.csv"
    airports.write_text("airport_id,DST\nA1,E\nA2,N\n", encoding="utf-8")
    source_bytes = [routes.read_bytes(), airports.read_bytes()]
    files = [SimpleNamespace(id=path.stem, original_filename=path.name, storage_path=str(path)) for path in [routes, airports]]
    context = {"fact_file": "routes", "declared_relationships": [
        {"from_file": "routes", "from_columns": [column], "to_file": "airports", "to_columns": ["airport_id"]}
        for column in ["source_airport_id", "destination_airport_id"]],
        **guide(definition("DST", source_table="airports.csv", label="Daylight-saving rule", values=[{"value": "E", "label": "Europe rules"}, {"value": "N", "label": "No daylight saving"}]))}
    original_context = copy.deepcopy(context)
    processor = FileProcessor()
    output = tmp_path / "combined.parquet"
    processor._combine_uploaded_files_sync(files, str(output), context)
    frame = pl.read_parquet(output)
    schema = annotate_measure_grain([{"name": name, "is_numeric": frame[name].dtype.is_numeric()} for name in frame.columns], context)
    bound = apply_data_dictionary(schema, context)
    defined = [field for field in bound if field.get("data_definition")]
    assert len(defined) == 2
    assert frame.height == 2 and frame["quantity"].sum() == 12
    assert source_bytes == [routes.read_bytes(), airports.read_bytes()]
    assert context["data_dictionary"] == original_context["data_dictionary"]
    assert {field["data_definition"]["source_role"] for field in defined} == {"source_airport", "destination_airport"}
    assert all(value_definition(field, "E")["label"] == "Europe rules" for field in defined)


async def test_guided_read_clean_statistics_charts_and_comparison_keep_unknown_codes(tmp_path, monkeypatch):
    source = tmp_path / "codes.csv"
    source.write_text("id,Active,country,code,date_submitted,amount\nA,N,US,001,-30,10\nB,n,us,1,0,20\nC,NA,NA,002,15,30\n", encoding="utf-8")
    original = source.read_bytes()
    context = guide(
        definition("Active", source_table=source.name, label="Operating status", values=[{"value": "N", "label": "No"}]),
        definition("country", source_table=source.name, label="Market code", values=[{"value": "US", "label": "First market"}, {"value": "us", "label": "Second market"}, {"value": "NA", "label": "Unallocated market"}]),
        definition("code", source_table=source.name, label="Product code", values=[{"value": "001", "label": "First product"}, {"value": "1", "label": "Second product"}, {"value": "002", "label": "Third product"}]),
        definition("date_submitted", source_table=source.name, label="Submission day", values=[], time_basis={"kind": "relative_day", "origin": "course start"}),
    )
    processor = FileProcessor(data_dictionary_context=context, source_name=source.name)
    frame = processor._read_file(str(source), ".csv")
    assert frame["code"].to_list() == ["001", "1", "002"]
    assert frame["Active"].to_list() == ["N", "n", "NA"]
    output, export = tmp_path / "cleaned.parquet", tmp_path / "cleaned.csv"
    profile = await processor.clean_file(str(source), ".csv", str(output), str(export),
        {"standardize_columns": True, "clean_text": True, "normalize_dates": True, "parse_currency_percent": True,
         "missing_data_strategy": "smart", "fuzzy_deduplicate": True, "outlier_policy": "cap"})
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", True)
    monkeypatch.setattr(settings, "semantic_wrangling_use_embeddings", False)
    await SemanticWrangler().canonicalize_cleaned_file(parquet_path=str(output), csv_path=str(export), profile=profile)
    cleaned = pl.read_parquet(output)
    assert cleaned["active"].to_list() == ["N", "n", "NA"]
    assert cleaned["country"].to_list() == ["US", "us", "NA"]
    assert cleaned["code"].to_list() == ["001", "1", "002"]
    assert cleaned["date_submitted"].to_list() == [-30, 0, 15]
    context["cleaning"] = {"source_filename": source.name, "report": profile["cleaning_report"]}
    with duckdb.connect(":memory:") as connection:
        await processor.read_to_duckdb_ex(connection, str(output), ".parquet")
        stats = StatisticsEngine(connection, upload_context=context, file_name="codes cleaned.parquet").describe_all()
        fields = {field["name"]: field for field in stats["schema"]}
        assert stats["categorical_stats"]["country"]["unique_count"] == 3
        assert value_label(fields["active"], "n") is None
        assert value_label(fields["active"], "NA") is None
        assert value_label(fields["country"], "NA") == "Unallocated market"
        chart = _horizontal_bar_chart("country", "amount", aggregation="sum")
        assert populate_chart_option(connection, chart, schema=stats["schema"])
        assert set(chart["echarts_option"]["yAxis"]["data"]) == {"US", "us", "NA"}
        where, parameters = build_where_clause([{"column": "country", "op": "in", "values": ["us"]}], stats["schema"])
        assert connection.execute("SELECT SUM(amount) FROM data WHERE " + where, parameters).fetchone()[0] == 20
        filtered = requery_chart(connection, chart, where, parameters, stats["schema"])
        assert filtered["echarts_option"]["yAxis"]["data"] == ["us"]
        assert stats["numeric_stats"]["amount"]["total"] == 60
    analysis = SimpleNamespace(id=uuid.uuid4(), row_count=3, file=SimpleNamespace(storage_path=str(output), original_filename="codes cleaned.parquet"),
                               metadata_={**stats, "upload_context": context})
    result = await compare(analysis, ComparisonPlan(aggregation="sum", column="amount", filters=[{"column": "country", "op": "in", "values": ["Second market"]}]), resolve_categories=True)
    assert result["groups"][0]["value"] == 20
    lower = await compare(analysis, ComparisonPlan(aggregation="count", filters=[{"column": "active", "op": "in", "values": ["n"]}]), resolve_categories=True)
    assert lower["groups"][0]["value"] == 1
    assert source.read_bytes() == original


@pytest.mark.parametrize("kind", [pl.Int64, pl.Float64])
def test_coded_numeric_filters_use_numeric_equality_and_text_codes_require_text(kind):
    numeric = apply_data_dictionary([source_field("country", is_numeric=True, dtype="DOUBLE")], guide(definition("country", values=[{"value": 1, "label": "First"}, {"value": 2, "label": "Second"}])))[0]
    frame = pl.DataFrame({"country": pl.Series([1, 1, 2], dtype=kind)})
    with duckdb.connect(":memory:") as connection:
        connection.register("data", frame)
        filters = [{"column": "country", "op": "in", "values": ["1"]}]
        validate_filters(filters, [numeric])
        where, parameters = build_where_clause(filters, [numeric])
        assert connection.execute("SELECT COUNT(*) FROM data WHERE " + where, parameters).fetchone()[0] == 2
    text = apply_data_dictionary([source_field()], guide(definition(values=[{"value": "1", "label": "First"}])))[0]
    with pytest.raises(FilterValidationError, match="exact text"):
        validate_filters([{"column": "MaritalStatus", "op": "in", "values": [1]}], [text])
    with pytest.raises(FilterValidationError, match="exact text"):
        build_where_clause([{"column": "MaritalStatus", "op": "in", "values": [1]}], [text])


def test_numeric_flags_stay_numeric_and_ordinary_geography_keeps_existing_rules(tmp_path):
    source = tmp_path / "flags.csv"
    source.write_text("flag,country\n0,US\n1,us\n0,NA\n", encoding="utf-8")
    context = guide(definition("flag", source_table=source.name, values=[{"value": 0, "label": "No"}, {"value": 1, "label": "Yes"}]))
    frame = FileProcessor(data_dictionary_context=context, source_name=source.name)._read_file(str(source), ".csv")
    assert frame["flag"].dtype.is_numeric() and frame["flag"].sum() == 1
    with duckdb.connect(":memory:") as connection:
        connection.register("data", frame)
        plain = StatisticsEngine(connection).describe_all()
        assert plain["categorical_stats"]["country"]["unique_count"] == 2


def test_literal_numeric_codes_are_protected_before_reader_type_inference(tmp_path):
    path = tmp_path / "literal.csv"
    path.write_text('status,amount\n001,10\n1,20\n" N ",30\nNA,40\n', encoding="utf-8")
    context = guide(definition("status", source_table=path.name, values=[
        {"value": "001", "label": "First"}, {"value": "1", "label": "Second"}, {"value": "NA", "label": "Not allocated"}]))
    processor = FileProcessor(data_dictionary_context=context, source_name=path.name)
    frame = processor._read_file(str(path), ".csv")
    assert frame["status"].to_list() == ["001", "1", " N ", "NA"]
    cleaned, _ = processor.clean_dataframe(frame, {"clean_text": True, "parse_currency_percent": True})
    assert cleaned["status"].to_list() == ["001", "1", " N ", "NA"]
    assert cleaned["amount"].sum() == 100
    numeric_path = tmp_path / "numeric-looking.csv"
    numeric_path.write_text("status,amount\n001,10\n1,20\n", encoding="utf-8")
    numeric_context = guide(definition("status", source_table=numeric_path.name, values=[{"value": "001", "label": "First"}, {"value": "1", "label": "Second"}]))
    assert FileProcessor()._read_file(str(numeric_path), ".csv")["status"].dtype.is_numeric()
    literal = FileProcessor(data_dictionary_context=numeric_context, source_name=numeric_path.name)._read_file(str(numeric_path), ".csv")
    assert literal["status"].dtype == pl.String and literal["status"].to_list() == ["001", "1"]


def test_relative_day_basis_prevents_early_calendar_conversion(tmp_path):
    path = tmp_path / "offset.csv"
    path.write_text("date,value\n20240101,2\n20240102,3\n", encoding="utf-8")
    context = guide(definition("date", source_table=path.name, values=[], time_basis={"kind": "relative_day", "origin": "the recorded starting point"}))
    processor = FileProcessor(data_dictionary_context=context, source_name=path.name)
    frame = processor._read_file(str(path), ".csv")
    assert frame["date"].dtype.is_numeric() and frame["date"].to_list() == [20240101, 20240102]
    cleaned, _ = processor.clean_dataframe(frame, {"normalize_dates": True})
    assert cleaned["date"].to_list() == [20240101, 20240102]


def test_filter_choices_show_meaning_and_raw_code_from_canonical_schema():
    field = apply_data_dictionary([source_field("status")], guide(definition("status", values=[{"value": "M", "label": "Married"}, {"value": "S", "label": "Single"}])))[0]
    choices = [{"value": "M", "count": 2}, {"value": "S", "count": 1}]
    metadata = {"schema": [field], "data_profile": {"columns": [{"name": "status", "analysis_role": "dimension",
        "categorical_summary": {"unique_count": 2, "top_values": choices}}]}}
    shown = _derive_filterable_columns(metadata)[0]
    assert shown.top_values[0] == {"value": "M", "count": 2, "label": "Married (M)"}
    assert choices[0] == {"value": "M", "count": 2}


def test_provided_label_keeps_nongeneric_source_roles_distinct():
    fields = [source_field("DST_" + role, measure_grain={"source_table": "airports.csv", "source_column": "DST", "source_role": role})
              for role in ("source_airport", "destination_airport")]
    bound = apply_data_dictionary(fields, guide(definition("DST", source_table="airports.csv", label="Daylight saving time region", values=[])))
    assert source_column_label(bound[0]) == "Source Airport daylight saving time region"
    assert source_column_label(bound[1]) == "Destination Airport daylight saving time region"


def test_one_output_column_with_mixed_roles_never_takes_the_first_role_definition():
    field = source_field("DST", measure_grain={"source_origins": [
        {"source_table": "airports.csv", "source_column": "DST", "source_role": "source_airport"},
        {"source_table": "airports.csv", "source_column": "DST", "source_role": "destination_airport"}]})
    with pytest.raises(ValueError, match="more than one source role"):
        apply_data_dictionary([field], guide(definition("DST", source_table="airports.csv")))


def test_supplied_label_is_not_reinterpreted_as_a_raw_header_with_units():
    field = apply_data_dictionary([source_field("RBI")], guide(definition("RBI", label="Runs Batted In", values=[])))[0]
    assert reader_label(source_column_label(field), field) == "runs batted in"


@pytest.mark.parametrize("codes", [
    ["9007199254740992", "9007199254740993"],
    ["9223372036854775808", "9223372036854775809"],
    ["0.10000000000000000001", "0.10000000000000000002"],
])
async def test_large_guided_codes_survive_read_and_clean_exactly(tmp_path, codes):
    path = tmp_path / "records.csv"
    path.write_text("segment,amount\n" + "\n".join(f"{value},{number}" for value, number in zip(codes, [10, 20], strict=True)) + "\n")
    before = path.read_bytes()
    context = {"data_dictionary": {"version": 1, "fields": [{
        "source_table": path.name, "source_column": "segment",
        "values": [{"value": value, "label": f"Category {index}"} for index, value in enumerate(codes)],
    }]}}
    processor = FileProcessor(data_dictionary_context=context, source_name=path.name)
    frame = processor._read_file(str(path), ".csv")
    assert frame["segment"].dtype == pl.String
    assert frame["segment"].to_list() == codes
    destination, export = tmp_path / "clean.parquet", tmp_path / "clean.csv"
    await processor.clean_file(str(path), ".csv", str(destination), str(export), {"parse_currency_percent": True})
    assert pl.read_parquet(destination)["segment"].to_list() == codes
    assert path.read_bytes() == before


@pytest.mark.parametrize("clean", [False, True])
@pytest.mark.parametrize("bad_field", [
    {"source_table": "missing.csv", "source_column": "status", "label": "Status"},
    {"source_table": "customers.csv", "source_column": "status", "label": "Status"},
    {"source_table": "customers.csv", "source_column": "name", "time_basis": {"kind": "relative_day", "origin": "start"}},
])
async def test_combined_guide_failure_cleans_generated_files(tmp_path, monkeypatch, clean, bad_field):
    files = []
    for name, text in [
        ("facts.csv", "line_id,customer_id,amount\n1,A,10\n2,A,20\n"),
        ("customers.csv", "customer_id,name\nA,Alice\nB,Bob\n"),
    ]:
        path = tmp_path / name
        path.write_text(text)
        files.append(SimpleNamespace(id=uuid.uuid4(), original_filename=name, storage_path=str(path),
                                     file_size=path.stat().st_size, row_count=2, column_count=3 if name == "facts.csv" else 2))
    before = {file.storage_path: Path(file.storage_path).read_bytes() for file in files}
    user = SimpleNamespace(id=uuid.uuid4(), storage_used_bytes=0)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: files))), add=Mock(), flush=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(analyses.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(analyses, "ensure_analysis_quota", lambda *_args: None)
    monkeypatch.setattr(analyses, "ensure_storage_quota", lambda *_args: None)
    body = CreateCombinedAnalysisRequest(file_ids=[file.id for file in files],
        cleaning={"mode": "clean" if clean else "raw"},
        relationship_context={"data_dictionary": {"version": 1, "fields": [bad_field]}})
    endpoint = analyses.create_combined_analysis
    while hasattr(endpoint, "__wrapped__"):
        endpoint = endpoint.__wrapped__
    with pytest.raises(HTTPException) as error:
        await endpoint(Request({"type": "http", "method": "POST", "path": "/api/v1/analyses/combined", "headers": []}),
                       body, user, db)
    assert error.value.status_code == 422
    assert list(tmp_path.rglob("*.parquet")) == []
    assert {file.storage_path: Path(file.storage_path).read_bytes() for file in files} == before

