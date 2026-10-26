import duckdb
import polars as pl
import pytest

from app.analytics.chart_selector import select_charts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.live_filter import populate_chart_option, requery_chart
from app.analytics.survey_context import clarify_survey, survey_fields
from app.services.file_processor import FileProcessor
from app.services.investigation import ComparisonPlan, validate_plan
from app.services.semantic_wrangler import SemanticWrangler


def test_headers_and_unpublished_percentages_survive_cleaning(tmp_path):
    path = tmp_path / "survey.csv"
    path.write_text('CountryCode,subset,question_code,question_label,answer,percentage,notes\n'
        'Austria,Group,b1_a,"In your opinion what happens in your country?",Yes,8,\n'
        'Austria,Group,b1_a,"In your opinion what happens in your country?",No,:,\n'
        'Austria,Group,b1_b,"Does a different question apply?",Yes,100,[0]\n', encoding="utf-8")
    processor = FileProcessor()
    raw = processor._read_file(str(path), ".csv")
    assert raw.height == 3 and raw.columns[0] == "CountryCode"
    cleaned, report = processor.clean_dataframe(raw)
    assert cleaned.height == 3 and cleaned["question_code"].n_unique() == 2
    assert cleaned["percentage"].to_list() == [8., None, 100.]
    assert cleaned["notes"].to_list() == [None, None, "[0]"]
    assert report["dropped_rows_missing_critical_metrics"] == 0
    assert not any(i["column"] == "notes" for i in report["source_quality"]["issues"])


@pytest.mark.asyncio
async def test_distinct_question_codes_never_reach_semantic_merging(monkeypatch):
    async def forbidden(*_args):
        raise AssertionError("Question codes must not be sent for semantic merging")
    monkeypatch.setattr(SemanticWrangler, "_canonical_mapping", forbidden)
    frame = pl.DataFrame({"question_code": ["b1_a", "b1_b", "b2_a"], "unnamed": ["h9", "h9_1", "h9_2"]})
    result = await SemanticWrangler().canonicalize_categorical_values(frame)
    assert result.dataframe.equals(frame)


def test_survey_charts_never_mix_questions_or_include_supplied_averages():
    schema = [{"name": n, "is_numeric": n == "percentage", "is_date": False} for n in
        ("countrycode", "subset", "question_code", "question_label", "answer", "percentage", "notes")]
    statistics = {"schema": schema, "row_count": 4, "numeric_stats": {"percentage": {"min": 0, "max": 100}},
        "data_quality": {"issues": [{"column": "notes", "type": "missing_values", "affected_rows": 3},
            {"column": "percentage", "type": "wide_spread", "affected_rows": 1}]}}
    clarify_survey(statistics)
    assert statistics["data_quality"]["issues"] == []
    assert survey_fields(schema)
    assert detect_kpis(schema, {}) == []
    with pytest.raises(ValueError, match="one survey question"):
        validate_plan(ComparisonPlan(aggregation="average", column="percentage", group_by="countrycode"), statistics)
    chart = select_charts(schema, {}, {}, {}, {})[0]
    with duckdb.connect() as conn:
        conn.execute("create table data(countrycode varchar, subset varchar, question_code varchar, question_label varchar, answer varchar, percentage double)")
        conn.execute("insert into data values ('Austria','Group','a1','Question A','Yes',8),('France','Group','a1','Question A','Yes',12),('Average','Group','a1','Question A','Yes',10),('Austria','Group','b1','Question B','Yes',100)")
        assert populate_chart_option(conn, chart)
        assert sorted(chart["echarts_option"]["series"][0]["data"]) == [8., 12.]
        assert "Question A" in chart["description"] and "Survey group: Group" in chart["description"]
        mixed = requery_chart(conn, chart, '"question_code" IN (?, ?)', ['a1', 'b1'])
        assert mixed["echarts_option"]["series"][0]["data"] == []
