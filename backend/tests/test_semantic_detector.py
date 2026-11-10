from __future__ import annotations

import pytest

from app.analytics.kpi_detector import detect_kpis
from app.analytics.semantic_detector import enrich_schema_with_semantics


def test_constant_quantity_remains_a_measure_instead_of_a_binary_flag():
    names = ("quantity", "order_quantity")
    schema = [{"name": name, "dtype": "BIGINT", "is_numeric": True, "is_date": False}
              for name in names]
    statistics = {name: {"min": 1, "max": 1, "unique_count": 1, "count": 100}
                  for name in names}

    fields = enrich_schema_with_semantics(schema, statistics, {})

    assert all(field["analysis_role"] == "metric" for field in fields)
    assert all(field["semantic_type"] == "count" for field in fields)


@pytest.mark.parametrize(("original", "semantic_type", "role"), [
    ("OrderQuantity", "count", "metric"),
    ("CustomerCount", "count", "metric"),
    ("NumberOfPassengers", "count", "metric"),
    ("WarehouseLatitude", "numeric_attribute", "attribute"),
    ("UnitPrice", "currency", "metric"),
    ("EmployeeID", "identifier", "identifier"),
    ("IsReturned", "boolean", "flag"),
    ("AverageQuantity", "average_metric", "metric"),
    ("AverageUnitPrice", "average_metric", "metric"),
])
def test_cleaned_compact_names_retain_original_header_meaning(original, semantic_type, role):
    name = original.lower()
    schema = [{"name": name, "dtype": "BIGINT", "is_numeric": True, "is_date": False}]
    numeric = {name: {"min": 1, "max": 3, "unique_count": 3, "count": 100}}

    enriched = enrich_schema_with_semantics(schema, numeric, {}, original_names={name: original})

    assert enriched[0]["name"] == name
    assert enriched[0]["semantic_type"] == semantic_type
    assert enriched[0]["analysis_role"] == role
    assert list(numeric) == [name]
    assert "semantic_type" not in schema[0]


def test_lookup_source_header_preserves_numeric_measure_and_provenance():
    origin = {"kind": "fact", "source_table": "sales.csv", "source_column": "OrderQuantity", "repeated": False}
    schema = [{"name": "orderquantity", "dtype": "BIGINT", "is_numeric": True, "measure_grain": origin}]
    numeric = {"orderquantity": {"min": 1, "max": 1, "unique_count": 1, "count": 100}}

    enriched = enrich_schema_with_semantics(schema, numeric, {})

    assert enriched[0]["semantic_type"] == "count"
    assert enriched[0]["analysis_role"] == "metric"
    assert enriched[0]["measure_grain"] == origin
    assert enriched[0]["name"] == "orderquantity"


def test_original_average_quantity_stays_an_average_kpi():
    schema = [{"name": "averagequantity", "dtype": "BIGINT", "is_numeric": True}]
    numeric = {"averagequantity": {"min": 1, "max": 3, "unique_count": 3, "count": 100, "mean": 2, "total": 200}}

    enriched = enrich_schema_with_semantics(schema, numeric, {}, original_names={"averagequantity": "AverageQuantity"})
    kpis = detect_kpis(enriched, numeric)

    assert enriched[0]["semantic_type"] == "average_metric"
    assert kpis[0]["value"] == 2
    assert kpis[0]["is_total"] is False


def test_three_named_medal_columns_are_counts_while_medal_ids_remain_labels():
    names = ("gold", "silver", "bronze", "gold_id")
    schema = [{"name": name, "dtype": "BIGINT", "is_numeric": True} for name in names]
    numeric = {name: {"min": 0, "max": 2, "unique_count": 3, "count": 100} for name in names}

    fields = {field["name"]: field for field in enrich_schema_with_semantics(schema, numeric, {})}

    assert all(fields[name]["semantic_type"] == "count" for name in names[:3])
    assert all(fields[name]["analysis_role"] == "metric" for name in names[:3])
    assert fields["gold_id"]["analysis_role"] == "identifier"


def test_one_bounded_gold_column_does_not_establish_a_medal_count():
    schema = [{"name": "gold", "dtype": "BIGINT", "is_numeric": True}]
    numeric = {"gold": {"min": 0, "max": 2, "unique_count": 3, "count": 100}}

    fields = enrich_schema_with_semantics(schema, numeric, {})

    assert fields[0]["analysis_role"] == "dimension"


def test_two_named_operational_groups_are_dimensions_not_boolean_flags():
    schema = [{"name": name, "dtype": "VARCHAR", "is_numeric": False, "is_date": False}
              for name in ("shift", "hiring_stage", "appointment_status")]
    categories = {name: {"unique_count": 2, "top_values": [{"value": "A", "count": 50}, {"value": "B", "count": 50}]}
                  for name in ("shift", "hiring_stage", "appointment_status")}
    assert all(item["analysis_role"] == "dimension" for item in enrich_schema_with_semantics(schema, {}, categories))


def test_rank_and_compact_ids_are_not_metrics_but_football_counts_are():
    names = ["rk", "rk_stats_keeper", "shipmentid", "spid", "pid", "gid", "gls", "ast", "mp", "column_1"]
    schema = [{"name": name, "dtype": "DOUBLE", "is_numeric": True, "is_date": False}
              for name in names]
    stats = {name: {"min": 0, "max": 10, "unique_count": 8, "count": 100}
             for name in names}
    roles = {item["name"]: item["analysis_role"]
             for item in enrich_schema_with_semantics(schema, stats, {})}
    assert all(roles[name] == "identifier" for name in names[:6])
    assert all(roles[name] == "metric" for name in ("gls", "ast", "mp"))
    assert roles["column_1"] == "unknown"


def test_detects_currency_metric_from_column_name():
    schema = [{"name": "total_revenue", "dtype": "DOUBLE", "is_numeric": True, "is_date": False}]
    enriched = enrich_schema_with_semantics(schema, {"total_revenue": {}}, {})
    assert enriched[0]["semantic_type"] == "currency"
    assert enriched[0]["analysis_role"] == "metric"


def test_detects_email_from_observed_values():
    schema = [{"name": "contact", "dtype": "VARCHAR", "is_numeric": False, "is_date": False}]
    categorical_stats = {
        "contact": {
            "unique_count": 2,
            "top_values": [
                {"value": "alex@example.com", "count": 1},
                {"value": "sam@example.com", "count": 1},
            ],
        }
    }
    enriched = enrich_schema_with_semantics(schema, {}, categorical_stats)
    assert enriched[0]["semantic_type"] == "email"
    assert enriched[0]["analysis_role"] == "identifier"


def test_numeric_date_name_is_temporal_not_metric():
    schema = [{"name": "match_date", "dtype": "DOUBLE", "is_numeric": True, "is_date": False}]
    numeric_stats = {"match_date": {"min": 20260710.0, "max": 20260731.0}}

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})

    assert enriched[0]["semantic_type"] == "date"
    assert enriched[0]["analysis_role"] == "temporal_dimension"


def test_prose_column_name_containing_time_is_not_a_date():
    """Regression: the name rule matched the word "time" inside
    "...assessment of the project at a fixed point in time...", so a
    Red/Amber/Green rating became the dashboard's time axis."""
    name = (
        "ipa_delivery_confidence_assessment_a_delivery_confidence_assessment_of_the_"
        "project_at_a_fixed_point_in_time_using_a_three_point_scale_red_amber_green"
    )
    schema = [{"name": name, "dtype": "VARCHAR", "is_numeric": False, "is_date": False}]
    categorical_stats = {
        name: {
            "unique_count": 3,
            "top_values": [
                {"value": "Amber", "count": 20},
                {"value": "Green", "count": 15},
                {"value": "Not Applicable", "count": 14},
            ],
        }
    }

    enriched = enrich_schema_with_semantics(schema, {}, categorical_stats)

    assert enriched[0]["analysis_role"] != "temporal_dimension"
    assert enriched[0]["semantic_type"] != "date"


def test_text_date_column_with_real_dates_is_still_temporal():
    schema = [{"name": "project_start_date", "dtype": "VARCHAR", "is_numeric": False, "is_date": False}]
    categorical_stats = {
        "project_start_date": {
            "unique_count": 2,
            "top_values": [{"value": "2000-05-17", "count": 3}, {"value": "2014-04-01", "count": 2}],
        }
    }

    enriched = enrich_schema_with_semantics(schema, {}, categorical_stats)

    assert enriched[0]["analysis_role"] == "temporal_dimension"


def test_narrative_column_is_not_typed_as_currency():
    """Same substring bug in the semantic rules: "arr" inside "narrative"."""
    schema = [
        {"name": "departmental_narrative_on_schedule", "dtype": "VARCHAR", "is_numeric": False, "is_date": False}
    ]

    enriched = enrich_schema_with_semantics(schema, {}, {})

    assert enriched[0]["semantic_type"] != "currency"


def test_text_columns_are_never_metrics_however_they_are_named():
    """Regression: a currency-sounding name made a free-text column a metric,
    so "Departmental Narrative on Budgeted Whole Life Costs" — prose — was
    described to the AI as a measure."""
    schema = [
        {
            "name": "departmental_narrative_on_budgeted_whole_life_costs",
            "dtype": "VARCHAR",
            "is_numeric": False,
            "is_date": False,
        },
        {"name": "total_cost", "dtype": "DOUBLE", "is_numeric": True, "is_date": False},
    ]

    enriched = enrich_schema_with_semantics(schema, {"total_cost": {}}, {})
    by_name = {column["name"]: column for column in enriched}

    assert by_name["departmental_narrative_on_budgeted_whole_life_costs"]["analysis_role"] != "metric"
    assert by_name["total_cost"]["analysis_role"] == "metric"


def test_age_and_coordinate_columns_are_attributes_not_metrics():
    schema = [
        {"name": "age", "dtype": "BIGINT", "is_numeric": True, "is_date": False},
        {"name": "warehouse_latitude", "dtype": "DOUBLE", "is_numeric": True, "is_date": False},
        {"name": "warehouse_longitude", "dtype": "DOUBLE", "is_numeric": True, "is_date": False},
    ]
    numeric_stats = {
        "age": {"min": 18.0, "max": 65.0},
        "warehouse_latitude": {"min": -90.0, "max": 90.0},
        "warehouse_longitude": {"min": -180.0, "max": 180.0},
    }

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})

    assert {column["analysis_role"] for column in enriched} == {"attribute"}


def test_small_integer_code_columns_are_dimensions_not_metrics():
    """Columns like cp (chest pain type 0-3) are integer category codes —
    summing, averaging, or outlier-scanning them produces nonsense. A wide
    continuous integer column (e.g. cholesterol) must stay a metric.
    Uses DOUBLE dtype because the CSV loader stores all numbers as DOUBLE —
    detection must work from the observed values."""
    schema = [
        {"name": "cp", "dtype": "DOUBLE", "is_numeric": True, "is_date": False},
        {"name": "chol", "dtype": "DOUBLE", "is_numeric": True, "is_date": False},
    ]
    numeric_stats = {
        "cp": {"min": 0.0, "max": 3.0, "count": 1025, "unique_count": 4},
        "chol": {"min": 126.0, "max": 564.0, "count": 1025, "unique_count": 152},
    }

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})
    by_name = {column["name"]: column for column in enriched}

    assert by_name["cp"]["analysis_role"] == "dimension"
    assert by_name["cp"]["semantic_type"] == "categorical_code"
    assert by_name["chol"]["analysis_role"] == "metric"


def test_fractional_low_cardinality_columns_stay_metrics():
    """A float column with a few distinct fractional values (e.g. discount
    tiers 0.25/0.5/0.75) is still a quantity, not a category code."""
    schema = [{"name": "discount", "dtype": "DOUBLE", "is_numeric": True, "is_date": False}]
    numeric_stats = {"discount": {"min": 0.25, "max": 2.5, "count": 500, "unique_count": 4}}

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})

    assert enriched[0]["analysis_role"] == "metric"


def test_binary_integer_columns_are_flags_not_metrics():
    schema = [{"name": "sex", "dtype": "DOUBLE", "is_numeric": True, "is_date": False}]
    numeric_stats = {"sex": {"min": 0.0, "max": 1.0, "count": 1025, "unique_count": 2}}

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})

    assert enriched[0]["semantic_type"] == "boolean"
    assert enriched[0]["analysis_role"] == "flag"


def test_package_weight_is_treated_as_a_business_metric():
    """A generic business dataset (e.g. logistics) can legitimately have a
    'weight' column as a real metric — it must not be excluded the way a
    sport-specific player-attribute list would."""
    schema = [{"name": "package_weight_kg", "dtype": "DOUBLE", "is_numeric": True, "is_date": False}]
    numeric_stats = {"package_weight_kg": {"min": 0.5, "max": 40.0}}

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})

    assert enriched[0]["analysis_role"] == "metric"
