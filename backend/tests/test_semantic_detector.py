from __future__ import annotations

from app.analytics.semantic_detector import enrich_schema_with_semantics


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


def test_player_physical_columns_are_attributes_not_metrics():
    schema = [
        {"name": "age", "dtype": "BIGINT", "is_numeric": True, "is_date": False},
        {"name": "height_cm", "dtype": "BIGINT", "is_numeric": True, "is_date": False},
        {"name": "weight_kg", "dtype": "BIGINT", "is_numeric": True, "is_date": False},
        {"name": "jersey_number", "dtype": "BIGINT", "is_numeric": True, "is_date": False},
    ]
    numeric_stats = {
        "age": {"min": 18.0, "max": 38.0},
        "height_cm": {"min": 165.0, "max": 205.0},
        "weight_kg": {"min": 60.0, "max": 100.0},
        "jersey_number": {"min": 1.0, "max": 99.0},
    }

    enriched = enrich_schema_with_semantics(schema, numeric_stats, {})

    assert {column["analysis_role"] for column in enriched} == {"attribute"}
