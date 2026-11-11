from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.analytics.chart_selector import _aggregation
from app.analytics.data_dictionary import apply_data_dictionary
from app.analytics.kpi_detector import uses_average_aggregation
from app.analytics.measure_semantics import is_power_reading, is_rate_or_average
from app.services.investigation import (
    ComparisonPlan,
    ComparisonUnavailable,
    EntryRequest,
    compare,
    comparison_answer,
    entries,
    validate_plan,
)


@pytest.mark.parametrize("column", ["AEP_MW", "load_kw", "power_w", "PowerWatts", "demand_watts"])
async def test_power_reading_sums_need_an_energy_or_time_basis(column, tmp_path):
    metadata = {"schema": [{"name": column, "is_numeric": True, "analysis_role": "metric"}]}
    with pytest.raises(ComparisonUnavailable, match="energy total"):
        validate_plan(ComparisonPlan(aggregation="sum", column=column), metadata)
    path = tmp_path / "power.parquet"
    pl.DataFrame({column: [100., 200., None, 300.]}).write_parquet(path)
    analysis = SimpleNamespace(id=uuid4(), row_count=4, metadata_=metadata,
                               file=SimpleNamespace(storage_path=str(path)))
    result = await compare(analysis, ComparisonPlan(aggregation="average", column=column))
    assert result["groups"][0]["value"] == 200
    assert result["groups"][0]["supplied_values"] == 3


@pytest.mark.parametrize("unit", ["W", "kW", "MW", "watts", "megawatts"])
def test_explicit_power_units_are_used_for_unnamed_readings(unit):
    metadata = {"schema": [{"name": "reading", "unit": unit, "is_numeric": True, "analysis_role": "metric"}]}
    with pytest.raises(ComparisonUnavailable):
        validate_plan(ComparisonPlan(aggregation="sum", column="reading"), metadata)


@pytest.mark.parametrize("unit", ["kW", "MW", "%", "percent", "percentage", "pct", "per cent"])
async def test_supplied_units_block_nonadditive_totals_and_preserve_raw_average(unit, tmp_path):
    schema = apply_data_dictionary([
        {"name": "consumption", "is_numeric": True, "analysis_role": "metric", "dtype": "DOUBLE"},
    ], {"data_dictionary": {"version": 1, "fields": [{
        "source_table": "readings.csv", "source_column": "consumption", "unit": unit,
    }]}}, file_name="readings.csv")
    metadata = {"schema": schema}
    with pytest.raises(ValueError):
        validate_plan(ComparisonPlan(aggregation="sum", column="consumption"), metadata)
    path = tmp_path / "readings.parquet"
    pl.DataFrame({"consumption": [.1, .2, None]}).write_parquet(path)
    before = path.read_bytes()
    analysis = SimpleNamespace(id=uuid4(), row_count=3, metadata_=metadata,
                               file=SimpleNamespace(storage_path=str(path)))
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="consumption"))
    assert result["groups"][0]["value"] == pytest.approx(.15)
    assert result["groups"][0]["supplied_values"] == 2
    assert path.read_bytes() == before


def test_supplied_energy_unit_retains_supported_sum_and_wins_saved_unit():
    field = {"name": "consumption", "is_numeric": True, "analysis_role": "metric", "unit": "kW",
             "data_definition": {"unit": "kWh"}}
    expression, _, _ = validate_plan(ComparisonPlan(aggregation="sum", column="consumption"), {"schema": [field]})
    assert expression.startswith("SUM(")
    field["unit"], field["data_definition"]["unit"] = "kWh", "kW"
    with pytest.raises(ComparisonUnavailable):
        validate_plan(ComparisonPlan(aggregation="sum", column="consumption"), {"schema": [field]})


def test_generic_numeric_field_without_a_supplied_unit_keeps_its_sum():
    field = {"name": "consumption", "is_numeric": True, "analysis_role": "metric"}
    expression, _, _ = validate_plan(ComparisonPlan(aggregation="sum", column="consumption"), {"schema": [field]})
    assert expression.startswith("SUM(")


@pytest.mark.parametrize(("column", "provided_label", "values"), [
    ("ERA", "Earned run average", [2.5, 3.5]),
    ("FP", "Fielding percentage", [.94, .98]),
    ("measure_x", "Average shipment size", [10., 20.]),
    ("measure_x", "Power in kilowatts", [100., 200.]),
    ("measure_x", "Measured ratio", [.1, .2]),
])
async def test_supplied_numeric_labels_use_shared_nonadditive_safeguards(column, provided_label, values, tmp_path):
    schema = apply_data_dictionary([
        {"name": column, "is_numeric": True, "is_date": False, "analysis_role": "metric", "semantic_type": "numeric_metric"},
    ], {"data_dictionary": {"version": 1, "fields": [{
        "source_table": "measurements.csv", "source_column": column, "label": provided_label,
    }]}}, file_name="measurements.csv")
    field = schema[0]
    assert field["semantic_type"] == "numeric_metric" and field["analysis_role"] == "metric"
    assert uses_average_aggregation(column, field=field)
    assert _aggregation(column, field) == "average"
    with pytest.raises(ValueError):
        validate_plan(ComparisonPlan(aggregation="sum", column=column), {"schema": schema})
    path = tmp_path / "measurements.parquet"
    pl.DataFrame({column: values}).write_parquet(path)
    before = path.read_bytes()
    analysis = SimpleNamespace(id=uuid4(), row_count=len(values), metadata_={"schema": schema},
                               file=SimpleNamespace(storage_path=str(path)))
    result = await compare(analysis, ComparisonPlan(aggregation="average", column=column))
    assert result["groups"][0]["value"] == pytest.approx(sum(values) / len(values))
    assert path.read_bytes() == before


def test_supplied_code_dimension_labels_keep_their_recorded_role():
    field = {"name": "status", "is_numeric": True, "analysis_role": "dimension",
             "data_definition": {"label": "Average category code", "value_labels": [{"value": 1, "label": "Percentage code"}]}}
    assert not is_rate_or_average("status", field)
    assert not is_power_reading("status", field)
    assert field["analysis_role"] == "dimension"
    ordinary = {"name": "measure_x", "is_numeric": True, "analysis_role": "metric", "display_label": "Average result"}
    assert not is_rate_or_average("measure_x", ordinary)


@pytest.mark.parametrize("column", ["energy_mwh", "consumption_kwh", "W", "new_orders", "amount_gbp"])
def test_energy_fields_and_unrelated_w_labels_keep_supported_sums(column):
    metadata = {"schema": [{"name": column, "is_numeric": True, "analysis_role": "metric"}]}
    expression, _, _ = validate_plan(ComparisonPlan(aggregation="sum", column=column), metadata)
    assert expression.startswith("SUM(")


@pytest.fixture
def dated_readings(tmp_path):
    frame = pl.DataFrame({"date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 2, 1), date(2025, 1, 1)],
                          "power_mw": [100., 200., 300., 400.], "revenue": [10., 20., 30., 40.]})
    path = tmp_path / "readings.parquet"
    frame.write_parquet(path)
    schema = [{"name": "date", "analysis_role": "temporal_dimension", "is_date": True},
              *[{"name": name, "analysis_role": "metric", "is_numeric": True} for name in ("power_mw", "revenue")]]
    return SimpleNamespace(id=uuid4(), row_count=4, file=SimpleNamespace(storage_path=str(path)),
                           metadata_={"schema": schema}, insights=[])


async def test_power_average_remains_measured_and_sum_cannot_reach_execution(dated_readings):
    result = await compare(dated_readings, ComparisonPlan(aggregation="average", column="power_mw"))
    assert result["groups"][0]["value"] == 250
    with pytest.raises(ComparisonUnavailable, match="known time intervals"):
        await compare(dated_readings, ComparisonPlan(aggregation="sum", column="power_mw"))


@pytest.mark.parametrize(("bucket", "expected_label", "raw", "count"), [
    ("year", "2024", "2024-01-01", 3),
    ("month", "Jan 2025", "2025-01-01", 1),
    ("day", "1 Jan 2025", "2025-01-01", 1),
])
async def test_date_bucket_labels_are_readable_and_drilldowns_keep_raw_values(dated_readings, bucket, expected_label, raw, count):
    plan = ComparisonPlan(aggregation="sum", column="revenue", group_by="date", date_bucket=bucket)
    result = await compare(dated_readings, plan)
    first = result["groups"][0]
    assert first["group"] == expected_label
    assert first["group_value"].startswith(raw)
    assert "00:00:00" not in result["answer"]
    assert "Date 2024" not in result["answer"]
    linked = await entries(dated_readings, EntryRequest(kind="comparison", comparison=plan,
                           group_value=first["group_value"], evidence_revision=result["evidence_revision"]))
    assert linked["matched_entries"] == count


def test_saved_date_comparisons_get_readable_labels_without_rewriting_values():
    result = {"answer": "Old list", "matched_entries": 2, "group_count": 2,
              "plan": {"aggregation": "average", "column": "power_mw", "group_by": "date", "date_bucket": "year"},
              "groups": [{"group": "2024-01-01 00:00:00", "group_value": "2024-01-01 00:00:00", "value": 200},
                         {"group": "2025-01-01 00:00:00", "group_value": "2025-01-01 00:00:00", "value": 100}]}
    answer = comparison_answer(result)
    assert answer.startswith("2024 has the highest")
    assert "100 more than 2025" in answer
    assert result["groups"][0]["group_value"] == "2024-01-01 00:00:00"
