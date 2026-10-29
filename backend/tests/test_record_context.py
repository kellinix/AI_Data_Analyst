from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import polars as pl

from app.analytics.histogram_presentation import present_histogram
from app.analytics.record_context import record_context, record_label
from app.services.investigation import ComparisonPlan, EntryRequest, entries
from app.services.report_language import present_metadata


def weekly_metadata():
    return {'schema': [{'name': name, 'is_date': name == 'week_start_date', 'is_numeric': name in {'revenue', 'units_sold'},
                        'analysis_role': 'metric' if name in {'revenue', 'units_sold'} else 'temporal_dimension' if name == 'week_start_date' else 'dimension'}
                       for name in ['week_start_date', 'region', 'category', 'channel', 'revenue', 'units_sold']]}


async def test_weekly_records_have_descriptive_names_without_changing_positions_or_values(tmp_path):
    path = tmp_path / 'weekly.parquet'
    pl.DataFrame({'week_start_date': [date(2025, 2, 3)], 'region': ['North America'], 'category': ['Apparel'],
                  'channel': ['Retail'], 'revenue': [15984.01], 'units_sold': [269]}).write_parquet(path)
    metadata = weekly_metadata()
    original = deepcopy(metadata)
    analysis = SimpleNamespace(id=uuid4(), row_count=1, metadata_=metadata, insights=[], file=SimpleNamespace(storage_path=str(path)))
    shown = await entries(analysis, EntryRequest(kind='comparison', comparison=ComparisonPlan(aggregation='count')))
    assert shown['record_context']['plural'] == 'weekly sales records'
    assert shown['entries'][0]['record_label'] == '3 Feb 2025 · North America · Apparel · Retail'
    assert shown['entries'][0]['entry_number'] == 1
    assert shown['entries'][0]['values']['revenue'] == 15984.01
    assert metadata == original


def test_missing_week_or_sales_fields_do_not_label_other_datasets_as_weekly_sales():
    metadata = weekly_metadata()
    metadata['schema'] = [field for field in metadata['schema'] if field['name'] != 'week_start_date']
    assert record_context(metadata) is None
    schema = {'Organisation Name': {'analysis_role': 'identifier'}}
    assert record_label({'Organisation Name': 'Acme Ltd'}, schema, None, 12) == 'Acme Ltd'
    assert record_label({'Organisation Name': None}, schema, None, 12) == 'Record 12'


def test_weekly_chart_context_survives_already_presented_charts_and_keeps_counts():
    chart = {'type': 'histogram', 'xAxis': 'revenue', 'echarts_option': {'xAxis': {'name': 'Revenue', 'data': ['10K-12K', '12K-14K']},
             'series': [{'data': [224, 261]}]}}
    plain = present_histogram(chart)
    shown = present_histogram(plain, record_context(weekly_metadata()))
    assert shown['title'] == 'Weekly sales records by revenue range'
    assert '261 of the 485 weekly sales records shown' in shown['description']
    assert shown['echarts_option']['series'][0]['data'] == [224, 261]
    assert shown['echarts_option']['series'][0]['name'] == 'Weekly sales records'
    assert present_histogram(shown, record_context(weekly_metadata())) == shown


def test_dated_sales_files_name_their_rows_without_claiming_unique_invoices():
    for amount, markers in (("money", ["cash_type", "coffee_name"]),
                            ("total", ["invoice_id", "branch", "product_line"])):
        schema = [
            {"name": "date", "is_date": True, "is_numeric": False, "analysis_role": "temporal_dimension"},
            {"name": amount, "is_date": False, "is_numeric": True, "analysis_role": "metric"},
            *[{"name": name, "is_date": False, "is_numeric": False, "analysis_role": "dimension"}
              for name in markers],
        ]
        metadata = {"schema": schema}
        context = record_context(metadata)
        assert context["plural"] == "sales records"
        assert "invoice" in context["description"]
        _, summary = present_metadata(metadata, "Your file has 100 entries and 5 fields.")
        assert summary == "Your file has 100 sales records and 5 fields."
