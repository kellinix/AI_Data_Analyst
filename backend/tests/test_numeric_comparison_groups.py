from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.services.investigation import ComparisonPlan, compare, validate_plan


async def test_explicit_numeric_grouping_keeps_the_source_field_numeric(tmp_path):
    path = tmp_path / "scores.parquet"
    pl.DataFrame({"length_days": [200, 200, 250], "score": [40, 60, 90]}).write_parquet(path)
    schema = [{"name": name, "analysis_role": "metric", "is_numeric": True}
              for name in ("length_days", "score")]
    analysis = SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)), row_count=3,
        metadata_={"schema": schema})
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="score", group_by="length_days"))
    assert result["groups"][0]["value"] == 90
    assert result["groups"][0]["group_value"] == "250"
    assert schema[0]["analysis_role"] == "metric"


@pytest.mark.parametrize("stats_source", ["numeric_stats", "profile_column"])
async def test_explicit_average_of_numeric_flag_is_arithmetic_mean(tmp_path, stats_source):
    path = tmp_path / "routes.parquet"
    pl.DataFrame({"stops": [0, 0, 1, None]}).write_parquet(path)
    metadata = {"schema": [{"name": "stops", "analysis_role": "flag", "is_numeric": True}]}
    if stats_source == "numeric_stats":
        metadata["numeric_stats"] = {"stops": {"count": 3, "min": 0, "max": 1, "integer_count": 3}}
    else:
        metadata["data_profile"] = {"columns": [{"name": "stops", "numeric_summary": {"count": 3, "min": 0, "max": 1},
            "categorical_summary": {"unique_count": 2, "top_values": [{"value": "0", "count": 2}, {"value": "1", "count": 1}]}}]}
    analysis = SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)), row_count=4, metadata_=metadata)
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="stops"))
    assert result["groups"][0]["value"] == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="measurable"):
        validate_plan(ComparisonPlan(aggregation="sum", column="stops"), analysis.metadata_)


@pytest.mark.parametrize("dtype", [pl.Int64, pl.Float64])
@pytest.mark.parametrize("requested", [2016, 2016.0])
@pytest.mark.parametrize("resolve_categories", [False, True])
async def test_numeric_calendar_year_can_filter_a_comparison_without_changing_its_role(tmp_path, dtype, requested, resolve_categories):
    path = tmp_path / "sets.parquet"
    pl.DataFrame({"year": pl.Series([2015, 2016, 2016], dtype=dtype), "theme": ["Technic"] * 3}).write_parquet(path)
    schema = [
        {"name": "year", "is_numeric": True, "is_date": False, "analysis_role": "temporal_dimension"},
        {"name": "theme", "is_numeric": False, "analysis_role": "dimension"},
    ]
    analysis = SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)), row_count=3,
                              metadata_={"schema": schema})
    result = await compare(analysis, ComparisonPlan(aggregation="count",
        filters=[{"column": "year", "op": "in", "values": [requested]},
                 {"column": "theme", "op": "in", "values": ["technic" if resolve_categories else "Technic"]}]),
        resolve_categories=resolve_categories)

    assert result["groups"][0]["value"] == 2
    assert schema[0]["analysis_role"] == "temporal_dimension"


@pytest.mark.parametrize("stats", [
    {},
    {"count": 2, "min": 1, "max": 2, "integer_count": 2},
    {"count": 3, "min": 0, "max": 1, "integer_count": 2, "unique_count": 3},
    {"count": 3, "min": 0, "max": 1},
])
def test_average_rejects_encoded_fractional_or_unverified_flag_domains(stats):
    metadata = {"schema": [{"name": "status_flag", "is_numeric": True, "analysis_role": "flag"}],
                "numeric_stats": {"status_flag": stats}}
    with pytest.raises(ValueError, match="verify every supplied flag is 0 or 1"):
        validate_plan(ComparisonPlan(aggregation="average", column="status_flag"), metadata)


@pytest.mark.parametrize("requested", [True, "NaN", "Infinity", "not-a-year"])
def test_numeric_calendar_membership_requires_a_finite_number(requested):
    metadata = {"schema": [{"name": "year", "is_numeric": True, "is_date": False,
                            "analysis_role": "temporal_dimension"}]}
    with pytest.raises(ValueError, match="finite numeric calendar value"):
        validate_plan(ComparisonPlan(aggregation="count", filters=[{"column": "year", "op": "in", "values": [requested]}]), metadata)


async def test_numeric_attribute_supports_an_explicit_average_and_rejects_its_sum(tmp_path):
    path = tmp_path / "athletes.parquet"
    pl.DataFrame({"height": [1.7, 1.9, None], "country": ["A", "A", "B"]}).write_parquet(path)
    metadata = {"schema": [
        {"name": "height", "is_numeric": True, "analysis_role": "attribute"},
        {"name": "country", "is_numeric": False, "analysis_role": "dimension"},
    ]}
    analysis = SimpleNamespace(id=uuid4(), file=SimpleNamespace(storage_path=str(path)), row_count=3,
                              metadata_=metadata)
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="height", group_by="country"))

    assert result["groups"][0]["value"] == pytest.approx(1.8)
    with pytest.raises(ValueError, match="measurable"):
        validate_plan(ComparisonPlan(aggregation="sum", column="height"), metadata)
