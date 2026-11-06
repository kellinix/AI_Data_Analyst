"""Behavioural checks for ambiguous codes, identifiers, dates and source gaps."""

from datetime import datetime
from types import SimpleNamespace

import duckdb
import polars as pl
import pytest

from app.analytics.anomaly_detection import detect_anomalies
from app.analytics.chart_selector import select_charts
from app.analytics.forecasting import generate_forecasts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.statistics import StatisticsEngine
from app.analytics.summary_evidence import build_summary_facts, render_summary
from app.services.chat_evidence import _friendly_fact, build_chat_facts
from app.services.data_profile import build_data_profile_schema
from app.services.file_processor import FileProcessor
from app.services.report_language import present_metadata


def analyse(conn):
    stats = StatisticsEngine(conn).describe_all()
    kpis = detect_kpis(stats["schema"], stats["numeric_stats"])
    charts = select_charts(stats["schema"], stats["numeric_stats"], stats["categorical_stats"],
                           stats["date_range"], stats["correlations"])
    return stats, kpis, charts


@pytest.mark.parametrize("identifier", ["UDI", "sequence", "opaque_reference"])
@pytest.mark.parametrize("start", [0, 1])
def test_unfamiliar_row_numbering_is_preserved_without_becoming_a_measure(identifier, start):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data AS SELECT i+{start} AS "{identifier}", '
                     "i+1 AS streams, 100+i*.5 AS temperature FROM range(40) t(i)")
        stats, kpis, charts = analyse(conn)
        assert stats["numeric_stats"][identifier]["count"] == 40
        assert next(c for c in stats["schema"] if c["name"] == identifier)["analysis_role"] == "identifier"
        assert identifier not in {k["column"] for k in kpis}
        assert {"streams", "temperature"} <= {k["column"] for k in kpis}
        assert not any(identifier in [c.get("xAxis"), c.get("yAxis")] for c in charts)
        assert conn.execute(f'SELECT MIN("{identifier}"), MAX("{identifier}") FROM data').fetchone() == (start, start+39)


@pytest.mark.parametrize("code", ["view", "click_code", "delivery_level"])
def test_bounded_activity_codes_are_dimensions_but_explicit_counts_still_sum(code):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data AS SELECT i%5 AS "{code}", i%5 AS page_views, '
                     "100000+i*500 AS price FROM range(60) t(i)")
        stats, kpis, charts = analyse(conn)
        assert next(c for c in stats["schema"] if c["name"] == code)["analysis_role"] == "dimension"
        assert code not in {k["column"] for k in kpis}
        assert next(k for k in kpis if k["column"] == "page_views")["value"] == 120
        assert next(k for k in kpis if k["column"] == "price")["is_total"] is False
        assert not any(code == (c.get("echarts_option") or {}).get("_columns", {}).get("value") for c in charts)


def test_fractional_readings_with_integer_endpoints_are_not_codes():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT (i%3)*.5 AS reading FROM range(30) t(i)")
        stats, _, _ = analyse(conn)
        assert stats["schema"][0]["analysis_role"] == "metric"


def test_price_charts_lead_unknown_attributes_without_displacing_revenue():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT i%5 AS view, i%5+1 AS bedrooms, 100000+i*500 AS sale_price, "
                     "DATE '2025-01-01'+CAST(i AS INTEGER) AS sale_date FROM range(60) t(i)")
        stats, kpis, charts = analyse(conn)
        assert kpis[0]["column"] == "sale_price"
        assert next(c for c in charts if c["type"] == "line")["yAxis"] == "sale_price"
        assert not any((c.get("echarts_option") or {}).get("_columns", {}).get("y") == "view" for c in charts)
        conn.execute("ALTER TABLE data ADD revenue DOUBLE")
        conn.execute("UPDATE data SET revenue = sale_price * 2")
        _, _, charts = analyse(conn)
        assert next(c for c in charts if c["type"] == "line")["yAxis"] == "revenue"


@pytest.mark.parametrize("measure", ["total", "reading", "temperature", "elapsed_minutes", "quantity"])
def test_sequential_values_do_not_override_an_explicit_measure_name(measure):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data AS SELECT i+1 AS "{measure}" FROM range(40) t(i)')
        stats, _, _ = analyse(conn)
        assert stats["schema"][0]["analysis_role"] == "metric"


@pytest.mark.parametrize("duration", ["pdays", "days_since_contact", "elapsed_minutes", "wait_duration"])
def test_negative_elapsed_codes_are_disclosed_and_not_used_in_decision_summaries(duration):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data AS SELECT CASE WHEN i<20 THEN -1 ELSE 10+i END AS "{duration}", '
                     "100+i AS revenue, DATE '2025-01-01'+CAST(i AS INTEGER) AS event_date FROM range(40) t(i)")
        stats, kpis, charts = analyse(conn)
        assert stats["numeric_stats"][duration]["count"] == 40
        assert stats["numeric_stats"][duration]["min"] == -1
        assert duration not in {k["column"] for k in kpis}
        assert not any(duration in [c.get("xAxis"), c.get("yAxis")] for c in charts)
        assert not any(a.get("column") == duration for a in detect_anomalies(conn, stats["schema"], stats["numeric_stats"]))
        assert not any(f.get("metric") == duration for f in generate_forecasts(conn, stats["schema"], kpis))
        facts = build_summary_facts(stats, kpis)
        warning = next(f for f in facts if f["id"].startswith("unresolved_measure_"))
        assert warning["required"] and warning["values"]["affected_rows"] == 20
        assert "Confirm their meaning" in _friendly_fact(warning)
        assert "unresolved_duration_codes" in {issue["type"] for issue in stats["data_quality"]["issues"]}
        profile = build_data_profile_schema(analysis_id="test", file_name="data.csv", statistics=stats,
            kpis=kpis, charts=charts, forecasts=[], anomalies=[], recommendations=[], upload_context={})
        metadata = {**stats, "forecasts": [], "data_profile": profile}
        chat = build_chat_facts(SimpleNamespace(metadata_=metadata, insights=[], row_count=40, column_count=3))
        assert any(f["id"].startswith("unresolved_measure_") for f in chat)
        assert not any(f.get("values", {}).get("column") == duration and f.get("values", {}).get("operation") for f in chat)


@pytest.mark.parametrize("measure", ["balance", "temperature", "time_offset", "duration_delta"])
def test_signed_measures_are_not_silently_deleted_or_reinterpreted(measure):
    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE data AS SELECT i-20 AS "{measure}" FROM range(40) t(i)')
        stats, _, _ = analyse(conn)
        assert "aggregation_warning" not in stats["numeric_stats"][measure]
        assert stats["numeric_stats"][measure]["count"] == 40
        assert stats["numeric_stats"][measure]["mean"] == -.5


@pytest.mark.parametrize("compact", ["20240102T153045", "20240102T153045Z", "20240102T153045+0130", "20240102"])
def test_compact_dates_keep_their_time_and_invalid_entries_are_separately_audited(tmp_path, compact):
    source = tmp_path / "source.csv"
    source.write_text("event_date,reference,amount\n" + "\n".join(
        f"{compact if i<9 else '20240230T153045'},20240102,{10+i}" for i in range(10)), encoding="utf-8")
    processor = FileProcessor()
    result = processor._clean_file_sync(str(source), ".csv", str(tmp_path / "clean.parquet"), str(tmp_path / "clean.csv"), {})
    data = pl.read_parquet(tmp_path / "clean.parquet")
    assert data["event_date"].null_count() == 1
    value = data["event_date"][0]
    if "T" in compact:
        assert isinstance(value, datetime)
        assert (value.hour, value.minute, value.second) == ((14, 0, 45) if "+0130" in compact else (15, 30, 45))
    else:
        assert value.isoformat().startswith("2024-01-02")
    assert "date" not in str(data["reference"].dtype).lower()
    issues = result["cleaning_report"]["source_quality"]["issues"]
    invalid = next(issue for issue in issues if issue["type"] == "invalid_date_values")
    assert invalid["affected_rows"] == 1
    assert invalid["examples"] == [{"table_row": 10, "value": "20240230T153045"}]
    assert not any(issue["type"] == "missing_values" for issue in issues)


def test_fully_numeric_compact_date_is_not_confused_with_an_eight_digit_id(tmp_path):
    source = tmp_path / "compact.csv"
    source.write_text("sale_date,account_id,amount\n20240102,20240102,100\n20240203,20240203,200\n", encoding="utf-8")
    FileProcessor()._clean_file_sync(str(source), ".csv", str(tmp_path / "clean.parquet"), str(tmp_path / "clean.csv"), {})
    frame = pl.read_parquet(tmp_path / "clean.parquet")
    assert frame["sale_date"].to_list()[0].isoformat() == "2024-01-02"
    assert frame["account_id"].to_list() == ["20240102", "20240203"]


@pytest.mark.parametrize("extension", [".csv", ".xlsx", ".json", ".parquet"])
def test_source_markers_blanks_and_failed_conversions_stay_distinct(tmp_path, extension):
    import pandas as pd

    data = {"group": ["unknown"]*8 + ["N/A", "", "A", "B"],
            "downloads": [str(i) for i in range(10)] + ["bad-number", None]}
    source = tmp_path / f"source{extension}"
    frame = pl.DataFrame(data)
    if extension == ".csv":
        frame.write_csv(source)
    elif extension == ".json":
        frame.write_json(source)
    elif extension == ".parquet":
        frame.write_parquet(source)
    else:
        pd.DataFrame(data).to_excel(source, index=False)
    result = FileProcessor()._clean_file_sync(str(source), extension, str(tmp_path / "clean.parquet"), str(tmp_path / "clean.csv"), {})
    report = result["cleaning_report"]
    issues = report["source_quality"]["issues"]
    marker = next(i for i in issues if i["type"] == "missing_value_markers")
    assert marker["affected_rows"] == 9
    assert marker["markers"] == [{"value": "N/A", "count": 1}, {"value": "unknown", "count": 8}]
    assert next(i for i in issues if i["type"] == "missing_values" and i["column"] == "group")["affected_rows"] == 1
    assert next(i for i in issues if i["type"] == "invalid_numeric_values")["affected_rows"] == 1
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM read_parquet(?)", [str(tmp_path / "clean.parquet")])
        stats = StatisticsEngine(conn).describe_all()
    stats["data_quality"]["source_quality"] = report["source_quality"]
    context = {"cleaning": {"report": report}}
    facts = build_summary_facts(stats, [], upload_context=context)
    gap = next(f for f in facts if f["id"] == "missing")
    assert gap["values"]["missing_kind"] == "supplied_marker"
    assert "not blank cells" in _friendly_fact(gap)
    summary, checks = render_summary(facts)
    meta = {**stats, "analysis_evidence": {"summary_checks": checks}, "upload_context": context}
    presented, text = present_metadata(meta, summary)
    assert "supplied missing-value markers" in text
    assert "is blank in 9" not in text
    assert "not blank cells" in next(i for i in presented["data_quality"]["source_quality"]["issues"] if i["type"] == "missing_value_markers")["description"]
