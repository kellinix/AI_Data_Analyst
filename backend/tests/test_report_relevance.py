from app.analytics.report_relevance import useful_charts, useful_insights


def test_sales_report_omits_ranges_balanced_counts_and_weak_relationships():
    trend = {"id": "trend", "type": "line", "title": "Revenue over time"}
    split = {"id": "split", "type": "donut", "echarts_option": {"series": [{"data": [{"value": 312}, {"value": 312}]}]}}
    weak = {"type": "scatter", "description": "A weak relationship"}
    assert useful_charts([trend, {"type": "histogram"}, split, weak]) == [trend]
    # A register without measures still benefits from record counts.
    assert useful_charts([split]) == [split]


def test_findings_keep_substantive_content_and_omit_filler_and_duplicates():
    warning = {"type": "anomaly", "title": "Revenue dropped", "importance": "high"}
    kpi = {"type": "summary", "title": "Revenue", "importance": "low"}
    filler = {"type": "recommendation", "title": "Track revenue regularly", "importance": "medium"}
    minor = {"type": "trend", "title": "Minor change", "importance": "low"}
    assert useful_insights([warning, warning.copy(), kpi, filler, minor]) == [warning, kpi]
