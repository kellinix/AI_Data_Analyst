import math
from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.analytics.summary_evidence import _finite, _format, build_summary_facts
from app.services.chat_evidence import friendly_chat_content
from app.services.investigation import ComparisonPlan, _decimal_aggregate, _load, compare


async def comparison(tmp_path, groups, aggregation="average", limit=1, include_dtype=True, grouped=True, order="desc", filters=None):
    rows = [{"category": name, "value": value} for name, values in groups.items() for value in values]
    path = tmp_path / f"{uuid4()}.parquet"
    frame = pl.DataFrame(rows)
    frame.write_parquet(path)
    analysis = SimpleNamespace(id=uuid4(), row_count=len(rows), file=SimpleNamespace(storage_path=str(path)),
        metadata_={"schema": [
            {"name": "category", "is_numeric": False, "analysis_role": "dimension"},
            {"name": "value", "is_numeric": True, "analysis_role": "metric",
             **({"dtype": str(frame.schema["value"])} if include_dtype else {})},
        ]})
    return await compare(analysis, ComparisonPlan(aggregation=aggregation, column="value",
                         group_by="category" if grouped else None, limit=limit, order=order, filters=filters or []))


@pytest.mark.parametrize("limit", [1, 5])
async def test_equal_unit_prices_tie_across_unequal_genre_sizes(tmp_path, limit):
    # The five purchased Chinook genres each contain only the recorded 1.99
    # line price. Their different sizes must not create a unique winner.
    sizes = {"Drama": 29, "Comedy": 9, "Science Fiction": 6, "Sci Fi & Fantasy": 20, "TV Shows": 47}
    result = await comparison(tmp_path, {name: [1.99] * count for name, count in sizes.items()}, limit=limit)
    assert result["ranking"]["tied"] == 5
    assert len(result["groups"]) == limit
    assert all(group["value"] == 1.99 for group in result["groups"])
    assert "5 groups tie" in result["answer"]
    if limit == 1:
        assert "Showing 1 of these tied groups" in result["answer"]
        assert result["groups"][0]["group"] in result["answer"]


@pytest.mark.parametrize("aggregation,second,expected", [("sum", [0.3], 0.3), ("average", [0.15], 0.15)])
async def test_equal_decimal_aggregates_tie_without_rounding_the_result(tmp_path, aggregation, second, expected):
    result = await comparison(tmp_path, {"first": [0.1, 0.2], "second": second}, aggregation)
    assert result["ranking"]["tied"] == 2
    assert result["groups"][0]["value"] == expected


@pytest.mark.parametrize("aggregation,expected", [("sum", 1.0), ("average", 1 / 3)])
async def test_cancellation_keeps_the_supplied_small_value(tmp_path, aggregation, expected):
    result = await comparison(tmp_path, {"recorded": [1e16, 1.0, -1e16]}, aggregation)
    assert result["groups"][0]["value"] == expected


@pytest.mark.parametrize("aggregation", ["sum", "average"])
@pytest.mark.parametrize("first,second", [
    ([1e12, 1e12, 1e12], [1e12 + 1, 1e12 + 1, 1e12 + 1]),
    ([1e-20, 2e-20, 3e-20], [1e-20, 2e-20, 3.000000000003e-20]),
    ([1.0], [1.0000000000000002]),
])
async def test_genuinely_different_large_tiny_and_adjacent_values_remain_distinct(tmp_path, aggregation, first, second):
    result = await comparison(tmp_path, {"first": first, "second": second}, aggregation)
    assert result["ranking"]["tied"] == 1
    assert result["groups"][0]["group_value"] == "second"


@pytest.mark.parametrize("operation", ["sum", "average"])
def test_decimal_aggregate_skips_nulls_and_returns_no_value_for_empty_input(operation):
    assert _decimal_aggregate(None, operation) is None
    assert _decimal_aggregate([], operation) is None
    assert _decimal_aggregate([None], operation) is None
    assert _decimal_aggregate([None, "1.99", None], operation) == 1.99


@pytest.mark.parametrize("operation", ["sum", "average"])
def test_nonfinite_input_remains_nonfinite_for_existing_validation(operation):
    assert math.isinf(_decimal_aggregate(["NaN"], operation))
    assert math.isinf(_decimal_aggregate(["Infinity"], operation))


async def test_overflowing_total_uses_the_existing_finite_result_error(tmp_path):
    with pytest.raises(ValueError, match="cannot be used as numbers"):
        await comparison(tmp_path, {"recorded": [1e308, 1e308]}, "sum")


@pytest.mark.parametrize("include_dtype", [True, False])
async def test_large_integer_totals_and_legacy_schemas_keep_native_exact_results(tmp_path, include_dtype):
    result = await comparison(tmp_path, {"first": [2**53 + 1], "second": [2**53 + 2]},
                              "sum", limit=2, include_dtype=include_dtype)
    assert result["calculation"] == 'SUM("value")'
    assert result["ranking"]["tied"] == 1
    assert [group["group_value"] for group in result["groups"]] == ["second", "first"]
    assert [group["value"] for group in result["groups"]] == [2**53 + 2, 2**53 + 1]
    assert all(isinstance(group["value"], int) for group in result["groups"])
    assert "9,007,199,254,740,994" in result["answer"]
    assert "9,007,199,254,740,993" in result["answer"]
    assert "1 more than first" in result["answer"]


async def test_scalar_integer_total_keeps_its_exact_digits(tmp_path):
    result = await comparison(tmp_path, {"recorded": [2**53 + 1]}, "sum", grouped=False)
    assert result["groups"][0]["value"] == 2**53 + 1
    assert "9,007,199,254,740,993" in result["answer"]


@pytest.mark.parametrize("value", [2**53 + 1, -(2**53 + 1)])
def test_summary_and_saved_fact_formatting_keep_large_integer_digits(value):
    assert _finite(value) == value and isinstance(_finite(value), int)
    assert _format(value) == f"{value:,}"
    stats = {"row_count": 1, "column_count": 1,
        "schema": [{"name": "units", "is_numeric": True, "analysis_role": "metric"}],
        "numeric_stats": {"units": {"count": 1, "total": value}}, "categorical_stats": {}}
    facts = build_summary_facts(stats, [{"column": "units", "value": value, "is_total": True}])
    metric = next(fact for fact in facts if fact["id"].startswith("metric_"))
    assert f"{value:,}" in metric["text"]
    saved = {"id": "saved_0", "text": metric["text"], "values": {"column": "units", "operation": "total", "value": value}}
    assert f"{value:,}" in friendly_chat_content([saved])


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity"])
async def test_registered_decimal_function_preserves_a_nonfinite_error_sentinel(tmp_path, invalid):
    path = tmp_path / "registered.parquet"
    pl.DataFrame({"value": [1.0]}).write_parquet(path)
    analysis = SimpleNamespace(row_count=1, file=SimpleNamespace(storage_path=str(path)),
        metadata_={"schema": [{"name": "value", "is_numeric": True, "analysis_role": "metric"}]})
    connection, _, _ = await _load(analysis)
    try:
        result = connection.execute("SELECT vesquiri_decimal_aggregate(?::VARCHAR[], 'average')", [[invalid]]).fetchone()[0]
        assert result is not None and math.isinf(result)
    finally:
        connection.close()


@pytest.mark.parametrize("operation", ["sum", "average"])
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
async def test_selected_nonfinite_groups_are_rejected_before_ranking_limit(tmp_path, operation, order, invalid):
    with pytest.raises(ValueError, match="cannot be used as numbers"):
        await comparison(tmp_path, {"valid": [1.0], "invalid": [invalid]}, operation, order=order, limit=1)


@pytest.mark.parametrize("operation", ["sum", "average"])
async def test_scalar_nonfinite_values_are_rejected(tmp_path, operation):
    with pytest.raises(ValueError, match="cannot be used as numbers"):
        await comparison(tmp_path, {"invalid": [float("nan")]}, operation, grouped=False)


@pytest.mark.parametrize("operation", ["sum", "average"])
async def test_filtered_out_invalid_values_do_not_block_valid_calculations(tmp_path, operation):
    result = await comparison(tmp_path, {"valid": [2.0], "invalid": [float("nan"), float("inf")]}, operation,
        filters=[{"column": "category", "op": "in", "values": ["valid"]}])
    assert result["matched_entries"] == 1
    assert result["groups"][0]["value"] == 2.0


@pytest.mark.parametrize("operation", ["sum", "average"])
async def test_all_null_measure_values_remain_unavailable_without_an_invalid_value_error(tmp_path, operation):
    result = await comparison(tmp_path, {"empty": [None, None]}, operation)
    assert result["matched_entries"] == 2
    assert result["groups"][0]["value"] is None
