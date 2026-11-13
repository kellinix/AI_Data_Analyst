from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.analytics.semantic_detector import enrich_schema_with_semantics
from app.services.investigation import ComparisonPlan, compare


@pytest.mark.parametrize('name', ['line_item_value', 'product_value', 'category_value', 'country_value'])
def test_numeric_values_are_not_labels_because_of_their_subject(name):
    field = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': True, 'dtype': 'DOUBLE'}],
        {name: {'count': 100, 'unique_count': 90, 'min': 1.25, 'max': 10000.75}}, {})[0]
    assert field['analysis_role'] == 'metric'
    assert field['semantic_type'] == 'numeric_metric'
    assert not field.get('unit')  # Value alone does not establish a currency.


@pytest.mark.parametrize('name', ['product_code_value', 'category_value', 'product_id'])
def test_bounded_codes_and_identifiers_still_are_not_measures(name):
    field = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': True, 'dtype': 'BIGINT'}],
        {name: {'count': 100, 'unique_count': 3, 'min': 0, 'max': 2}}, {})[0]
    assert field['analysis_role'] != 'metric'


@pytest.mark.parametrize('name,meaning', [('sales_value', 'currency'), ('rate_value', 'percentage')])
def test_value_suffix_keeps_explicit_money_and_rate_meanings(name, meaning):
    field = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': True, 'dtype': 'DOUBLE'}],
        {name: {'count': 100, 'unique_count': 90, 'min': 1.25, 'max': 10000.75}}, {})[0]
    assert field['semantic_type'] == meaning


@pytest.mark.parametrize('name', ['title', 'film_title', 'course_title'])
def test_short_titles_can_group_business_results(name):
    field = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': False, 'dtype': 'VARCHAR'}], {},
        {name: {'top_values': [{'value': 'A Film', 'count': 3}, {'value': 'Another Film', 'count': 2}]}})[0]
    assert field['analysis_role'] == 'dimension'


@pytest.mark.parametrize('value', ['Long description ' * 30, 'First line\nSecond line'])
def test_narrative_title_stays_text(value):
    field = enrich_schema_with_semantics(
        [{'name': 'title', 'is_numeric': False, 'dtype': 'VARCHAR'}], {},
        {'title': {'top_values': [{'value': value, 'count': 1}]}})[0]
    assert field['analysis_role'] == 'text'


@pytest.mark.parametrize('long_tail', [False, True])
def test_large_title_catalogue_uses_all_values_not_only_top_categories(long_tail):
    import duckdb

    from app.analytics.statistics import StatisticsEngine
    titles = [f'Film {index}' for index in range(1000)]
    if long_tail:
        titles[-1] = 'Long narrative ' * 40
    with duckdb.connect(':memory:') as connection:
        connection.register('data', pl.DataFrame({'title': titles, 'amount': [1.5] * len(titles)}))
        result = StatisticsEngine(connection).describe_all()
    assert result['categorical_stats']['title']['top_values'] == []
    field = next(field for field in result['schema'] if field['name'] == 'title')
    assert field['analysis_role'] == ('text' if long_tail else 'dimension')


async def test_value_and_title_work_together_in_calculated_answers(tmp_path):
    path = tmp_path/'records.parquet'
    pl.DataFrame({'title': ['A', 'B', 'A'], 'line_item_value': [12.25, 14.5, 8.75]}).write_parquet(path)
    schema = enrich_schema_with_semantics(
        [{'name': 'title', 'is_numeric': False, 'dtype': 'VARCHAR'},
         {'name': 'line_item_value', 'is_numeric': True, 'dtype': 'DOUBLE'}],
        {'line_item_value': {'count': 3, 'unique_count': 3, 'min': 8.75, 'max': 14.5}},
        {'title': {'top_values': [{'value': 'A', 'count': 2}, {'value': 'B', 'count': 1}]}})
    analysis = SimpleNamespace(id=uuid4(), row_count=3, file=SimpleNamespace(storage_path=str(path)),
                               metadata_={'schema': schema})
    answer = await compare(analysis, ComparisonPlan(aggregation='sum', column='line_item_value', group_by='title'))
    assert answer['groups'][0]['value'] == 21.0


def test_chart_caption_does_not_duplicate_group_word():
    from app.services.report_language import present_chart
    chart = {'type': 'bar', 'xAxis': 'quantity', 'yAxis': 'product_group', 'aggregation': 'sum',
             'echarts_option': {'xAxis': {'type': 'value'}, 'yAxis': {'type': 'category', 'data': ['A']},
                               'series': [{'type': 'bar', 'data': [10]}],
                               '_columns': {'x': 'product_group', 'y': 'quantity', 'aggregation': 'sum'}}}
    result = present_chart(chart)
    assert 'group group' not in result['description']
    assert 'same product group' in result['description']
