from copy import deepcopy

from app.analytics.line_presentation import present_time_line
from app.schemas.analysis import ChartConfig


def line(values):
    return {'id': 'line', 'type': 'line', 'title': 'Revenue over time', 'xAxis': 'week_start_date', 'yAxis': 'revenue',
            'echarts_option': {'xAxis': {'type': 'category', 'data': ['2025-02-03', '2025-02-10', '2025-02-17']},
            'yAxis': {'type': 'value', 'name': 'Revenue'}, 'series': [{'type': 'line', 'name': 'revenue', 'smooth': True, 'data': values}],
            '_columns': {'x': 'week_start_date', 'y': 'revenue', 'aggregation': 'sum'}}}


def test_start_is_the_first_recorded_amount_not_an_invented_zero():
    original = line([144076.51, 150000., 140000.])
    before = deepcopy(original)
    shown = ChartConfig(**original)
    option = shown.echarts_option
    assert option['xAxis']['boundaryGap'] is False and option['yAxis']['scale'] is True and 'min' not in option['yAxis']
    assert option['xAxis']['_monthYearLabels']['2025-02-03'] == 'Feb 2025'
    assert option['series'][0]['data'] == original['echarts_option']['series'][0]['data']
    assert 'markPoint' not in option['series'][0]
    assert 'First recorded point' not in shown.description
    assert 'Total revenue for each week' in shown.description
    assert original == before and ChartConfig(**shown.model_dump()) == shown


def test_missing_and_negative_values_are_preserved_without_clipping_or_padding():
    original = line([None, -10., 20.])
    original['echarts_option']['yAxis']['min'] = 0
    shown = present_time_line(original)
    assert 'min' not in shown['echarts_option']['yAxis']
    assert 'markPoint' not in shown['echarts_option']['series'][0]
    assert shown['echarts_option']['series'][0]['data'] == [None, -10., 20.]


def test_disconnected_readings_are_not_presented_as_a_connected_trend():
    original = line([None, 5., None])
    original['echarts_option']['series'][0]['lineStyle'] = {'opacity': 0}
    assert present_time_line(original) == original
