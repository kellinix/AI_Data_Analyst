from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.analytics.chart_selector import select_charts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.measure_grain import annotate_measure_grain, is_repeated_lookup
from app.analytics.summary_evidence import build_summary_facts
from app.services.chat_evidence import build_chat_facts
from app.services.data_profile import build_data_profile_schema
from app.services.investigation import ComparisonPlan, ComparisonUnavailable, validate_plan


def measured_statistics():
    return {
        "row_count": 3, "column_count": 4,
        "schema": [
            {"name": "quantity", "is_numeric": True, "is_date": False, "analysis_role": "metric", "semantic_type": "numeric_metric"},
            {"name": "freight", "is_numeric": True, "is_date": False, "analysis_role": "metric", "semantic_type": "currency"},
            {"name": "country", "is_numeric": False, "is_date": False, "analysis_role": "dimension"},
            {"name": "order_id", "is_numeric": False, "is_date": False, "analysis_role": "identifier"},
        ],
        "numeric_stats": {
            "quantity": {"count": 3, "null_count": 0, "total": 4, "mean": 4 / 3, "min": 1, "max": 2},
            "freight": {"count": 3, "null_count": 0, "total": 25, "mean": 25 / 3, "min": 5, "max": 10},
        },
        "categorical_stats": {"country": {"unique_count": 2, "top_values": [{"value": "UK", "count": 2}, {"value": "US", "count": 1}]}},
        "date_range": {}, "correlations": {"quantity|freight": .5}, "data_quality": {},
    }


def relationship_context(repeated=True):
    return {"relationship_resolution": {"status": "enriched", "field_origins": {
        "freight": {"source_table": "orders.csv", "source_column": "freight", "entity_key_columns": ["order_id"],
                    "kind": "lookup", "repeated": repeated, "key_basis": "foreign_reference"},
    }}}


@pytest.mark.parametrize("path", ["combined", "cleaned_workbook", "raw_workbook"])
def test_grain_provenance_survives_all_context_paths(path):
    fields = [{"name": "freight_charge", "is_numeric": True}]
    resolution = relationship_context()["relationship_resolution"]
    resolution["field_origins"] = {"Freight Charge": resolution["field_origins"]["freight"]}
    context, parser = {}, {}
    if path == "combined":
        context = {"relationship_resolution": resolution, "cleaning": {"report": {"renamed_columns": {"Freight Charge": "freight_charge"}}}}
    elif path == "cleaned_workbook":
        context = {"cleaning": {"report": {"parser": {"relationship_resolution": resolution}}}}
    else:
        parser = {"relationship_resolution": resolution}
    annotated = annotate_measure_grain(fields, context, parser)
    assert is_repeated_lookup(annotated[0])
    assert fields == [{"name": "freight_charge", "is_numeric": True}]


@pytest.mark.parametrize("aggregation", ["sum", "average", "weighted_average"])
def test_direct_parent_aggregation_is_explicitly_unavailable(aggregation):
    stats = measured_statistics()
    metadata = {"schema": stats["schema"], "upload_context": relationship_context()}
    plan = ComparisonPlan(aggregation=aggregation, column="freight", **({"weight_column": "quantity"} if aggregation == "weighted_average" else {}))
    with pytest.raises(ComparisonUnavailable, match="each source row once"):
        validate_plan(plan, metadata)


def test_repeated_parent_weight_is_unavailable_for_fact_measure():
    stats = measured_statistics()
    with pytest.raises(ComparisonUnavailable):
        validate_plan(ComparisonPlan(aggregation="weighted_average", column="quantity", weight_column="freight"),
                      {"schema": stats["schema"], "upload_context": relationship_context()})


@pytest.mark.parametrize("plan", [
    {"aggregation": "count", "filters": [{"column": "freight", "op": "gte", "values": [10]}]},
    {"aggregation": "distinct_count", "column": "order_id"},
    {"aggregation": "sum", "column": "quantity", "group_by": "country"},
])
def test_fact_counts_distinct_codes_and_fact_measures_remain_supported(plan):
    stats = measured_statistics()
    validate_plan(ComparisonPlan.model_validate(plan), {"schema": stats["schema"], "upload_context": relationship_context()})


def test_one_to_one_lookup_measure_is_unchanged():
    stats = measured_statistics()
    validate_plan(ComparisonPlan(aggregation="sum", column="freight"),
                  {"schema": stats["schema"], "upload_context": relationship_context(repeated=False)})


def test_repeated_parent_values_do_not_feed_kpis_charts_or_saved_facts():
    stats = measured_statistics()
    original = deepcopy(stats["numeric_stats"])
    stats["schema"] = annotate_measure_grain(stats["schema"], relationship_context())
    kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
    assert kpis and all(kpi["column"] != "freight" for kpi in kpis)
    charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"], {}, stats["correlations"])
    assert all(chart.get("xAxis") != "freight" and chart.get("yAxis") != "freight" for chart in charts)
    legacy_kpi = {"column": "freight", "value": 25, "is_total": True}
    assert all(fact.get("values", {}).get("column") != "freight" for fact in build_summary_facts(stats, [legacy_kpi]))
    assert stats["numeric_stats"] == original
    profile = build_data_profile_schema(analysis_id="grain", file_name="combined", statistics=stats,
        kpis=kpis, charts=charts, forecasts=[], anomalies=[], recommendations=[], upload_context=relationship_context())
    freight = next(column for column in profile["columns"] if column["name"] == "freight")
    assert is_repeated_lookup(freight)
    assert set(freight["numeric_summary"]) == {"count", "null_count", "min", "max"}
    assert "freight" not in profile["metrics"]["numeric_statistics"]
    assert profile["metrics"]["correlations"] == {}
    item = SimpleNamespace(row_count=3, column_count=4,
        metadata_={"schema": stats["schema"], "data_profile": profile, "upload_context": relationship_context()},
        insights=[SimpleNamespace(type="summary", data=legacy_kpi)])
    assert all(fact.get("values", {}).get("column") != "freight" for fact in build_chat_facts(item))


def test_fact_percentage_does_not_use_a_repeated_parent_weight():
    stats = measured_statistics()
    stats["schema"].append({"name": "margin_pct", "is_numeric": True, "is_date": False,
                            "analysis_role": "metric", "semantic_type": "percentage"})
    stats["numeric_stats"]["margin_pct"] = {"count": 3, "min": .1, "max": .2, "total": .4,
        "mean": .4 / 3, "weighted_mean": .18, "weight_column": "freight"}
    original = deepcopy(stats["numeric_stats"])
    stats["schema"] = annotate_measure_grain(stats["schema"], relationship_context())
    kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
    margin = next(kpi for kpi in kpis if kpi["column"] == "margin_pct")
    assert margin["weighted_by"] is None and margin["value"] != .18
    profile = build_data_profile_schema(analysis_id="weighted", file_name="combined", statistics=stats,
        kpis=kpis, charts=[], forecasts=[], anomalies=[], recommendations=[], upload_context=relationship_context())
    assert profile["metrics"]["numeric_statistics"]["margin_pct"]["weighted_mean"] is None
    legacy = {"column": "margin_pct", "value": .18, "is_total": False, "weighted_by": "freight"}
    assert all(fact.get("values", {}).get("column") != "margin_pct" for fact in build_summary_facts(stats, [legacy]))
    assert stats["numeric_stats"] == original


def test_legacy_lookup_forecasts_do_not_become_summary_or_chat_evidence():
    stats = measured_statistics()
    stats["schema"] = annotate_measure_grain(stats["schema"], relationship_context())
    forecasts = [{"metric": column, "latest_value": 10,
                  "predictions": {"next_month": {"lower": 5, "upper": 15}}}
                 for column in ("quantity", "freight")]
    facts = build_summary_facts(stats, [], forecasts)
    forecast_columns = [fact["values"]["column"] for fact in facts if fact["id"].startswith("forecast_")]
    assert forecast_columns == ["quantity"]
    profile = build_data_profile_schema(analysis_id="legacy-forecast", file_name="combined", statistics=stats,
        kpis=[], charts=[], forecasts=[], anomalies=[], recommendations=[], upload_context=relationship_context())
    item = SimpleNamespace(row_count=3, column_count=4,
        metadata_={"schema": stats["schema"], "data_profile": profile, "upload_context": relationship_context(),
                   "forecasts": forecasts}, insights=[])
    chat_forecasts = [fact["values"]["column"] for fact in build_chat_facts(item)
                      if fact["id"].startswith("forecast_")]
    assert chat_forecasts == ["quantity"]


@pytest.mark.parametrize("domain", ["football", "clinic"])
async def test_domain_overrides_preserve_lookup_measure_guards(tmp_path, monkeypatch, domain):
    from datetime import date

    import polars as pl

    from app.services.analysis_engine import compute_analysis
    from app.services.file_processor import FileProcessor
    from app.services.semantic_wrangler import SemanticWrangler
    from evals.calibration.run_eval import _OfflineAIService

    if domain == "football":
        parent_column = "ast"
        data = {"player": ["First", "First", "Second"], "squad": ["A", "A", "B"],
                "comp": ["L", "L", "L"], "pos": ["M", "M", "F"], "gls": [1, 2, 3], "ast": [10, 10, 20]}
    else:
        parent_column = "wait_minutes"
        data = {"appointment_date": [date(2025, 1, day) for day in (1, 2, 3)],
                "clinic": ["A", "A", "B"], "appointment_status": ["Attended"] * 3, "wait_minutes": [5, 5, 30]}
    parquet = tmp_path / f"{domain}.parquet"
    pl.DataFrame(data).write_parquet(parquet)
    origin = relationship_context()["relationship_resolution"]["field_origins"]["freight"]
    context = {"relationship_resolution": {"status": "enriched", "field_origins": {parent_column: origin}}}

    async def display(*args, **kwargs):
        return {"columns": [], "charts": []}

    monkeypatch.setattr(SemanticWrangler, "build_display_metadata", display)
    result = await compute_analysis(file_processor=FileProcessor(), ai_service=_OfflineAIService(),
        storage_path=str(parquet), file_name=f"{domain} combined", analysis_id=f"grain-{domain}", upload_context=context)
    assert all(kpi["column"] != parent_column for kpi in result["kpis"])
    assert all(chart.get("xAxis") != parent_column and chart.get("yAxis") != parent_column for chart in result["charts"])
    assert parent_column not in result["profile_json"]["metrics"]["numeric_statistics"]
    if domain == "football":
        assert "40 assists" not in result["ai_result"]["executive_summary"]
def test_entity_key_provenance_uses_cleaned_schema_names():
    from app.analytics.measure_grain import annotate_measure_grain

    origin = {"kind": "lookup", "repeated": True, "entity_key_columns": ["Order ID related 2"]}
    context = {"relationship_resolution": {"field_origins": {"Freight": origin}},
               "cleaning": {"report": {"renamed_columns": {"Freight": "freight", "Order ID related 2": "order_id_related_2"}}}}
    result = annotate_measure_grain([{"name": "freight"}, {"name": "order_id_related_2"}], context)
    assert result[0]["measure_grain"]["entity_key_columns"] == ["order_id_related_2"]
    assert origin["entity_key_columns"] == ["Order ID related 2"]

