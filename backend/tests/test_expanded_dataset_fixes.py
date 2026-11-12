from types import SimpleNamespace
from uuid import uuid4

import polars as pl
import pytest

from app.analytics.labels import source_column_label
from app.analytics.semantic_detector import enrich_schema_with_semantics
from app.services.file_processor import FileProcessor
from app.services.investigation import ComparisonPlan, ComparisonUnavailable, compare
from app.services.relational_files import enrich_related_files


@pytest.mark.parametrize('name', ['total_runs', 'batsman_runs', 'extra_runs', 'wickets',
                                 'defects', 'incidents', 'admissions', 'discharges'])
def test_small_repeated_counts_are_measures(name):
    result = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': True, 'dtype': 'Int64'}],
        {name: {'min': 0, 'max': 4, 'unique_count': 5, 'count': 100}}, {})
    assert result[0]['analysis_role'] == 'metric'
    assert result[0]['semantic_type'] == 'count'


@pytest.mark.parametrize('name', ['run_id', 'defect_code', 'incident_level', 'dept', 'number'])
def test_identifiers_codes_and_undefined_numbers_do_not_become_counts(name):
    result = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': True, 'dtype': 'Int64'}],
        {name: {'min': 0, 'max': 4, 'unique_count': 5, 'count': 100}}, {})
    assert result[0]['analysis_role'] != 'metric'


@pytest.mark.parametrize('name', ['standard_error', 'standard_deviation', 'error_rate', 'variance', 'uncertainty'])
def test_statistical_errors_and_rates_are_not_event_counts(name):
    from app.analytics.measure_semantics import is_additive_flow
    result = enrich_schema_with_semantics(
        [{'name': name, 'is_numeric': True, 'dtype': 'Float64'}],
        {name: {'min': .1, 'max': .4, 'unique_count': 4, 'count': 100}}, {})
    assert result[0]['semantic_type'] != 'count'
    assert not is_additive_flow(name)


async def test_each_group_question_overrides_planner_default_page(tmp_path, monkeypatch):
    import json

    from app.services import ai_service
    path = tmp_path/'data.parquet'
    pl.DataFrame({'dept': list(range(81)), 'sales': list(range(81))}).write_parquet(path)
    analysis = SimpleNamespace(id=uuid4(), name='Sales', column_count=2, row_count=81,
        file=SimpleNamespace(storage_path=str(path)), insights=[],
        metadata_={'schema': [{'name': 'dept', 'is_numeric': True, 'analysis_role': 'dimension'},
                              {'name': 'sales', 'is_numeric': True, 'analysis_role': 'metric'}]})
    async def create(**kwargs):
        payload = {'answer_kind': 'calculated', 'plan': {'aggregation':'average', 'column':'sales',
                   'group_by':'dept', 'limit':10, 'all_groups':None}}
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    monkeypatch.setattr(ai_service, 'client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    answer = await ai_service.AIService().chat(analysis, [], 'What is the average sales for each department?')
    assert answer['metadata']['status'] == 'succeeded'
    assert len(answer['metadata']['comparison']['groups']) == 81


@pytest.mark.parametrize('entity', ['patient', 'payer', 'supplier', 'customer'])
def test_bare_entity_reference_requires_named_unique_parent(entity):
    fact = pl.DataFrame({entity.upper(): ['A', 'A', 'B'], 'amount': [5, 10, 20]})
    parent = pl.DataFrame({'Id': ['A', 'B'], 'name': ['One', 'Two']})
    combined, resolution = enrich_related_files([fact, parent], table_names=['events.csv', entity+'s.csv'])
    assert resolution['status'] == 'enriched'
    assert combined['amount'].sum() == 35
    assert combined['name'].to_list() == ['One', 'One', 'Two']
    refused, _ = enrich_related_files([fact, parent], table_names=['events.csv', 'unrelated.csv'])
    assert refused is None
    duplicate = pl.concat([parent, parent.head(1)])
    refused, _ = enrich_related_files([fact, duplicate], table_names=['events.csv', entity+'s.csv'])
    assert refused is None


def test_entity_date_composite_links_without_multiplying_sales():
    sales = pl.DataFrame({'Store': [1, 1, 1, 2], 'Date': ['2020-01-01']*2+['2020-01-08', '2020-01-01'], 'sales': [1, 2, 3, 4]})
    weeks = pl.DataFrame({'Store': [1, 1, 2], 'Date': ['2020-01-01', '2020-01-08', '2020-01-01'], 'temperature': [3, 6, 9]})
    combined, resolution = enrich_related_files([sales, weeks], table_names=['sales.csv', 'features.csv'])
    assert resolution['status'] == 'enriched'
    assert combined['sales'].sum() == 10 and combined.height == 4
    assert combined['temperature'].to_list() == [3, 3, 6, 9]
    # Date overlap without a named entity key does not imply a relationship.
    refused, _ = enrich_related_files([sales.drop('Store'), weeks.drop('Store')], table_names=['sales.csv', 'features.csv'])
    assert refused is None


@pytest.mark.parametrize('groups', [81, 1001])
async def test_complete_breakdown_never_silently_truncates(tmp_path, groups):
    path = tmp_path/'data.parquet'
    pl.DataFrame({'dept': list(range(groups)), 'sales': list(range(groups))}).write_parquet(path)
    analysis = SimpleNamespace(id=uuid4(), row_count=groups, file=SimpleNamespace(storage_path=str(path)),
        metadata_={'schema': [{'name': 'dept', 'is_numeric': True, 'analysis_role': 'dimension'},
                              {'name': 'sales', 'is_numeric': True, 'analysis_role': 'metric'}]}, insights=[])
    plan = ComparisonPlan(aggregation='average', column='sales', group_by='dept', all_groups=True)
    if groups > 1000:
        with pytest.raises(ComparisonUnavailable, match='1,000'):
            await compare(analysis, plan)
    else:
        result = await compare(analysis, plan)
        assert len(result['groups']) == result['group_count'] == groups
        assert {r['group_value']: r['value'] for r in result['groups']} == {str(i): i for i in range(groups)}
        assert 'Showing 50' not in result['scope']


def test_same_header_in_annual_sources_keeps_year():
    for year in (2015, 2016):
        field = {'name': 'region', 'measure_grain': {'source_table': f'{year}.csv', 'source_column': 'Region'}}
        assert str(year) in source_column_label(field)


def test_two_dates_cannot_replace_an_unmatched_entity_key():
    from app.services.relational_files import _candidate_relationships
    fact = pl.DataFrame({'Store': [1, 1], 'Date': ['2020-01-01']*2, 'Period': ['2020-02-01']*2})
    parent = pl.DataFrame({'Store': [2, 2], 'Date': ['2020-01-01', '2020-01-08'],
                          'Period': ['2020-02-01', '2020-02-08']})
    assert _candidate_relationships(fact, parent, lookup_name='stores.csv') == []


def test_titles_keep_the_measure_denominator():
    from app.analytics.labels import derive_label
    assert derive_label('revenue_per_employee') == 'Revenue Per Employee'
    assert 'Per Capita' in derive_label('Economy (GDP per Capita)')


def test_binary_flag_total_uses_count_language_only_when_verified():
    from app.services.chat_evidence import _friendly_fact
    fact = {'id': 'saved_1', 'values': {'column': 'is_canceled', 'operation': 'total',
                                     'value': 12, 'verified_binary_count': True}}
    assert _friendly_fact(fact) == '12 entries have is canceled set to 1.'
    fact['values'].pop('verified_binary_count')
    assert 'set to 1' not in _friendly_fact(fact)


@pytest.mark.parametrize('low,high,distinct,verified', [(0, 1, 2, True), (1, 1, 1, True),
    (0, 1, 3, False), (0, 2, 2, False), (0, 1, None, False)])
def test_binary_count_wording_requires_measured_codes(low, high, distinct, verified):
    from app.services.chat_evidence import build_chat_facts
    stats = {'count': 3, 'total': 2, 'mean': 2/3, 'min': low, 'max': high, 'unique_count': distinct}
    item = SimpleNamespace(row_count=3, column_count=1, insights=[], metadata_={
        'schema': [{'name': 'is_canceled', 'analysis_role': 'flag'}],
        'data_profile': {'dataset': {}, 'columns': [{'name': 'is_canceled', 'numeric_summary': stats}]}})
    total = next(f for f in build_chat_facts(item) if f['values'].get('operation') == 'total')
    assert bool(total['values'].get('verified_binary_count')) is verified


def test_large_combination_budget_refuses_before_joining():
    processor = FileProcessor()
    processor.MAX_COMBINED_CELLS = 3
    context = {}
    result = processor._combine_frames([pl.DataFrame({'id': [1, 2], 'amount': [3, 4]})], context)
    assert result.is_empty()
    assert context['relationship_resolution']['reason_code'] == 'analysis_size_limit'


def test_unrelated_definition_cannot_hide_an_unknown_chart_code():
    from app.services.report_language import present_chart
    chart = {'type': 'bar', 'xAxis': 'segment', 'yAxis': 'sales', 'aggregation': 'sum',
        'echarts_option': {'xAxis': {'type': 'category', 'data': ['TA', 'TO']},
                          'yAxis': {'type': 'value'}, 'series': [{'type': 'bar', 'data': [1, 2]}],
                          '_columns': {'x': 'segment', 'y': 'sales', 'aggregation': 'sum'}}}
    meta = {'schema': [{'name': 'segment', 'analysis_role': 'dimension',
                        'data_definition': {'value_labels': [{'value': 'TA', 'label': 'Supplied meaning'}]}},
                       {'name': 'sales', 'is_numeric': True, 'analysis_role': 'metric',
                        'data_definition': {'label': 'Sales'}}]}
    result = present_chart(chart, meta)
    assert 'Source codes TO have no supplied definitions' in result['description']
    assert 'Source codes TA' not in result['description']
