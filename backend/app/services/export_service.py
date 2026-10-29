"""Generate downloadable PDF and Excel reports for a completed analysis."""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xlsxwriter import Workbook

from app.analytics.report_relevance import useful_charts, useful_insights
from app.services.export_charts import PdfChart, add_excel_charts, normalise_charts

_IMPORTANCE_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_KNOWN_CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥"}


def _currency_prefix(data: dict[str, Any]) -> str:
    code = str(data.get("currency") or "").upper()
    symbol = data.get("currency_symbol") or _KNOWN_CURRENCY_SYMBOLS.get(code)
    return str(symbol) if symbol else f"{code} " if code else ""


def _kpi_insights(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in useful_insights(insights) if i.get("type") == "summary"]


def _finding_insights(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (i for i in useful_insights(insights) if i.get("type") not in {"summary", "recommendation"}),
        key=lambda i: _IMPORTANCE_ORDER.get(i.get("importance", "medium"), 2),
    )


def _recommendation_insights(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (i for i in useful_insights(insights) if i.get("type") == "recommendation"),
        key=lambda i: _IMPORTANCE_ORDER.get(i.get("importance", "medium"), 2),
    )


def build_pdf_report(
    *,
    name: str,
    row_count: int | None,
    column_count: int | None,
    summary: str | None,
    insights: list[dict[str, Any]],
    charts: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render the analysis narrative and its saved dashboard charts."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        title=name,
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=16, spaceAfter=8,
        textColor=colors.HexColor("#1e3a8a"),
    )
    body = ParagraphStyle("Body", parent=styles["BodyText"], spaceAfter=6, leading=15)

    story: list[Any] = []
    story.append(Paragraph(escape(name), styles["Title"]))
    row_text = f"{row_count:,} rows" if row_count is not None else "Unknown rows"
    col_text = f"{column_count} columns" if column_count is not None else "unknown columns"
    story.append(Paragraph(f"{row_text} &middot; {col_text}", styles["Normal"]))
    story.append(Spacer(1, 12))

    if summary:
        story.append(Paragraph("Executive Summary", heading))
        for line in summary.splitlines():
            if line.strip():
                story.append(Paragraph(escape(line.strip()), body))

    visual_charts = normalise_charts(useful_charts(charts or []))
    if visual_charts:
        for index, chart in enumerate(visual_charts):
            parts: list[Any] = []
            if index == 0:
                parts.append(Paragraph(f"Visual Charts ({len(visual_charts)})", heading))
            parts.append(Paragraph(escape(chart.title), styles["Heading3"]))
            if chart.description:
                parts.append(Paragraph(escape(chart.description), body))
            parts.extend([Spacer(1, 6), PdfChart(chart), Spacer(1, 10)])
            story.append(KeepTogether(parts))

    kpis = _kpi_insights(insights)
    if kpis:
        rows = [["Metric", "Value"]]
        for kpi in kpis:
            data = kpi.get("data") or {}
            value = data.get("value")
            is_currency = data.get("is_currency")
            formatted = (
                f"{_currency_prefix(data)}{value:,.2f}" if is_currency and isinstance(value, int | float)
                else f"{value:,.0f}" if isinstance(value, int | float)
                else str(value) if value is not None else "N/A"
            )
            rows.append([kpi.get("title", ""), formatted])
        table = Table(rows, colWidths=[9 * cm, 6 * cm])
        table.setStyle(_table_style())
        story.append(KeepTogether([Paragraph("Key Metrics", heading), table]))

    findings = _finding_insights(insights)
    if findings:
        story.append(Paragraph("Findings", heading))
        for finding in findings[:10]:
            story.append(Paragraph(f"<b>{finding.get('title', '')}</b>", body))
            story.append(Paragraph(finding.get("description", ""), body))

    recommendations = _recommendation_insights(insights)
    if recommendations:
        story.append(Paragraph("Recommended Actions", heading))
        for rec in recommendations[:8]:
            story.append(Paragraph(f"<b>{rec.get('title', '')}</b>", body))
            story.append(Paragraph(rec.get("description", ""), body))

    if not summary and not kpis and not findings and not recommendations and not visual_charts:
        story.append(Paragraph(
            "This analysis has not finished generating content yet.", body
        ))

    doc.build(story)
    return buffer.getvalue()


def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ])


def build_excel_report(
    *,
    name: str,
    row_count: int | None,
    column_count: int | None,
    summary: str | None,
    insights: list[dict[str, Any]],
    charts: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render a multi-sheet workbook with editable charts and source values."""
    buffer = io.BytesIO()
    workbook = Workbook(buffer, {"in_memory": True})
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#1e3a8a", "font_color": "white", "border": 1,
    })
    wrap_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})
    currency_formats: dict[str, Any] = {}

    overview = workbook.add_worksheet("Overview")
    overview.set_column(0, 0, 24)
    overview.set_column(1, 1, 80)
    overview.write(0, 0, "Analysis name", header_fmt)
    overview.write(0, 1, name, header_fmt)
    overview.write(1, 0, "Rows")
    overview.write(1, 1, row_count if row_count is not None else "Unknown")
    overview.write(2, 0, "Columns")
    overview.write(2, 1, column_count if column_count is not None else "Unknown")
    if summary:
        overview.write(4, 0, "Executive summary")
        overview.write(4, 1, summary, wrap_fmt)
        overview.set_row(4, 60)

    kpis = _kpi_insights(insights)
    if kpis:
        sheet = workbook.add_worksheet("Key Metrics")
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 1, 20)
        sheet.write(0, 0, "Metric", header_fmt)
        sheet.write(0, 1, "Value", header_fmt)
        for row, kpi in enumerate(kpis, start=1):
            data = kpi.get("data") or {}
            value = data.get("value")
            is_currency = data.get("is_currency")
            sheet.write(row, 0, kpi.get("title", ""))
            if isinstance(value, int | float):
                fmt = None
                if is_currency:
                    prefix = _currency_prefix(data)
                    if prefix not in currency_formats:
                        currency_formats[prefix] = workbook.add_format({
                            "num_format": f'"{prefix}"#,##0.00' if prefix else "#,##0.00",
                        })
                    fmt = currency_formats[prefix]
                sheet.write_number(row, 1, value, fmt)
            else:
                sheet.write(row, 1, value if value is not None else "N/A")

    findings = _finding_insights(insights)
    if findings:
        sheet = workbook.add_worksheet("Findings")
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 1, 70)
        sheet.set_column(2, 2, 14)
        sheet.write_row(0, 0, ["Finding", "Description", "Importance"], header_fmt)
        for row, finding in enumerate(findings, start=1):
            sheet.write(row, 0, finding.get("title", ""))
            sheet.write(row, 1, finding.get("description", ""), wrap_fmt)
            sheet.write(row, 2, finding.get("importance", ""))

    recommendations = _recommendation_insights(insights)
    if recommendations:
        sheet = workbook.add_worksheet("Recommended Actions")
        sheet.set_column(0, 0, 32)
        sheet.set_column(1, 1, 70)
        sheet.set_column(2, 2, 14)
        sheet.write_row(0, 0, ["Action", "Description", "Priority"], header_fmt)
        for row, rec in enumerate(recommendations, start=1):
            sheet.write(row, 0, rec.get("title", ""))
            sheet.write(row, 1, rec.get("description", ""), wrap_fmt)
            sheet.write(row, 2, rec.get("importance", ""))

    add_excel_charts(workbook, normalise_charts(useful_charts(charts or [])))

    workbook.close()
    return buffer.getvalue()
