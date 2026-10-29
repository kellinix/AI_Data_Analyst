from __future__ import annotations

import duckdb
import pytest

from app.analytics.chart_selector import _time_series_chart
from app.analytics.line_presentation import present_time_line
from app.analytics.live_filter import (
    FilterValidationError,
    _histogram_edges,
    _is_log_worthy,
    build_where_clause,
    populate_chart_option,
    recompute_kpi,
    requery_chart,
    validate_filters,
)
from app.api.v1.endpoints.analyses import _derive_filterable_columns


def test_long_daily_series_keeps_all_dates_by_grouping_full_months():
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE data AS SELECT DATE '2025-01-01' + CAST(i AS INTEGER) AS sale_date, 1.0 AS revenue FROM range(180) t(i)")
        chart = _time_series_chart("sale_date", "revenue")
        populate_chart_option(conn, chart)
        option = chart["echarts_option"]
        assert option["_columns"]["time_grain"] == "month"
        assert len(option["xAxis"]["data"]) == 6
        assert sum(option["series"][0]["data"]) == 180
        assert "each month" in present_time_line(chart)["description"]
        populate_chart_option(conn, chart, '"sale_date" >= ?', ["2025-04-01"])
        assert sum(option["series"][0]["data"]) == 90


def test_monthly_chart_warns_when_last_month_has_few_recorded_dates():
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE data AS SELECT DATE '2026-01-01' + CAST(i AS INTEGER) AS sale_date, 1.0 AS revenue FROM range(120) t(i) UNION ALL SELECT DATE '2026-05-01', 5.0")
        chart = _time_series_chart("sale_date", "revenue")
        populate_chart_option(conn, chart)
    option = chart["echarts_option"]
    assert sum(option["series"][0]["data"]) == 125
    assert option["_columns"]["partial_last_month"]
    assert "may be incomplete" in present_time_line(chart)["description"]

SCHEMA = [
    {"name": "cp", "is_numeric": True, "analysis_role": "dimension"},
    {"name": "sex", "is_numeric": True, "analysis_role": "flag"},
    {"name": "chol", "is_numeric": True, "analysis_role": "metric"},
    {"name": "patient_id", "is_numeric": True, "analysis_role": "identifier"},
    {"name": "recorded_at", "is_numeric": False, "analysis_role": "temporal_dimension"},
]


def test_validate_filters_rejects_unknown_column():
    with pytest.raises(FilterValidationError):
        validate_filters([{"column": "nope", "op": "in", "values": ["1"]}], SCHEMA)


def test_validate_filters_rejects_identifier_role():
    with pytest.raises(FilterValidationError):
        validate_filters([{"column": "patient_id", "op": "in", "values": ["1"]}], SCHEMA)


def test_validate_filters_rejects_temporal_role():
    with pytest.raises(FilterValidationError):
        validate_filters([{"column": "recorded_at", "op": "in", "values": ["2024-01-01"]}], SCHEMA)


def test_date_range_recalculates_sales_without_model_inference():
    schema = [{"name": "sale_date", "is_date": True, "is_numeric": False,
               "analysis_role": "temporal_dimension"}]
    filters = validate_filters(
        [{"column": "sale_date", "op": "date_between", "values": ["2024-02-01", "2024-02-29"]}],
        schema,
    )
    sql, params = build_where_clause(filters)
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES (DATE '2024-01-31', 10.0), (DATE '2024-02-01', 20.0), (DATE '2024-02-29', 30.0), (DATE '2024-03-01', 40.0)) t(sale_date, sales)")
        assert conn.execute(f"SELECT COUNT(*) FROM data WHERE {sql}", params).fetchone()[0] == 2
        assert recompute_kpi(conn, "sales", is_total=True, is_percent=False,
                             filter_sql=sql, filter_params=params) == 50.0


def test_filtered_weighted_kpi_keeps_its_original_definition():
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES ('North', 10.0, 100.0), ('North', 50.0, 900.0), ('South', 90.0, 1000.0)) t(region, margin_pct, revenue)")
        sql, params = build_where_clause([
            {"column": "region", "op": "in", "values": ["North"]}
        ])
        assert recompute_kpi(conn, "margin_pct", is_total=False, is_percent=False,
                             filter_sql=sql, filter_params=params, weighted_by="revenue") == 46.0
        assert recompute_kpi(conn, "margin_pct", is_total=False, is_percent=False,
                             filter_sql='CAST("region" AS VARCHAR) IN (?)',
                             filter_params=["Missing"], weighted_by="revenue") is None


@pytest.mark.parametrize("values", [
    ["2024-02-30", "2024-03-01"], ["2024-03-01", "2024-02-01"],
    ["2024-02-01"], ["2024-02-01' OR true --", "2024-03-01"],
])
def test_date_range_rejects_invalid_or_reversed_dates(values):
    schema = [{"name": "sale_date", "is_date": True, "analysis_role": "temporal_dimension"}]
    with pytest.raises(FilterValidationError):
        validate_filters([{"column": "sale_date", "op": "date_between", "values": values}], schema)


def test_date_filter_suggested_from_saved_profile():
    metadata = {"data_profile": {"columns": [
        {"name": "sale_date", "display_label": "Sale Date", "is_date": True,
         "analysis_role": "temporal_dimension"},
    ]}, "date_range": {"sale_date": {"min": "2024-01-01", "max": "2024-03-31"}}}
    result = _derive_filterable_columns(metadata)
    assert [(c.column, c.kind, c.min_date, c.max_date) for c in result] == [
        ("sale_date", "date", "2024-01-01", "2024-03-31")
    ]


def test_validate_filters_rejects_between_on_non_numeric():
    schema = [{"name": "region", "is_numeric": False, "analysis_role": "dimension"}]
    with pytest.raises(FilterValidationError):
        validate_filters([{"column": "region", "op": "between", "values": [1, 2]}], schema)


@pytest.mark.parametrize("values", [
    [2, 1], [1], [1, 2, 3], [True, 2], ["1", 2], [float("inf"), 2],
])
def test_numeric_range_rejects_invalid_bounds(values):
    with pytest.raises(FilterValidationError):
        validate_filters([{"column": "chol", "op": "between", "values": values}], SCHEMA)


def test_numeric_range_recalculates_filtered_total():
    filters = validate_filters([{"column": "chol", "op": "between", "values": [100, 200]}], SCHEMA)
    sql, params = build_where_clause(filters)
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES (90, 10.0), (100, 20.0), (200, 30.0), (201, 40.0)) t(chol, sales)")
        assert conn.execute(f"SELECT COUNT(*) FROM data WHERE {sql}", params).fetchone()[0] == 2
        assert recompute_kpi(conn, "sales", is_total=True, is_percent=False,
                             filter_sql=sql, filter_params=params) == 50.0


def test_validate_filters_accepts_known_dimension():
    validated = validate_filters([{"column": "cp", "op": "in", "values": ["0", "2"]}], SCHEMA)
    assert len(validated) == 1


def test_validate_filters_drops_empty_values_without_raising():
    validated = validate_filters([{"column": "cp", "op": "in", "values": []}], SCHEMA)
    assert validated == []


def test_build_where_clause_in_op():
    sql, params = build_where_clause([{"column": "cp", "op": "in", "values": [0, 2]}])
    assert sql == 'CAST("cp" AS VARCHAR) IN (?, ?)'
    assert params == ["0", "2"]


def test_build_where_clause_between_op():
    sql, params = build_where_clause([{"column": "chol", "op": "between", "values": [100, 200]}])
    assert sql == '"chol" BETWEEN ? AND ?'
    assert params == [100, 200]


def test_build_where_clause_multiple_filters_anded():
    sql, params = build_where_clause([
        {"column": "cp", "op": "in", "values": [0]},
        {"column": "chol", "op": "between", "values": [100, 200]},
    ])
    assert sql == 'CAST("cp" AS VARCHAR) IN (?) AND "chol" BETWEEN ? AND ?'
    assert params == ["0", 100, 200]


def test_build_where_clause_no_filters_is_empty():
    sql, params = build_where_clause([])
    assert sql == ""
    assert params == []


def test_scatter_uses_a_log_scale_and_says_what_it_could_not_plot():
    """A log axis has no place for a zero. Six of 118 projects have no
    baseline cost recorded, and showing 112 points without a word would be the
    quiet kind of wrong this dashboard exists to avoid."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (baseline DOUBLE, forecast DOUBLE)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?)",
        [(float(v), float(v) * 1.05) for v in range(1, 60)] + [(3000.0, 3150.0), (0.0, 0.0)],
    )
    chart = {
        "type": "scatter",
        "echarts_option": {
            "xAxis": {"type": "value"},
            "yAxis": {"type": "value"},
            "series": [{"type": "scatter", "data": []}],
            "_columns": {"x": "baseline", "y": "forecast"},
        },
    }

    assert populate_chart_option(conn, chart) is True

    opt = chart["echarts_option"]
    assert opt["_scale"]["x"] is True
    assert opt["_excluded_points"] == 1
    assert all(point[0] > 0 and point[1] > 0 for point in opt["series"][0]["data"])


def test_scatter_keeps_every_point_when_the_scale_stays_linear():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (baseline DOUBLE, forecast DOUBLE)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?)",
        [(float(v), float(v) + 1) for v in range(0, 40)],
    )
    chart = {
        "type": "scatter",
        "echarts_option": {
            "xAxis": {"type": "value"},
            "yAxis": {"type": "value"},
            "series": [{"type": "scatter", "data": []}],
            "_columns": {"x": "baseline", "y": "forecast"},
        },
    }

    assert populate_chart_option(conn, chart) is True

    opt = chart["echarts_option"]
    assert opt["_scale"] == {"x": False, "y": False}
    assert "_excluded_points" not in opt
    assert len(opt["series"][0]["data"]) == 40


def test_histogram_bands_widen_for_a_skewed_distribution():
    """Regression: 84 of 118 government projects landed in a single bar,
    because a handful run to thousands of millions while most are under 400."""
    values = [50.0] * 80 + [300.0] * 20 + [1200.0, 2600.0, 5118.0]

    edges = _histogram_edges(values, min(values), max(values))

    assert edges[0] == 0.0
    # Bands step 1-2-5, so the bulk of the records are separated rather than
    # pooled into the first bar with everything else.
    assert 100.0 in edges
    assert 1000.0 in edges
    assert len(edges) > 4


def test_histogram_bands_stay_even_when_the_data_is_not_skewed():
    values = [float(value) for value in range(120)]

    edges = _histogram_edges(values, 0.0, 119.0)
    widths = {round(edges[i + 1] - edges[i], 6) for i in range(len(edges) - 1)}

    assert len(widths) == 1


def test_log_scale_only_for_positive_data_spanning_orders_of_magnitude():
    assert _is_log_worthy([1.0] * 10 + [5000.0])
    # A log axis cannot place a zero. A few such records are allowed, because
    # the populator leaves them out and the chart says how many; a large share
    # is not, since the reader would be shown a chart missing much of the data.
    assert _is_log_worthy([0.0] + [1.0] * 10 + [5000.0])
    assert not _is_log_worthy([0.0] * 3 + [1.0] * 10 + [5000.0])
    # A narrow spread reads fine on a linear axis.
    assert not _is_log_worthy([float(value) for value in range(1, 30)])
    # Too few points to be worth the reader's effort.
    assert not _is_log_worthy([1.0, 5000.0])


def _connect_with_portfolio_table() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (department VARCHAR, rag VARCHAR, cost DOUBLE)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?, ?)",
        [
            ("MOD", "Amber", 60.0),
            ("MOD", "Amber", 40.0),
            ("MOD", "Red", 17.0),
            ("DFT", "Amber", 60.0),
            ("DFT", "Green", 7.0),
        ],
    )
    return conn


def _stacked_chart() -> dict:
    return {
        "type": "bar",
        "echarts_option": {
            "xAxis": {"type": "category", "data": []},
            "yAxis": {"type": "value"},
            "series": [],
            "_columns": {"x": "department", "y": "cost", "series_by": "rag", "aggregation": "sum"},
        },
    }


def test_populate_stacked_bar_builds_one_series_per_status():
    conn = _connect_with_portfolio_table()
    chart = _stacked_chart()

    assert populate_chart_option(conn, chart) is True

    opt = chart["echarts_option"]
    assert opt["xAxis"]["data"] == ["MOD", "DFT"]  # ordered by total cost
    assert [s["name"] for s in opt["series"]] == ["Amber", "Green", "Red"]
    assert all(s["stack"] == "total" for s in opt["series"])
    by_name = {s["name"]: s["data"] for s in opt["series"]}
    assert by_name["Amber"] == [100.0, 60.0]
    assert by_name["Green"] == [0.0, 7.0]  # absent combinations are zero, not missing
    assert by_name["Red"] == [17.0, 0.0]


def test_stacked_bar_re_aggregates_under_a_filter():
    """The point of retaining `_columns`: a slicer must re-query, not re-scale
    a cached total."""
    conn = _connect_with_portfolio_table()
    chart = _stacked_chart()
    filter_sql, filter_params = build_where_clause(
        [{"column": "rag", "op": "in", "values": ["Amber"]}]
    )

    assert populate_chart_option(conn, chart, filter_sql, filter_params) is True

    opt = chart["echarts_option"]
    assert [s["name"] for s in opt["series"]] == ["Amber"]
    assert opt["series"][0]["data"] == [100.0, 60.0]


def test_stacked_bar_folds_values_that_say_nothing_into_one_series():
    """Regression: the GMPP delivery-confidence column carries six different
    "Exempt under Section N of the Freedom of Information Act 2000" sentences
    plus "Unknown", which stacked six invisible segments with paragraph-long
    legend entries."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (department VARCHAR, rag VARCHAR, cost DOUBLE)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?, ?)",
        [
            ("MOD", "Amber", 100.0),
            ("MOD", "Red", 20.0),
            ("MOD", "Exempt under Section 43 of the Freedom of Information Act 2000", 5.0),
            ("MOD", "Exempt under Section 24 of the Freedom of Information Act 2000", 3.0),
            ("MOD", "Unknown", 2.0),
            ("MOD", "Not Applicable", 1.0),
        ],
    )
    chart = _stacked_chart()

    assert populate_chart_option(conn, chart) is True

    series = chart["echarts_option"]["series"]
    assert [s["name"] for s in series] == ["Amber", "Red", "Not reported"]
    by_name = {s["name"]: s["data"] for s in series}
    assert by_name["Not reported"] == [11.0]  # 5 + 3 + 2 + 1, one segment


def test_stacked_bar_averages_over_the_folded_group_not_over_averages():
    """Folding after an AVG would average four averages; the mean has to be
    re-derived across the whole folded group."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (department VARCHAR, rag VARCHAR, cost DOUBLE)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?, ?)",
        [
            ("MOD", "Unknown", 10.0),
            ("MOD", "Unknown", 20.0),
            ("MOD", "Exempt under Section 43 of the Freedom of Information Act 2000", 60.0),
        ],
    )
    chart = _stacked_chart()
    chart["echarts_option"]["_columns"]["aggregation"] = "average"

    assert populate_chart_option(conn, chart) is True

    series = chart["echarts_option"]["series"]
    assert [s["name"] for s in series] == ["Not reported"]
    assert series[0]["data"] == [30.0]  # (10 + 20 + 60) / 3, not (15 + 60) / 2


def test_stacked_bar_reports_no_match_on_an_empty_filter_result():
    conn = _connect_with_portfolio_table()
    chart = _stacked_chart()
    filter_sql, filter_params = build_where_clause(
        [{"column": "rag", "op": "in", "values": ["Nonexistent"]}]
    )

    assert populate_chart_option(conn, chart, filter_sql, filter_params) is False


def _connect_with_heart_like_table() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE data (cp INTEGER, chol DOUBLE, target INTEGER)")
    conn.executemany(
        "INSERT INTO data VALUES (?, ?, ?)",
        [
            (0, 200.0, 0),
            (0, 220.0, 0),
            (2, 240.0, 1),
            (2, 260.0, 1),
            (2, 280.0, 1),
        ],
    )
    return conn


def _bar_chart(orientation: str = "horizontal", aggregation: str = "average") -> dict:
    return {
        "id": "abc123",
        "type": "bar",
        "title": "Avg Chol by Cp",
        "xAxis": "chol",
        "yAxis": "cp",
        "series": ["chol"],
        "echarts_option": {
            "yAxis": {"type": "category", "data": []},
            "series": [{"type": "bar", "data": []}],
            "_columns": {"x": "cp", "y": "chol", "orientation": orientation, "aggregation": aggregation},
        },
    }


def test_requery_bar_chart_matches_manual_duckdb_query():
    conn = _connect_with_heart_like_table()
    chart = _bar_chart()

    patched = requery_chart(conn, chart, "CAST(\"cp\" AS VARCHAR) IN (?)", ["2"])

    assert patched is not None
    expected = conn.execute(
        "SELECT CAST(cp AS VARCHAR), AVG(chol) FROM data WHERE cp IS NOT NULL AND chol IS NOT NULL "
        "AND CAST(cp AS VARCHAR) IN ('2') GROUP BY cp ORDER BY AVG(chol) DESC"
    ).fetchall()
    expected_values = [round(float(r[1]), 2) for r in expected][::-1]
    assert patched["echarts_option"]["series"][0]["data"] == expected_values
    assert patched["visual_spec"] is not None


def test_requery_chart_returns_none_when_columns_missing():
    conn = _connect_with_heart_like_table()
    chart = {
        "id": "no-spec",
        "type": "bar",
        "xAxis": "chol",
        "yAxis": "cp",
        "series": ["chol"],
        "echarts_option": {"series": [{"type": "bar", "data": [1, 2, 3]}]},
    }
    assert requery_chart(conn, chart, "", []) is None


def test_requery_chart_does_not_mutate_stored_chart():
    conn = _connect_with_heart_like_table()
    chart = _bar_chart()
    original_data = list(chart["echarts_option"]["series"][0]["data"])

    requery_chart(conn, chart, "CAST(\"cp\" AS VARCHAR) IN (?)", ["2"])

    assert chart["echarts_option"]["series"][0]["data"] == original_data


def test_populate_chart_option_unfiltered_matches_original_pipeline_shape():
    conn = _connect_with_heart_like_table()
    chart = _bar_chart()
    assert populate_chart_option(conn, chart, "", []) is True
    assert chart["echarts_option"]["series"][0]["data"] != []


def test_recompute_kpi_sum():
    conn = _connect_with_heart_like_table()
    value = recompute_kpi(conn, "chol", is_total=True, is_percent=False, filter_sql="", filter_params=[])
    assert value == 1200.0


def test_recompute_kpi_average():
    conn = _connect_with_heart_like_table()
    value = recompute_kpi(conn, "chol", is_total=False, is_percent=False, filter_sql="", filter_params=[])
    assert value == 240.0


def test_recompute_kpi_percent_rate():
    conn = _connect_with_heart_like_table()
    value = recompute_kpi(conn, "target", is_total=False, is_percent=True, filter_sql="", filter_params=[])
    assert value == 60.0


def test_recompute_kpi_with_filter():
    conn = _connect_with_heart_like_table()
    sql, params = build_where_clause([{"column": "cp", "op": "in", "values": [2]}])
    value = recompute_kpi(conn, "target", is_total=False, is_percent=True, filter_sql=sql, filter_params=params)
    assert value == 100.0


def test_derive_filterable_columns_keeps_late_columns_over_truncation():
    """Regression test: a flat slice used to drop whichever categorical
    dimensions came late in the file's column order — on a 14-column heart
    dataset this silently dropped 'target', the outcome column, since it's
    the last column and a naive [:12] cut it off."""
    columns = [
        {"name": f"dim_{i}", "analysis_role": "dimension",
         "categorical_summary": {"unique_count": 3, "top_values": [{"value": "a", "count": 1}]}}
        for i in range(12)
    ] + [
        {"name": "target", "analysis_role": "flag",
         "categorical_summary": {"unique_count": 2, "top_values": [{"value": "1", "count": 5}]}},
        {"name": "thal", "analysis_role": "dimension",
         "categorical_summary": {"unique_count": 4, "top_values": [{"value": "2", "count": 5}]}},
    ]
    metadata = {"data_profile": {"columns": columns}}

    result = _derive_filterable_columns(metadata)

    names = {c.column for c in result}
    assert "target" in names
    assert "thal" in names


@pytest.mark.asyncio
async def test_analysis_engine_populate_chart_data_retains_columns_spec():
    """Regression test for the refactor that extracted _populate_chart_data's
    inline SQL into shared, filter-aware helpers: the pipeline's own
    population method must still populate a chart's data AND must no longer
    strip `_columns` (the live-filter endpoint depends on it surviving)."""
    from app.services.analysis_engine import AnalysisEngine

    conn = _connect_with_heart_like_table()
    chart = _bar_chart()

    populated = await AnalysisEngine()._populate_chart_data(conn, [chart])

    assert len(populated) == 1
    assert populated[0]["echarts_option"]["series"][0]["data"] != []
    assert "_columns" in populated[0]["echarts_option"]
