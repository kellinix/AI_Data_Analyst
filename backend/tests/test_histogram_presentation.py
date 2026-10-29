from copy import deepcopy

import duckdb

from app.analytics.chart_selector import _histogram_chart
from app.analytics.histogram_presentation import present_histogram
from app.analytics.live_filter import populate_chart_option, requery_chart
from app.schemas.analysis import ChartConfig
from app.services.export_charts import normalise_charts


def test_saved_range_counts_remain_identical_across_ui_spec_and_export():
    raw = {'id': 'revenue', 'type': 'histogram', 'title': 'How Revenue is spread', 'currency': 'GBP',
           'xAxis': 'revenue', 'echarts_option': {'xAxis': {'name': 'Revenue', 'type': 'category', 'data': ['0-2K', '2K-4K', '4K-6K']},
           'yAxis': {'type': 'value', 'name': 'count'}, 'series': [{'name': 'revenue', 'type': 'bar', 'data': [2, 8, 1]}]}}
    original = deepcopy(raw)
    shown = ChartConfig(**raw)
    assert shown.echarts_option['yAxis']['data'] == ['0 to 2,000', '2,000 to 4,000', '4,000 to 6,000']
    assert shown.echarts_option['series'][0]['data'] == [2, 8, 1]
    assert shown.echarts_option['series'][0]['label']['position'] == 'right'
    assert shown.currency is None and shown.echarts_option['xAxis']['name'] == 'Entries'
    assert shown.yAxis == 'Revenue (GBP)' and '8 of the 11 entries shown' in shown.description
    assert [row['count'] for row in shown.visual_spec['data']['values']] == [2, 8, 1]
    assert shown.visual_spec['encoding']['x']['field'] == 'count'
    exported = normalise_charts([raw])[0]
    assert exported.horizontal and exported.series == [('Entries', [2., 8., 1.])]
    assert raw == original and ChartConfig(**shown.model_dump()) == shown


def test_filtered_range_counts_and_explanation_use_only_matching_entries():
    with duckdb.connect() as conn:
        conn.execute("CREATE TABLE data AS SELECT i AS revenue FROM range(100) t(i)")
        chart = _histogram_chart('revenue', {'min': 0, 'max': 99})
        assert populate_chart_option(conn, chart)
        filtered = requery_chart(conn, chart, 'revenue < ?', [10])
        empty = requery_chart(conn, chart, 'revenue < ?', [-1])
    shown = present_histogram(filtered)
    assert sum(shown['echarts_option']['series'][0]['data']) == 10
    assert '11 entries shown' not in shown['description']
    assert shown['visual_spec']['description'] == shown['description']
    assert all('K' not in value for value in shown['echarts_option']['yAxis']['data'])
    assert empty['echarts_option']['series'][0]['data'] == []


def test_tied_and_capped_saved_ranges_do_not_invent_a_unique_leader_or_full_scope():
    raw = {'type': 'histogram', 'xAxis': 'value', 'echarts_option': {'xAxis': {'data': ['5K+', '10K+']},
           'series': [{'data': [5000, 5000]}]}}
    shown = present_histogram(raw)
    assert '2 ranges share the highest count' in shown['description']
    assert 'first 10,000 entries' in shown['description']
    assert 'Most common range' not in shown['description']


def test_sales_donut_names_the_record_and_payment_method_without_changing_counts():
    chart = {"type": "donut", "title": "Cash Type breakdown", "series": ["cash_type"],
             "echarts_option": {"series": [{"data": [{"name": "card", "value": 9},
                                                     {"name": "cash", "value": 1}]}]}}
    shown = present_histogram(chart, {"kind": "sales_transaction"})
    assert shown["title"] == "Sales records by payment method"
    assert shown["description"] == "Number of sales records for each payment method."
    assert shown["echarts_option"] == chart["echarts_option"]
