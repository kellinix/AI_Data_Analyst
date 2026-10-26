from types import SimpleNamespace

import duckdb
import pytest

from app.analytics.admission_context import (
    FIELDS,
    admission_summary,
    clarify_chart,
    clarify_statistics,
    is_admission,
)
from app.analytics.chart_selector import select_charts
from app.analytics.kpi_detector import detect_kpis
from app.analytics.live_filter import populate_chart_option, recompute_kpi
from app.services.investigation import ComparisonPlan, validate_plan


def profile():
    return {"schema": [{"name": name, "is_numeric": True, "is_date": False,
        "analysis_role": "dimension" if name in {"sop", "lor"} else "flag" if name == "research" else "metric"}
        for name in FIELDS], "numeric_stats": {name: {"mean": .72 if name == "chance_of_admit" else 8.,
        "total": 2.88 if name == "chance_of_admit" else 32., "count": 4} for name in FIELDS}}


def test_domain_guard_and_non_additive_comparisons():
    metadata = profile()
    assert is_admission(metadata["schema"])
    assert not is_admission(metadata["schema"][:2])
    clarify_statistics(metadata)
    assert metadata["record_context"]["plural"] == "applicant records"
    with pytest.raises(ValueError, match="rate or average"):
        validate_plan(ComparisonPlan(aggregation="sum", column="cgpa"), metadata)
    kpis = detect_kpis(metadata["schema"], metadata["numeric_stats"])
    assert [k["column"] for k in kpis[:2]] == ["chance_of_admit", "cgpa"]
    assert kpis[0]["value"] == 72 and kpis[0]["is_percent"]
    assert "not an actual acceptance rate" in admission_summary(metadata)


def test_outcome_charts_include_actual_group_sizes_and_filtered_percentages():
    metadata = profile()
    charts = select_charts(metadata["schema"], metadata["numeric_stats"], {}, {}, {"cgpa|chance_of_admit": .8})
    assert len(charts) == 4
    with duckdb.connect() as conn:
        conn.execute("create table data(research integer, chance_of_admit double)")
        conn.execute("insert into data values (0,.4),(1,.8),(1,.9)")
        assert populate_chart_option(conn, charts[0])
        clarify_chart(charts[0])
        option = charts[0]["echarts_option"]
        assert option["_group_counts"] == {"0": 1, "1": 2}
        assert sorted(option["series"][0]["data"]) == [40., 85.]
        assert recompute_kpi(conn, "chance_of_admit", False, True, "research = ?", [1]) == 85.
    clarify_chart(charts[-1])
    assert charts[-1]["echarts_option"]["yAxis"]["_percentage"]
    assert charts[-1]["echarts_option"]["xAxis"]["scale"]


@pytest.mark.asyncio
async def test_admission_comparison_uses_percentages_and_percentage_point_gaps(monkeypatch):
    from app.services import investigation

    conn = duckdb.connect()
    conn.execute("create table data(research integer, chance_of_admit double)")
    conn.execute("insert into data values (0,.4),(1,.8),(1,.9)")

    async def load(_analysis):
        return conn, 3, False

    monkeypatch.setattr(investigation, "_load", load)
    result = await investigation.compare(SimpleNamespace(id="admission", row_count=3, metadata_=profile()),
        ComparisonPlan(aggregation="average", column="chance_of_admit", group_by="research"))
    assert result["value_unit"] == "%"
    assert [row["value"] for row in result["groups"]] == [85., 40.]
    assert "85%" in result["answer"] and "45 percentage points" in result["answer"]
