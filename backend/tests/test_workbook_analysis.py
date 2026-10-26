"""Regression cases for operational workbooks with notes, serials and optional fields."""
from datetime import date

import duckdb
import polars as pl

from app.analytics.chart_selector import select_charts
from app.analytics.chart_specs import build_visual_spec
from app.analytics.data_quality import _quality_score
from app.analytics.forecasting import generate_forecasts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.live_filter import build_where_clause, populate_chart_option
from app.analytics.statistics import StatisticsEngine
from app.services.analysis_engine import _summary_without_unverified_currency
from app.services.file_processor import FileProcessor, _parse_mixed_datetime_series


def test_notes_sheet_does_not_inflate_records_and_dates_survive_header_promotion():
    raw = pl.DataFrame({
        "column_1": ["3", "Sr #", "1", "2", "3"],
        "column_2": ["3", "Service Order Dates", "2022-02-28 00:00:00", "2023-02-28 00:00:00", "2025-02-28 00:00:00"],
        "column_3": ["3", "Region", "North West", "South West", "North West"],
    })
    report = {}
    table = FileProcessor()._normalize_excel_sheets({
        "Empty": pl.DataFrame(), "Orders": raw,
        "Objectives": pl.DataFrame({"Objective": ["Build a dashboard"], "Explanation": ["Notes only"]}),
    }, report)
    assert table.height == 3
    assert table["Service Order Dates"].dtype in {pl.Date, pl.Datetime("us"), pl.Datetime("ns")}
    assert table["Service Order Dates"][0].date() == date(2022, 2, 28)
    assert report["included_sheets"] == ["Orders"]
    assert report["excluded_sheets"][0]["name"] == "Objectives"


def test_serials_are_identifiers_and_constant_sla_is_not_summed_or_charted():
    with duckdb.connect() as conn:
        conn.execute('CREATE TABLE data AS SELECT i AS "Sr #", i + 10 AS "Sr #_2", 120 AS "Project SLA Duration Days", 40 AS "Tower Height M", CASE WHEN i % 2 = 0 THEN \'Active\' ELSE \'Cancelled\' END AS status FROM range(1, 31) t(i)')
        stats = StatisticsEngine(conn).describe_all()
        stats["schema"].append({"name": "optional_measure", "is_numeric": True, "is_date": False, "analysis_role": "metric"})
        stats["numeric_stats"]["optional_measure"] = {"count": 0, "null_count": 30, "min": None, "max": None}
        roles = {c["name"]: c["analysis_role"] for c in stats["schema"]}
        assert roles["Sr #"] == roles["Sr #_2"] == "identifier"
        assert roles["Tower Height M"] == "attribute"
        assert not stats["correlations"]
        sla = next(k for k in detect_kpis(stats["schema"], stats["numeric_stats"]) if k["column"] == "Project SLA Duration Days")
        assert sla["value"] == 120 and not sla["is_total"]
        charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"], stats["date_range"], stats["correlations"])
        assert any(c.get("aggregation") == "count" for c in charts)
        assert not any(c["type"] in {"scatter", "line", "histogram"} for c in charts)


def test_geography_counts_and_filters_use_the_same_groups():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES ('North West'), (' north-west '), ('NORTH  WEST'), ('South West')) t(region)")
        stats = StatisticsEngine(conn).describe_all()
        assert stats["categorical_stats"]["region"]["unique_count"] == 2
        assert stats["categorical_stats"]["region"]["top_values"][0] == {"value": "North West", "count": 3}
        charts = select_charts(stats["schema"], {}, stats["categorical_stats"], {}, {})
        chart = next(c for c in charts if c.get("aggregation") == "count")
        where, params = build_where_clause([{"column": "region", "op": "in", "values": ["North West"]}])
        assert populate_chart_option(conn, chart, where, params)
        assert chart["echarts_option"]["yAxis"]["data"] == ["North West"]
        assert chart["echarts_option"]["series"][0]["data"] == [3]


def test_optional_empty_columns_do_not_compound_the_score_penalty():
    issue = {"type": "missing_values", "severity": "critical", "affected_rows": 60}
    empty = {"type": "empty_field", "severity": "low", "affected_rows": 100}
    assert _quality_score(100, [issue]) == _quality_score(100, [issue] * 20 + [empty] * 20)
    assert _quality_score(100, [empty]) == 100


def test_grouped_averages_and_missing_values_survive_visual_specs():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES ('A', 'Open', 10.0), ('A', 'Open', 30.0), ('B', 'Closed', 50.0)) t(region, status, duration)")
        chart = {"type": "bar", "aggregation": "average", "echarts_option": {
            "xAxis": {}, "yAxis": {}, "_columns": {"x": "region", "y": "duration", "series_by": "status", "aggregation": "average"},
        }}
        assert populate_chart_option(conn, chart)
        assert all("stack" not in s for s in chart["echarts_option"]["series"])
        spec = build_visual_spec(chart)
        assert spec["encoding"]["y"]["stack"] is None
        assert any(row["value"] is None for row in spec["data"]["values"])
        assert any(row["value"] == 20 for row in spec["data"]["values"])


def test_unambiguous_dates_choose_the_order_for_ambiguous_rows():
    european, report = _parse_mixed_datetime_series(
        pl.Series("Date", ["05-02-2010", "24-12-2010", "10-01-2011"]), "Date"
    )
    assert report["strategy"] == "day_first"
    assert european.to_list() == [date(2010, 2, 5), date(2010, 12, 24), date(2011, 1, 10)]

    american, report = _parse_mixed_datetime_series(
        pl.Series("Date", ["02-05-2010", "12-24-2010", "01-10-2011"]), "Date"
    )
    assert report["strategy"] == "month_first"
    assert american.to_list() == [date(2010, 2, 5), date(2010, 12, 24), date(2011, 1, 10)]


def test_store_is_a_group_and_prices_are_means_not_sales():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES (1, 100.0, 3.0), (2, 200.0, 4.0), (1, 150.0, 5.0)) t(store, weekly_sales, fuel_price)")
        stats = StatisticsEngine(conn).describe_all()
        roles = {c["name"]: c["analysis_role"] for c in stats["schema"]}
        assert roles["store"] == "dimension"
        kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
        fuel = next(k for k in kpis if k["column"] == "fuel_price")
        assert fuel["value"] == 4.0 and not fuel["is_total"]
        assert all(k["column"] != "store" for k in kpis)
        charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"], {}, {})
        assert any(c.get("yAxis") == "store" and c.get("xAxis") == "weekly_sales" for c in charts)
        assert not any(c.get("xAxis") == "store" and c.get("yAxis") == "weekly_sales" and c.get("type") == "scatter" for c in charts)


def test_holiday_comparison_uses_average_per_record():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES (1, 0, 100.0), (2, 0, 100.0), (1, 1, 150.0)) t(store, holiday_flag, weekly_sales)")
        stats = StatisticsEngine(conn).describe_all()
        charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"], {}, {})
        chart = next(c for c in charts if c.get("yAxis") == "holiday_flag" and c.get("xAxis") == "weekly_sales")
        assert chart["aggregation"] == "average"
        assert populate_chart_option(conn, chart)
        assert sorted(chart["echarts_option"]["series"][0]["data"]) == [100.0, 150.0]


def test_unstable_monthly_trend_does_not_claim_directional_change():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT CAST('2020-01-01' AS DATE) + i * INTERVAL 1 MONTH AS date, CASE WHEN i % 2 = 0 THEN 100.0 ELSE 220.0 END AS weekly_sales FROM range(18) t(i)")
        stats = StatisticsEngine(conn).describe_all()
        kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
        forecasts = generate_forecasts(conn, stats["schema"], kpis)
        assert len(forecasts) == 1
        assert forecasts[0]["change_direction_supported"] is False


def test_unknown_currency_symbol_is_removed_from_generated_summary():
    summary = "One entry reached $3,818,686.45; another reached £12."
    assert _summary_without_unverified_currency(summary, None) == "One entry reached 3,818,686.45; another reached 12."
    assert _summary_without_unverified_currency(summary, {"code": "USD"}) == summary
