"""Cross-domain regressions: no fixture-specific dataset or column shortcuts."""

from datetime import date

import duckdb
import pytest

from app.analytics.chart_selector import select_charts
from app.analytics.forecasting import generate_forecasts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.line_presentation import present_time_line
from app.analytics.live_filter import populate_chart_option, requery_chart
from app.analytics.statistics import StatisticsEngine
from app.services.export_charts import PdfChart, normalise_charts
from app.services.export_service import _format_metric_value
from app.services.file_processor import FileProcessor
from app.services.semantic_wrangler import apply_display_metadata_to_charts


@pytest.mark.parametrize("metric", [
    "duration_ms", "danceability", "energy", "temperature", "confidence_score",
    "unit_price", "click_rate", "inventory_units", "cumulative_sales",
])
def test_attributes_never_become_sum_forecasts_even_with_wrong_kpi_type(metric):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data (event_date DATE, "{metric}" DOUBLE)')
        conn.executemany("INSERT INTO data VALUES (?, ?)", [
            (date(2025, month, 1), 100 + month * 10 + month % 3) for month in range(1, 13)
        ])
        schema = [{"name": "event_date", "is_date": True},
                  {"name": metric, "is_numeric": True, "analysis_role": "metric"}]
        assert generate_forecasts(conn, schema, [{"column": metric, "kpi_type": "revenue"}],
                                  reference_date=date(2026, 1, 5)) == []


@pytest.mark.parametrize("date_column", ["first_week", "release_date", "date_of_birth", "last_seen"])
def test_dense_catalogue_dates_do_not_forecast_activity(date_column):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data ("{date_column}" DATE, downloads DOUBLE)')
        conn.executemany("INSERT INTO data VALUES (?, ?)", [
            (date(2025, month, 1), 100 + month * 10 + month % 3) for month in range(1, 13)
        ])
        schema = [{"name": date_column, "is_date": True},
                  {"name": "downloads", "is_numeric": True, "analysis_role": "metric"}]
        assert generate_forecasts(conn, schema, [], reference_date=date(2026, 1, 5)) == []


@pytest.mark.parametrize("metric", ["revenue", "downloads", "page_views", "units_sold"])
@pytest.mark.parametrize("period", ["period_date", "week_start_date", "month_end_date"])
def test_observed_flows_still_forecast(metric, period):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data ("{period}" DATE, "{metric}" DOUBLE)')
        conn.executemany("INSERT INTO data VALUES (?, ?)", [
            (date(2025, month, 1), 100 + month * 10 + month % 3) for month in range(1, 13)
        ])
        schema = [{"name": period, "is_date": True},
                  {"name": metric, "is_numeric": True, "analysis_role": "metric"}]
        assert len(generate_forecasts(conn, schema, [], reference_date=date(2026, 1, 5))) == 1


@pytest.mark.parametrize("volume", ["streams", "downloads", "page_views"])
def test_catalogue_ranks_entities_by_activity_not_calendar_fragments(volume):
    with duckdb.connect() as conn:
        conn.execute(f"""CREATE TABLE data AS SELECT
            CAST(i % 28 + 1 AS INTEGER) AS published_day,
            CAST(i % 12 + 1 AS INTEGER) AS published_month,
            CAST(2000 + i % 24 AS INTEGER) AS published_year,
            'Item ' || i AS item_name,
            10000 + i AS {volume}, i % 97 + 0.2 AS quality_score FROM range(1000) t(i)""")
        stats = StatisticsEngine(conn).describe_all()
        schema = {column["name"]: column for column in stats["schema"]}
        assert schema["published_day"]["analysis_role"] == "dimension"
        assert schema["published_month"]["semantic_type"] == "month"
        kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
        assert kpis[0]["column"] == volume
        assert kpis[0]["is_total"]
        assert kpis[0]["value"] == 10499500
        assert not {"published_day", "published_month", "published_year"} & {k["column"] for k in kpis}
        charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"],
                               stats["date_range"], stats["correlations"])
        ranking = next(c for c in charts if c.get("type") == "bar" and c.get("yAxis") == "item_name")
        assert ranking["xAxis"] == volume
        populate_chart_option(conn, ranking)
        assert len(ranking["echarts_option"]["series"][0]["data"]) <= 15
        assert max(ranking["echarts_option"]["series"][0]["data"]) == 10999


@pytest.mark.parametrize("extension", [".csv", ".tsv", ".xlsx"])
def test_invalid_number_is_audited_separately_from_original_blank(tmp_path, extension):
    import pandas as pd

    frame = pd.DataFrame({"record": [f"Row {i}" for i in range(12)],
                          "downloads": [str(i) for i in range(10)] + ["bad source value", None]})
    source = tmp_path / f"input{extension}"
    if extension == ".xlsx":
        frame.to_excel(source, index=False)
    else:
        frame.to_csv(source, index=False, sep="\t" if extension == ".tsv" else ",")
    result = FileProcessor()._clean_file_sync(str(source), extension, str(tmp_path / "clean.parquet"),
                                            str(tmp_path / "clean.csv"), {})
    report = result["cleaning_report"]
    issues = report["source_quality"]["issues"]
    blank = next(i for i in issues if i["type"] == "missing_values")
    invalid = next(i for i in issues if i["type"] == "invalid_numeric_values")
    assert blank["affected_rows"] == 1
    assert invalid["affected_rows"] == 1
    assert invalid["examples"] == [{"table_row": 11, "value": "bad source value"}]
    assert "recorded_invalid_numeric_values" in report["steps"]
    assert result["row_count"] == 12


def test_donut_includes_unknown_and_other_categories_and_refreshes_denominator():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT CASE WHEN i < 2 THEN NULL ELSE 'Group ' || i END AS category FROM range(12) t(i)")
        chart = {"type": "donut", "description": "Category breakdown.", "echarts_option": {
            "_columns": {"category": "category"}, "series": [{"data": []}]}}
        populate_chart_option(conn, chart)
        assert sum(d["value"] for d in chart["echarts_option"]["series"][0]["data"]) == 12
        assert {d["name"] for d in chart["echarts_option"]["series"][0]["data"]} >= {"Not recorded", "Other categories"}
        assert "all 12 entries" in chart["description"]
        filtered = requery_chart(conn, chart, "category IS NOT NULL")
        assert "all 10 entries" in filtered["description"]
        assert "all 12 entries" not in filtered["description"]
        assert "have no recorded category" not in filtered["description"]


def test_scatter_separates_sampling_missing_and_nonpositive_exclusions():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT CASE WHEN i=501 THEN NULL ELSE i END AS x, i*2 AS y FROM range(502) t(i)")
        chart = {"type": "scatter", "echarts_option": {"_columns": {"x": "x", "y": "y"},
                 "series": [{"data": []}], "xAxis": {}, "yAxis": {}}}
        populate_chart_option(conn, chart)
        assert "1 entry is missing one of the two figures" in chart["description"]
        assert "first 500 of 501 entries with both figures filled in" in chart["description"]
        assert "nothing recorded" not in chart["description"]


@pytest.mark.parametrize(("value", "expected"), [(0.986533, "0.99"), (1.58132, "1.58"),
                          (66.96957, "66.97"), (489458828542, "489,458,828,542"), (0.000005, "0.000005")])
def test_fractional_metrics_keep_useful_precision(value, expected):
    assert _format_metric_value({"value": value}) == expected


def test_year_axis_cannot_be_relabelled_as_month_by_display_metadata():
    chart = {"id": "year", "type": "line", "xAxis": "published_year", "yAxis": "downloads",
             "aggregation": "sum", "echarts_option": {"_columns": {"x": "published_year", "time_grain": "year"},
             "xAxis": {"data": [2024, 2025]}, "yAxis": {"name": "Downloads"}, "series": [{"data": [20, 40]}]}}
    charts = apply_display_metadata_to_charts([chart], {"columns": [{"name": "published_year", "label": "Month"}]})
    result = present_time_line(charts[0])
    assert "month" not in result["echarts_option"]["xAxis"]["name"].lower()
    assert "their published year" in result["description"]
    assert "month" not in result["description"]


def test_logarithmic_scatter_exports_preserve_scale_and_source_values():
    import io
    import zipfile
    from unittest.mock import Mock

    from app.services.export_service import build_excel_report

    raw = {"type": "scatter", "title": "Activity", "echarts_option": {
        "_scale": {"x": True, "y": True},
        "series": [{"data": [[1, 1], [10, 10], [100, 100]]}]}}
    chart = normalise_charts([raw])[0]
    assert chart.x_log and chart.y_log
    assert chart.points == [(1, 1), (10, 10), (100, 100)]
    drawing = PdfChart(chart)
    drawing.canv = Mock()
    drawing.draw()
    # Equal multiplicative steps must be equally spaced on the PDF plot.
    coordinates = [call.args[:2] for call in drawing.canv.circle.call_args_list]
    assert coordinates[1][0] == pytest.approx((coordinates[0][0] + coordinates[2][0]) / 2)
    assert coordinates[1][1] == pytest.approx((coordinates[0][1] + coordinates[2][1]) / 2)
    workbook = build_excel_report(name="Activity", row_count=3, column_count=2,
                                  summary="", insights=[], charts=[raw])
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        assert archive.read("xl/charts/chart1.xml").count(b'<c:logBase val="10"') == 2


def test_explicit_percent_kpi_preserves_source_scale_in_summary():
    from app.analytics.summary_evidence import build_summary_facts

    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT 60.0 + i AS completion_pct FROM range(12) t(i)")
        statistics = StatisticsEngine(conn).describe_all()
        kpis = detect_kpis(statistics["schema"], statistics["numeric_stats"])
        assert kpis[0]["is_percent"]
        assert kpis[0]["value"] == 65.5
        facts = build_summary_facts(statistics, kpis, [])
        assert any("65.5%" in fact["text"] for fact in facts)


def test_wide_dataset_does_not_silently_drop_later_measures():
    with duckdb.connect() as conn:
        descriptors = ", ".join(f"i + {n} AS measurement_{n}" for n in range(25))
        conn.execute(f"CREATE TABLE data AS SELECT {descriptors}, 100 + i AS downloads FROM range(20) t(i)")
        stats = StatisticsEngine(conn).describe_all()
        assert len(stats["numeric_stats"]) == 26
        kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
        assert kpis[0]["column"] == "downloads"
        assert kpis[0]["value"] == 2190


def test_late_excel_error_cell_survives_sampling_for_the_conversion_audit(tmp_path):
    import pandas as pd

    source = tmp_path / "late-error.xlsx"
    values = [str(i) for i in range(1500)] + ["malformed numeric entry"]
    pd.DataFrame({"label": [f"Entry {i}" for i in range(len(values))], "views": values}).to_excel(source, index=False)
    result = FileProcessor()._clean_file_sync(str(source), ".xlsx", str(tmp_path / "clean.parquet"),
                                            str(tmp_path / "clean.csv"), {})
    issue = next(i for i in result["cleaning_report"]["source_quality"]["issues"] if i["type"] == "invalid_numeric_values")
    assert issue["examples"] == [{"table_row": 1501, "value": "malformed numeric entry"}]


def test_catalogue_line_is_explicitly_a_cohort_comparison():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT CAST(2020+i%5 AS INTEGER) AS release_year, 100+i AS downloads FROM range(50) t(i)")
        stats = StatisticsEngine(conn).describe_all()
        charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"], {}, {})
        chart = next(c for c in charts if c["type"] == "line")
        assert "over time" not in chart["title"].lower()
        populate_chart_option(conn, chart)
        result = present_time_line(chart)
        assert "cohort comparisons" in result["description"]


def test_summary_wording_distinguishes_source_percentages_outcomes_and_confidence():
    from app.services.report_language import present_insight

    percentage = present_insight({"type": "summary", "title": "Average completion", "data": {
        "column": "completion_pct", "value": 65.5, "is_percent": True, "kpi_type": "average"}})
    assert "percentages supplied" in percentage["description"]
    assert "marked 1" not in percentage["description"]
    outcome = present_insight({"type": "summary", "title": "Won", "data": {
        "column": "won", "value": 65.5, "is_percent": True, "kpi_type": "outcome_rate"}})
    assert "marked 1" in outcome["description"]
    confidence = present_insight({"type": "summary", "title": "Confidence", "data": {
        "column": "confidence_score", "value": 0.9865, "is_total": False, "kpi_type": "average"}})
    assert "not confidence in this analysis" in confidence["description"]


@pytest.mark.parametrize(("period", "metric"), [("first_week", "downloads"),
                          ("event_date", "duration_ms"), ("event_date", "quality_score")])
def test_monthly_sum_anomalies_follow_the_same_measure_and_date_rules(period, metric):
    from app.analytics.anomaly_detection import detect_anomalies

    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data ("{period}" DATE, "{metric}" DOUBLE)')
        conn.executemany("INSERT INTO data VALUES (?, ?)", [
            (date(2025, month, 1), 10000 if month == 12 else 10 + month % 3) for month in range(1, 13)])
        stats = StatisticsEngine(conn).describe_all()
        anomalies = detect_anomalies(conn, stats["schema"], stats["numeric_stats"])
        assert not any(item["type"] == "time_series_spike" for item in anomalies)
        assert any(item["type"] == "statistical_outlier" for item in anomalies)
