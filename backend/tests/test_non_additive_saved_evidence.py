from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.analytics.kpi_detector import detect_kpis, uses_average_aggregation
from app.analytics.measure_semantics import is_power_reading
from app.analytics.percentage_scale import SCALE_WARNING
from app.analytics.summary_evidence import build_summary_facts
from app.services.chat_evidence import build_chat_facts, friendly_chat_content


def saved_analysis(column, field=None):
    schema = [{"name": column, "is_numeric": True, "analysis_role": "metric", **(field or {})}]
    numeric = {"count": 3, "total": 60., "mean": 20., "min": 10., "max": 30.}
    return SimpleNamespace(
        name="Readings", row_count=3, column_count=1,
        summary="An old unsafe total must not become current evidence.",
        insights=[SimpleNamespace(type="summary", data={"column": column, "value": 60., "is_total": True})],
        metadata_={"schema": schema, "data_profile": {"columns": [
            {"name": column, "numeric_summary": numeric}], "categories": {}}},
    )


@pytest.mark.parametrize("column, field", [
    ("aep_mw", {}), ("load_kw", {}), ("PowerWatts", {}), ("power_w", {}),
    ("reading", {"unit": "W"}), ("reading", {"display_unit": "MW"}),
    ("share_pct", {}), ("conversion_rate", {}), ("percentage", {}), ("margin%", {}),
    ("cgpa", {}), ("gpa", {}), ("measurement", {"semantic_type": "average_metric"}),
    ("measurement", {"semantic_type": "percentage"}),
])
def test_non_additive_raw_and_legacy_totals_never_enter_chat_catalogue(column, field):
    item = saved_analysis(column, field)
    original = deepcopy(item.metadata_)
    facts = build_chat_facts(item)
    measured = [fact for fact in facts if fact["values"].get("column") == column]
    assert {fact["values"]["operation"] for fact in measured} == {"mean", "min", "max"}
    assert next(fact for fact in measured if fact["values"]["operation"] == "mean")["values"]["value"] == 20.
    assert all("SUM(" not in fact["calculation"] and "TOTAL(" not in fact["calculation"] for fact in facts)
    assert item.metadata_ == original


@pytest.mark.parametrize("column", ["energy_mwh", "consumption_kwh", "kilowatt_hours", "W", "price", "sale_price"])
def test_energy_wins_and_sale_price_totals_remain_available(column):
    item = saved_analysis(column)
    facts = build_chat_facts(item)
    total = next(fact for fact in facts if fact["values"].get("operation") == "total")
    assert total["values"]["column"] == column and total["values"]["value"] == 60.
    assert not is_power_reading(column)


def test_summary_legacy_power_total_is_filtered_and_mean_remains_available():
    stats = {"row_count": 3, "column_count": 1,
             "schema": [{"name": "aep_mw", "analysis_role": "metric"}],
             "numeric_stats": {"aep_mw": {"total": 60., "mean": 20., "count": 3}}}
    facts = build_summary_facts(stats, [
        {"column": "aep_mw", "value": 60., "is_total": True},
        {"column": "aep_mw", "value": 20., "is_total": False},
    ])
    measured = [fact for fact in facts if fact["values"].get("column") == "aep_mw"]
    assert len(measured) == 1 and measured[0]["values"]["operation"] == "mean"
    assert measured[0]["values"]["value"] == 20.


@pytest.mark.parametrize("column, field", [("sales_mw", {}), ("sales", {"unit": "MW"}),
                                           ("sales_rate", {}), ("sales", {"semantic_type": "average_metric"})])
def test_classified_kpis_cannot_override_power_or_average_semantics(column, field):
    schema = [{"name": column, "is_numeric": True, "analysis_role": "metric", **field}]
    numeric = {column: {"total": 60., "mean": 20., "count": 3}}
    kpi = detect_kpis(schema, numeric)[0]
    assert kpi["value"] == 20. and not kpi["is_total"]
    if is_power_reading(column, field):
        assert not kpi["is_currency"]
    numeric[column].pop("mean")
    assert not detect_kpis(schema, numeric)


def test_named_power_aggregation_stays_consistent_for_charts_and_kpis():
    assert uses_average_aggregation("sales_mw")
    assert not uses_average_aggregation("kwh_consumed")


def test_raw_fraction_warning_survives_without_a_saved_kpi():
    item = saved_analysis("share_pct", {"semantic_type": "percentage", "percentage_scale": "unconfirmed",
                                         "display_warning": SCALE_WARNING})
    item.insights = []
    item.metadata_["data_profile"]["columns"][0]["numeric_summary"].update(
        {"total": .15, "mean": .05, "min": .01, "max": .09})
    facts = build_chat_facts(item)
    mean = next(fact for fact in facts if fact["values"].get("operation") == "mean")
    content = friendly_chat_content([mean])
    assert "raw scale" in content and SCALE_WARNING in content
    assert "0.05%" not in content and mean["values"]["value"] == .05
