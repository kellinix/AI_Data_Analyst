from copy import deepcopy

import pytest

from app.analytics.kpi_detector import detect_kpis
from app.analytics.percentage_scale import SCALE_WARNING, clarify_percentage_display
from app.analytics.semantic_detector import enrich_schema_with_semantics
from app.analytics.summary_evidence import build_summary_facts
from app.services.chat_evidence import friendly_chat_content
from app.services.data_profile import build_data_profile_schema
from app.services.semantic_wrangler import (
    apply_display_metadata_to_charts,
    apply_display_metadata_to_statistics,
)


@pytest.mark.parametrize("name", ["EmployeeNumber", "employeenumber", "employee_number", "PatientNumber", "customernumber", "PolicyNo", "flight", "FlightNumber"])
def test_named_identifier_numbers_do_not_become_measurements(name):
    stats = {name: {"min": 5, "max": 200, "unique_count": 100, "count": 100, "mean": 101, "total": 10100}}
    schema = enrich_schema_with_semantics([{"name": name, "dtype": "BIGINT", "is_numeric": True}], stats, {})
    assert schema[0]["analysis_role"] == "identifier"
    assert not detect_kpis(schema, stats)


def test_quantity_counts_keep_their_metric_role():
    stats = {"number_of_employees": {"min": 10, "max": 500, "unique_count": 30, "count": 100}}
    schema = enrich_schema_with_semantics([{"name": "number_of_employees", "dtype": "BIGINT", "is_numeric": True}], stats, {})
    assert schema[0]["analysis_role"] == "metric"


def test_season_labels_are_groups_and_real_phone_values_remain_identifiers():
    schema = [{"name": name, "dtype": "VARCHAR", "is_numeric": False} for name in ("season", "contact")]
    categories = {"season": {"unique_count": 27, "top_values": [{"value": "2021-22"}, {"value": "2022-23"}]},
                  "contact": {"unique_count": 2, "top_values": [{"value": "555-0123"}, {"value": "555-1234"}]}}
    enriched = {item["name"]: item for item in enrich_schema_with_semantics(schema, {}, categories)}
    assert enriched["season"]["analysis_role"] == "dimension"
    assert enriched["contact"]["semantic_type"] == "phone"


def ambiguous_stats():
    numeric = {"share_pct": {"min": .01, "max": .09, "mean": .05, "total": 5., "count": 100}}
    schema = enrich_schema_with_semantics([{"name": "share_pct", "dtype": "DOUBLE", "is_numeric": True}], numeric, {})
    return {"schema": schema, "numeric_stats": numeric, "row_count": 100, "column_count": 1}


def test_unknown_percentage_scale_is_preserved_and_disclosed_everywhere():
    statistics = ambiguous_stats()
    original = deepcopy(statistics["numeric_stats"])
    kpis = detect_kpis(statistics["schema"], statistics["numeric_stats"])
    assert kpis[0]["value"] == .05
    assert not kpis[0]["is_percent"]
    assert kpis[0]["percentage_scale"] == "unconfirmed"
    facts = build_summary_facts(statistics, kpis)
    fact = next(item for item in facts if item["id"].startswith("metric_"))
    assert "0.05%" not in fact["text"]
    assert "raw scale" in fact["text"] and SCALE_WARNING in fact["text"]
    assert SCALE_WARNING in friendly_chat_content([fact])
    profile = build_data_profile_schema(analysis_id="scale", file_name="data.csv", statistics=statistics,
        kpis=kpis, charts=[], forecasts=[], anomalies=[], recommendations=[], upload_context={})
    assert profile["columns"][0]["percentage_scale"] == "unconfirmed"
    assert profile["metrics"]["kpis"][0]["display_warning"] == SCALE_WARNING
    assert statistics["numeric_stats"] == original


def test_raw_scale_warning_and_label_reach_chart_axes():
    statistics = ambiguous_stats()
    charts = [{"id": "share", "type": "bar", "xAxis": "share_pct", "yAxis": "region", "aggregation": "average",
               "echarts_option": {"xAxis": {}, "yAxis": {}, "series": [{"name": "share_pct", "data": [.05]}]}}]
    display = {"columns": [{"name": "share_pct", "label": "Share %"}, {"name": "region", "label": "Region"}],
               "charts": [{"id": "share", "title": "Average Share %", "description": "Share % by region."}]}
    clarify_percentage_display(statistics, display, charts)
    displayed = apply_display_metadata_to_charts(charts, display)[0]
    assert "raw scale" in displayed["title"] and "%" not in displayed["title"]
    assert "raw scale" in displayed["echarts_option"]["xAxis"]["name"]
    assert SCALE_WARNING in displayed["description"]
    assert displayed["echarts_option"]["series"][0]["data"] == [.05]
    assert apply_display_metadata_to_statistics(statistics, display)["schema"][0]["display_warning"] == SCALE_WARNING


def test_small_unlabelled_measure_is_not_invented_as_a_percentage():
    numeric = {"x1": {"min": .1, "max": .9, "mean": .5, "count": 100, "unique_count": 20}}
    schema = enrich_schema_with_semantics([{"name": "x1", "dtype": "DOUBLE", "is_numeric": True}], numeric, {})
    assert schema[0]["semantic_type"] == "numeric_metric"
    assert not detect_kpis(schema, numeric)[0].get("is_percent")


def test_percentage_scale_is_not_assumed_from_a_few_values_above_one():
    statistics = ambiguous_stats()
    statistics["numeric_stats"]["share_pct"].update({"max": 1.5, "p25": .48, "p75": .56})
    kpi = detect_kpis(statistics["schema"], statistics["numeric_stats"])[0]
    assert not kpi["is_percent"] and kpi["percentage_scale"] == "unconfirmed"


def test_sport_or_lab_abbreviations_do_not_invent_football_counts():
    stats = {name: {"min": 0, "max": 12, "count": 100, "unique_count": 8} for name in ("ast", "gls", "mp")}
    schema = enrich_schema_with_semantics([{"name": name, "dtype": "DOUBLE", "is_numeric": True} for name in stats], stats, {})
    assert all(column["analysis_role"] == "metric" for column in schema)
    assert all(column["semantic_type"] != "count" and "football" not in column["semantic_reason"] for column in schema)


@pytest.mark.parametrize("minimum, maximum, mean, is_percent", [(.1, .4, .2, False), (10, 40, 20, True)])
def test_profit_percentage_is_never_formatted_as_money(minimum, maximum, mean, is_percent):
    stats = {"profit_margin_pct": {"min": minimum, "max": maximum, "mean": mean, "total": mean * 100, "count": 100}}
    schema = enrich_schema_with_semantics([{"name": "profit_margin_pct", "dtype": "DOUBLE", "is_numeric": True}], stats, {})
    assert schema[0]["semantic_type"] == "percentage"
    kpi = detect_kpis(schema, stats)[0]
    assert kpi["is_percent"] is is_percent
    assert kpi["is_currency"] is False
    assert kpi["value"] == mean


def test_declared_survey_and_existing_admission_scales_stay_supported():
    survey_schema = [{"name": name, "is_numeric": name == "percentage"} for name in (
        "country", "questioncode", "questionlabel", "answer", "percentage", "subset")]
    survey = enrich_schema_with_semantics(survey_schema, {"percentage": {"min": .1, "max": .9}}, {})
    assert not next(item for item in survey if item["name"] == "percentage").get("percentage_scale")
    numeric = {"chance_of_admit": {"min": .3, "max": .9, "mean": .6, "total": 60, "count": 100}}
    kpis = detect_kpis([{"name": "chance_of_admit", "is_numeric": True, "analysis_role": "metric"}], numeric)
    assert kpis[0]["value"] == 60
    assert kpis[0]["is_percent"] and kpis[0]["display_multiplier"] == 100
