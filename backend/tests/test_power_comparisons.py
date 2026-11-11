from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

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
