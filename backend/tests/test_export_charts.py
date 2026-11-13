"""Exported charts retain plotted values in PDF and editable Excel formats."""

from __future__ import annotations

import base64
import io
import re
import zipfile
import zlib

from openpyxl import load_workbook

from app.services.export_charts import normalise_charts
from app.services.export_service import build_excel_report, build_pdf_report
from app.services.report_language import present_chart


def test_long_pdf_categories_stay_distinguishable_and_keep_full_names():
    from app.services.export_charts import PdfChart

    labels = ['Trailers,Commentaries,Deleted Scenes',
              'Trailers,Commentaries,Deleted Scenes,Behind the Scenes']
    chart = {'type': 'bar', 'title': 'Payments by features', 'xAxis': 'Amount', 'yAxis': 'Features',
             'echarts_option': {'yAxis': {'type': 'category', 'data': labels},
                               'series': [{'name': 'Amount', 'data': [10, 20]}]}}
    drawing = PdfChart(normalise_charts([chart])[0])
    assert drawing.label_key == [(1, labels[0]), (2, labels[1])]
    assert drawing._category_label(labels[0], 0, 35) != drawing._category_label(labels[1], 1, 35)
    pdf = build_pdf_report(name='Long labels', row_count=2, column_count=2,
                           summary=None, insights=[], charts=[chart])
    content = b'\n'.join(zlib.decompress(base64.a85decode(stream.strip(), adobe=True))
                         for stream in re.findall(rb'stream\n(.*?)endstream', pdf, re.S))
    assert b'Full labels for' in content
    assert labels[1].encode() in content


def test_vertical_category_charts_identify_every_bar():
    from app.services.export_charts import PdfChart

    labels = ['North', 'South', 'East', 'West', 'Central']
    chart = {'type': 'bar', 'title': 'Orders', 'xAxis': 'Region', 'yAxis': 'Orders',
             'echarts_option': {'xAxis': {'type': 'category', 'data': labels},
                               'series': [{'name': 'Orders', 'data': [10, 20, 30, 40, 50]}]}}
    drawing = PdfChart(normalise_charts([chart])[0])
    assert drawing.numbered_categories
    assert drawing.label_key == list(enumerate(labels, 1))


def _charts() -> list[dict]:
    return [
        {"type": "line", "title": "Revenue over time", "xAxis": "Week", "yAxis": "Revenue",
         "echarts_option": {"xAxis": {"data": ["Jan", "Feb", "Mar"]},
                             "series": [{"name": "Revenue", "data": [10, 20, 15]}]}},
        {"type": "bar", "title": "Revenue by region", "xAxis": "Revenue", "yAxis": "Region",
         "echarts_option": {"yAxis": {"type": "category", "data": ["North", "South"]},
                             "series": [{"name": "Revenue", "data": [30, 40]}]}},
        {"type": "bar", "title": "Orders by region and status", "series_by": "Status",
         "xAxis": "Region", "yAxis": "Orders", "aggregation": "sum",
         "echarts_option": {"xAxis": {"data": ["North", "South"]},
                             "series": [{"name": "Open", "data": [3, 5]},
                                        {"name": "Closed", "data": [2, 4]}]}},
        {"type": "donut", "title": "Status breakdown",
         "echarts_option": {"series": [{"data": [
             {"name": "Open", "value": 7}, {"name": "Closed", "value": 9}]}]}},
        {"type": "scatter", "title": "Spend vs revenue", "xAxis": "Spend", "yAxis": "Revenue",
         "echarts_option": {"series": [{"data": [[1, 2], [3, 6], [4, 9]]}]}},
        {"type": "histogram", "title": "Order size distribution", "xAxis": "Size",
         "echarts_option": {"xAxis": {"data": ["0-10", "10-20"]},
                             "series": [{"name": "Orders", "data": [11, 8]}]}},
        {"type": "line", "title": "Sparse readings", "xAxis": "Week", "yAxis": "Value",
         "echarts_option": {"xAxis": {"data": ["Jan", "Feb", "Mar"]},
                             "series": [{"name": "Value", "data": [3, None, 7],
                                         "lineStyle": {"opacity": 0}}]}},
    ]


def test_all_saved_chart_types_export_as_editable_excel_charts():
    workbook_bytes = build_excel_report(
        name="Sample", row_count=42, column_count=4, summary="Sample summary",
        insights=[], charts=_charts(),
    )
    workbook = load_workbook(io.BytesIO(workbook_bytes))
    assert {"Overview", "Charts", "Chart Data"} <= set(workbook.sheetnames)
    assert len(workbook["Charts"]._charts) == 6
    values = [cell.value for row in workbook["Chart Data"] for cell in row]
    assert {"Recorded revenue by week", "North", "Closed", "Mar", 40, 9} <= set(values)
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as archive:
        chart_names = [name for name in archive.namelist() if name.startswith("xl/charts/chart") and name.endswith(".xml")]
        assert len(chart_names) == 6
        assert any(b"Recorded value by week" in archive.read(name) and b"<a:noFill/>" in archive.read(name)
                   for name in chart_names)


def test_horizontal_bar_chart_data_header_names_the_category_axis():
    workbook_bytes = build_excel_report(
        name="Regional revenue", row_count=2, column_count=2, summary=None,
        insights=[], charts=[_charts()[1]],
    )
    workbook = load_workbook(io.BytesIO(workbook_bytes))

    assert list(workbook["Chart Data"].values)[1:] == [
        ("Region", "Recorded revenue"),
        ("North", 30),
        ("South", 40),
    ]
    assert len(workbook["Charts"]._charts) == 1


def test_pdf_chart_section_adds_vector_visuals_without_dropping_narrative():
    kpis = [{"type": "summary", "title": f"Metric {index}", "data": {"value": index}}
            for index in range(6)]
    plain = build_pdf_report(name="Sample", row_count=42, column_count=4,
                             summary="Sample summary", insights=kpis)
    illustrated = build_pdf_report(name="Sample", row_count=42, column_count=4,
                                   summary="Sample summary", insights=kpis, charts=_charts())
    assert illustrated.startswith(b"%PDF-")
    assert len(illustrated) > len(plain) + 3_000
    assert len(re.findall(rb"/Type\s*/Page\b", illustrated)) >= 2
    page_contents = [
        zlib.decompress(base64.a85decode(stream.strip(), adobe=True))
        for stream in re.findall(rb"stream\n(.*?)endstream", illustrated, re.S)
    ]
    for chart in _charts():
        if chart["type"] == "histogram":
            assert not any(chart["title"].encode() in page for page in page_contents)
            continue
        assert any(present_chart(chart)["title"].encode() in page for page in page_contents)
    assert b"Visual Charts" in page_contents[0]
    assert b"Recorded revenue by week" in page_contents[0]


def test_invalid_or_unpopulated_charts_are_excluded_without_invented_values():
    charts = _charts() + [
        {"type": "line", "title": "Empty", "echarts_option": {"xAxis": {"data": ["Jan"]},
                                                      "series": [{"data": [None]}]}},
        {"type": "scatter", "title": "Bad", "echarts_option": {"series": [{"data": [[1, "nan"]]}]}},
    ]
    assert len(normalise_charts(charts)) == 7


def test_exports_do_not_invent_us_dollars_for_unknown_currency():
    insights = [{"type": "summary", "title": "Sales Amount",
                 "data": {"value": 115431.58, "is_currency": True, "currency": None}}]
    args = {"name": "Coffee", "row_count": 3636, "column_count": 6,
            "summary": None, "insights": insights}
    pdf = build_pdf_report(**args)
    page_content = b"\n".join(
        zlib.decompress(base64.a85decode(stream.strip(), adobe=True))
        for stream in re.findall(rb"stream\n(.*?)endstream", pdf, re.S)
    )
    assert b"115,431.58" in page_content
    assert b"$115,431.58" not in page_content
    workbook = load_workbook(io.BytesIO(build_excel_report(**args)))
    assert workbook["Key Metrics"]["B2"].value == 115431.58
    assert "$" not in workbook["Key Metrics"]["B2"].number_format


def test_exports_explain_scope_and_show_million_unit():
    insights = [{"type": "summary", "title": "Project value", "data": {"value": 12.5, "unit": "million"}}]
    args = {
        "name": "Projects", "row_count": 19, "column_count": 5,
        "summary": "This file contains 19 projects.", "insights": insights,
        "limitations": ["Project counts describe rows, not distinct projects."],
    }
    pdf = build_pdf_report(**args)
    content = b"\n".join(
        zlib.decompress(base64.a85decode(stream.strip(), adobe=True))
        for stream in re.findall(rb"stream\n(.*?)endstream", pdf, re.S)
    )
    assert b"What these results cover" in content
    assert b"Project counts describe rows" in content
    assert b"12.5 million" in content

    workbook = load_workbook(io.BytesIO(build_excel_report(**args)))
    assert workbook["Overview"]["A7"].value == "What these results cover"
    assert "Project counts describe rows" in workbook["Overview"]["B7"].value
    assert workbook["Key Metrics"]["A2"].value == "Project value (millions)"
    assert workbook["Key Metrics"]["B2"].value == 12.5


def test_pdf_section_and_item_headings_stay_with_their_first_explanation():
    insights = [
        {"type": "outlier", "title": "First finding", "importance": "high",
         "description": "A recorded amount needs a closer look."},
        {"type": "recommendation", "title": "Review the source", "importance": "high",
         "description": "Compare the amount with the original file."},
    ]
    for line_count in range(18, 42):
        summary = "\n".join(f"Entry {index} describes values supplied in this file." for index in range(line_count))
        pdf = build_pdf_report(name="Page boundaries", row_count=42, column_count=4,
                               summary=summary, insights=insights)
        pages = [zlib.decompress(base64.a85decode(stream.strip(), adobe=True))
                 for stream in re.findall(rb"stream\n(.*?)endstream", pdf, re.S)]
        for page in pages:
            if b"Findings" in page or b"First finding" in page:
                assert b"A recorded amount needs a closer look." in page
            if b"Recommended Actions" in page or b"Review the source" in page:
                assert b"Compare the amount with the original file." in page
