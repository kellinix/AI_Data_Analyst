"""The same readable chart wording reaches saved reports and exports."""
from copy import deepcopy

import duckdb
import pytest

from app.analytics.chart_selector import (
    _donut_chart,
    _histogram_chart,
    _horizontal_bar_chart,
    _multi_line_chart,
    _record_count_chart,
    _scatter_chart,
    _stacked_bar_chart,
    _time_series_chart,
)
from app.analytics.forecasting import generate_forecasts
from app.analytics.labels import derive_label, reader_label, source_column_label
from app.analytics.live_filter import populate_chart_option
from app.analytics.measure_semantics import is_observation_date
from app.schemas.analysis import ChartConfig
from app.services.export_charts import normalise_charts
from app.services.report_language import (
    forecast_wording,
    present_chart,
    present_insight,
    present_metadata,
)
from app.services.semantic_wrangler import (
    _fallback_display_metadata,
    apply_display_metadata_to_charts,
    apply_display_metadata_to_statistics,
)


def field(name, original, table="items.csv", **extra):
    return {"name": name, "measure_grain": {"source_column": original, "source_table": table}, **extra}


@pytest.mark.parametrize(("original", "expected"), [
    ("OrderQuantity", "Order Quantity"), ("InvoiceLineId", "Invoice Line ID"),
    ("BillingCountry", "Billing Country"), ("unitPriceUSD", "Unit Price USD"),
])
def test_original_camel_case_headers_recover_word_boundaries(original, expected):
    assert derive_label(original) == expected


def test_source_roles_and_existing_decoded_names_are_retained():
    assert source_column_label(field("name", "name", "themes.csv")) == "Theme name"
    assert source_column_label(field("country", "Country", "Customer.csv")) == "Customer country"
    assert source_column_label(field("dob", "dob", display_label="Date of birth")) == "Date of birth"
    assert source_column_label(field("g", "G")) == "G"


@pytest.mark.parametrize("saved", [None, "Country", "Country country", "Country country country"])
def test_countries_country_label_is_stable_across_generation_and_repeated_reads(saved):
    statistics = {"schema": [field("country", "Country", "countries.csv", display_label=saved),
                              field("weight", "weight", "athletes.csv")]}
    chart = _horizontal_bar_chart("country", "weight", aggregation="average")
    for _ in range(3):
        display = _fallback_display_metadata(statistics, [chart])
        statistics = apply_display_metadata_to_statistics(statistics, display)
        chart = apply_display_metadata_to_charts([chart], display)[0]
        shown = present_chart(chart, statistics)
        response = ChartConfig(**shown)
        assert response.title == "Average weight by country"
        assert response.echarts_option["yAxis"]["name"] == "Country"
        assert statistics["schema"][0]["display_label"] == "Country"
        chart = response.model_dump()


def test_source_qualification_preserves_meaningful_labels_and_singular_status():
    assert source_column_label(field("country", "Country", "countries.csv", display_label="Country of residence")) == "Country of residence"
    assert source_column_label(field("type", "Type", "Status.csv")) == "Status type"


def test_num_expands_for_numeric_measures_while_identifier_labels_stay_precise():
    measure = field("num_parts", "num_parts", "sets.csv", is_numeric=True, analysis_role="metric")
    assert reader_label("num_parts", measure) == "number of parts"
    assert source_column_label(measure) == "Number of parts"
    identifier = field("num_account", "num_account", "accounts.csv", is_numeric=True, analysis_role="identifier")
    assert reader_label("num_account", identifier) == "num account"
    assert source_column_label(identifier) == "Num Account"
    assert reader_label("num_parts") == "num parts"


def test_average_line_explains_the_same_calculation_as_a_bar():
    chart = _time_series_chart("year", "num_parts", "average")
    schema = [field("num_parts", "num_parts", "sets.csv", is_numeric=True, analysis_role="metric")]
    shown = present_chart(chart, {"schema": schema})
    assert shown["title"] == "Average number of parts by year"
    assert "To find an average, we add the supplied numbers and divide by how many there are." in shown["description"]


def test_total_bars_name_the_calculation_and_keep_exact_data():
    chart = _horizontal_bar_chart("billingcountry", "quantity", aggregation="sum")
    chart["echarts_option"]["yAxis"]["data"] = ["USA", "UK"]
    chart["echarts_option"]["series"][0]["data"] = [2**53 + 1, 7]
    metadata = {"schema": [field("billingcountry", "BillingCountry"), field("quantity", "Quantity")]}
    before = deepcopy(chart)
    shown = present_chart(chart, metadata)
    assert shown["title"] == "Total quantity by billing country"
    assert "Each bar shows total quantity" in shown["description"]
    assert shown["echarts_option"]["xAxis"]["name"] == "Total quantity"
    assert shown["echarts_option"]["series"][0]["data"] == [2**53 + 1, 7]
    assert chart == before
    assert present_chart(shown, metadata) == shown
    response = ChartConfig(**shown)
    assert response.title == shown["title"]
    assert response.echarts_option["series"][0]["data"] == [2**53 + 1, 7]


def test_average_and_split_bars_explain_their_groups():
    chart = _stacked_bar_chart("country", "rating", "status", aggregation="average")
    shown = present_chart(chart)
    assert shown["title"] == "Average rating by country and status"
    assert "divide by how many" in shown["description"]
    assert "Colours show status groups side by side" in shown["description"]


def test_count_and_pie_titles_describe_entries_instead_of_people():
    for chart in [_record_count_chart("country"), _donut_chart("country", [{"value": "UK", "count": 3}])]:
        shown = present_chart(chart)
        assert shown["title"] == "Number of entries by country"
        assert "people" not in shown["description"]
    assert "same name or ID" in present_chart(_record_count_chart("country"))["description"]


def test_line_title_and_legend_name_every_measure_and_operation():
    chart = _multi_line_chart("date", ["quantity", "returns"], ["sum", "sum"])
    chart["echarts_option"]["_columns"]["time_grain"] = "month"
    shown = present_chart(chart)
    assert shown["title"] == "Total quantity and total returns by month"
    assert [item["name"] for item in shown["echarts_option"]["series"]] == ["Total quantity", "Total returns"]
    assert "one month" in shown["description"]


def test_store_opening_dates_describe_groups_and_do_not_become_activity_history():
    chart = _time_series_chart("store_open_date", "stock_on_hand", "sum")
    chart["echarts_option"]["_columns"]["time_grain"] = "year"
    shown = present_chart(chart)
    assert shown["title"] == "Total stock on hand by store open date"
    assert "year of their store open date" in shown["description"]
    assert "different groups of entries" in shown["description"]
    assert "over time" not in shown["title"]


def test_saved_lifecycle_labels_keep_recovered_original_words():
    chart = _time_series_chart("storeopendate", "stock_on_hand", "sum")
    shown = present_chart(chart, labels={"storeopendate": "Store Open Date"})
    assert shown["title"] == "Total stock on hand by store open date"
    assert ChartConfig(**shown).title == shown["title"]


@pytest.mark.parametrize("name", ["store_open_date", "StoreOpenDate", "debut", "dob", "DateOfBirth"])
def test_lifecycle_dates_cannot_drive_an_activity_forecast(name):
    assert is_observation_date(name) is False
    with duckdb.connect() as conn:
        assert generate_forecasts(conn, [{"name": name, "is_date": True}], []) == []


def test_daily_date_labels_keep_the_day_while_monthly_labels_say_month():
    chart = _time_series_chart("date", "quantity", "sum")
    chart["echarts_option"]["xAxis"]["data"] = ["2025-02-01", "2025-02-02"]
    chart["echarts_option"]["series"][0]["data"] = [1, 2]
    shown = present_chart(chart)
    assert shown["echarts_option"]["xAxis"]["_monthYearLabels"] == {}
    assert shown["echarts_option"]["xAxis"]["name"] == "Date"


def test_scatter_explains_a_dot_and_preserves_sample_and_missing_value_limits():
    chart = _scatter_chart("quantity", "unit_price", .8)
    chart["echarts_option"]["series"][0]["data"] = [[2, 3.5], [4, 7]]
    chart["echarts_option"]["_scatter_coverage"] = {"missing": 5, "eligible": 1000, "sampled": 500}
    shown = present_chart(chart)
    assert shown["title"] == "How quantity and unit price compare"
    assert "Each dot is one entry" in shown["description"]
    assert "5 entries are missing one of the two figures" in shown["description"]
    assert "first 500 of 1,000 entries with both figures filled in" in shown["description"]
    assert "Other factors" in shown["description"]
    assert present_chart(shown) == shown


def test_histogram_title_counts_ranges_and_exports_keep_the_same_title():
    chart = _histogram_chart("amount_usd", {})
    chart["echarts_option"]["xAxis"]["data"] = ["0-10", "10-20"]
    chart["echarts_option"]["series"][0]["data"] = [2, 3]
    shown = present_chart(chart)
    assert shown["title"] == "Number of entries by amount (US dollars) range"
    assert shown["echarts_option"]["series"][0]["data"] == [2, 3]
    exported = normalise_charts([shown])[0]
    assert exported.title == shown["title"]
    assert exported.y_label == "Amount (US dollars)"


def test_ai_titles_cannot_replace_the_recorded_calculation_or_add_a_currency():
    chart = _horizontal_bar_chart("country", "quantity", aggregation="sum")
    statistics = {"schema": [field("quantity", "OrderQuantity"), field("country", "Country", "customers.csv")]}
    display = _fallback_display_metadata(statistics, [chart])
    display["charts"] = [{"id": chart["id"], "title": "Average profit by country", "description": "Guaranteed growth"}]
    shown = apply_display_metadata_to_charts([chart], display)[0]
    assert shown["title"] == "Total order quantity by customer country"
    assert "Guaranteed" not in shown["description"]


def test_old_forecasts_with_opening_dates_explain_the_required_date_basis():
    title, text = forecast_wording({"metric": "quantity", "date_column": "store_open_date",
                                   "predictions": {"next_month": {"value": 999}}})
    assert title == "Use activity dates before making a forecast"
    assert "when the measured activity happened" in text and "999" not in text


def test_summary_and_key_figures_recover_source_names_without_altering_values():
    metadata = {"schema": [field("orderquantity", "OrderQuantity")], "analysis_evidence": {
        "summary_checks": {"method": "measured_facts_v1", "facts": [{"id": "metric_0",
        "text": "Orderquantity sums to 3.", "values": {"column": "orderquantity", "operation": "total", "value": 3}}]}}}
    shown, text = present_metadata(metadata, "Orderquantity sums to 3.")
    assert text == "Total order quantity is 3."
    assert shown["analysis_evidence"]["summary_checks"]["facts"][0]["values"] == metadata["analysis_evidence"]["summary_checks"]["facts"][0]["values"]
    insight = present_insight({"type": "summary", "data": {"column": "orderquantity", "value": 3}}, metadata)
    assert insight["title"] == "Total order quantity" and insight["data"]["value"] == 3


def test_a_probability_average_is_never_relabelled_as_binary_successes():
    chart = _horizontal_bar_chart("research", "chance_of_admit", aggregation="percent_rate")
    shown = present_chart(chart)
    assert shown["title"] == "Average recorded admission chance (%) by research"
    assert "marked 1" not in shown["description"]
    assert "Actual admission decisions require separate records" in shown["description"]


def test_scoped_published_percentages_keep_the_question_and_supplied_calculation():
    chart = _horizontal_bar_chart("country", "percentage", aggregation="average")
    chart["echarts_option"]["_columns"]["survey_fields"] = {"country": "country", "percentage": "percentage"}
    chart["description"] = "Question is A. Answer is Yes. Survey group is Group. Supplied Average entries are excluded."
    chart["echarts_option"]["series"][0]["data"] = [12., 8.]
    shown = present_chart(chart)
    assert shown["title"] == "Published percentage (%) by country"
    assert "Question is A. Answer is Yes. Survey group is Group" in shown["description"]
    assert "divide" not in shown["description"] and "average" not in shown["title"].lower()
    assert present_chart(shown) == shown


def test_known_money_units_belong_only_to_the_money_axis():
    chart = _scatter_chart("quantity", "price", .8)
    chart["currency"] = "GBP"
    metadata = {"schema": [field("quantity", "Quantity", semantic_type="count"),
                           field("price", "Price", semantic_type="currency")]}
    shown = present_chart(chart, metadata)
    assert shown["echarts_option"]["xAxis"]["_currency"] is None
    assert shown["echarts_option"]["yAxis"]["_currency"] == "GBP"
    assert "British pounds" in shown["title"]
    assert "pounds" not in shown["echarts_option"]["xAxis"]["name"]


def test_identical_rendered_summary_aliases_show_once_without_losing_the_catalogue():
    facts = [{"id": f"identity_{index}", "text": f"Raw identity {index}",
              "calculation": f"COUNT(DISTINCT {column})", "scope": "analysed file",
              "values": {"column": column, "distinct_values": 35, "repeated_records": 10}}
             for index, column in enumerate(["product_id", "product_id_related", "store_id"])]
    metadata = {"schema": [field("product_id", "Product_ID"),
                           field("product_id_related", "Product_ID", "products.csv"),
                           field("store_id", "Store_ID")],
                "analysis_evidence": {"summary_checks": {"method": "measured_facts_v1", "facts": deepcopy(facts)},
                                      "summary_fact_catalogue": deepcopy(facts)}}
    before = deepcopy(metadata)
    shown, summary = present_metadata(metadata, "\n".join(f["text"] for f in facts))
    assert summary.count("35 different product IDs") == 1
    assert summary.count("35 different store IDs") == 1
    selected = shown["analysis_evidence"]["summary_checks"]["facts"]
    assert [fact["id"] for fact in selected] == ["identity_0", "identity_2"]
    assert selected[0]["calculation"] == "COUNT(DISTINCT product_id)"
    assert shown["analysis_evidence"]["summary_fact_catalogue"] == facts
    assert metadata == before


@pytest.mark.parametrize("aggregation", ["sum", "average"])
def test_split_charts_aggregate_all_combinations_before_selecting_groups(aggregation):
    with duckdb.connect() as conn:
        conn.execute("""CREATE TABLE data AS
            SELECT 'c' || c.i::VARCHAR AS category, 's' || s.i::VARCHAR AS status,
                   c.i + s.i + v.i AS amount
            FROM range(25) c(i), range(10) s(i), (VALUES (1), (3)) v(i)""")
        chart = _stacked_bar_chart("category", "amount", "status", aggregation)
        assert populate_chart_option(conn, chart)
    option = chart["echarts_option"]
    assert option["xAxis"]["data"] == [f"c{index}" for index in range(24, 12, -1)]
    assert len(option["series"]) == 8
    for series in option["series"]:
        status = int(series["name"][1:])
        expected = [(category + status + 2) * (2 if aggregation == "sum" else 1)
                    for category in range(24, 12, -1)]
        assert series["data"] == expected
    shown = present_chart(chart)
    assert "12 main groups" in shown["description"] and "8 named colour groups" in shown["description"]
    assert "totals across all colour groups" in shown["description"]
    assert "bars use only the displayed colour groups" in shown["description"]


def test_record_count_bound_survives_legacy_and_new_chart_presentation():
    legacy = present_chart(_record_count_chart("country"))
    assert "up to 15 largest groups" in legacy["description"]
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT (i%20)::VARCHAR AS country FROM range(100) t(i)")
        chart = _record_count_chart("country")
        populate_chart_option(conn, chart)
    shown = present_chart(chart)
    assert "up to 15 groups with the highest entry counts" in shown["description"]
    assert shown["description"].count("up to 15") == 1
    assert present_chart(shown) == shown
