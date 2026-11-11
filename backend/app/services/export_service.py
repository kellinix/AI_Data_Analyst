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

from app.analytics.labels import source_column_label
from app.analytics.report_relevance import useful_charts, useful_insights
from app.services.export_charts import PdfChart, add_excel_charts, normalise_charts
from app.services.report_language import provided_definitions

_IMPORTANCE_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_KNOWN_CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥"}


def _format_metric_value(data: dict[str, Any]) -> str:
    value = data.get("value")
    if not isinstance(value, int | float):
        return str(value) if value is not None else "N/A"
    if data.get("is_currency"):
        formatted = f"{_currency_prefix(data)}{value:,.2f}"
    elif float(value).is_integer():
        formatted = f"{value:,.0f}"
    else:
        # Keep small fractional measures visible instead of rounding them to
        # zero or one. Numeric values in Excel retain their full precision.
        decimals = 2 if abs(value) >= 0.01 else 6
        formatted = f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
        if float(formatted.replace(",", "")) == 0 and value != 0:
            formatted = f"{value:.3g}"
    if data.get("is_percent"):
        formatted += "%"
    if data.get("unit") == "million":
        formatted += " million"
    return formatted


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


def _definition_fields(metadata: dict[str, Any] | None, charts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    fields = provided_definitions(metadata)
    for chart in charts or []:
        reader = (chart.get("echarts_option") or {}).get("_reader") or {}
        for name, definition in (reader.get("definitions") or {}).items():
            fields.setdefault(name, {"name": name, "display_label": (reader.get("labels") or {}).get(name),
                                     "data_definition": definition})
    return list(fields.values())


def _code_text(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False) if value is None or isinstance(value, bool) or value == "" else str(value)


def _definition_source(definition: dict[str, Any]) -> str:
    return " / ".join(str(definition[key]) for key in ("source_table", "source_sheet", "source_role", "source_column")
                      if definition.get(key))


def build_pdf_report(
    *,
    name: str,
    row_count: int | None,
    column_count: int | None,
    summary: str | None,
    insights: list[dict[str, Any]],
    charts: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
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
        textColor=colors.HexColor("#1e3a8a"), keepWithNext=True,
    )
    body = ParagraphStyle("Body", parent=styles["BodyText"], spaceAfter=6, leading=15)
    item_heading = ParagraphStyle("ItemHeading", parent=body, keepWithNext=True)

    story: list[Any] = []
    story.append(Paragraph(escape(name), styles["Title"]))
    if row_count is not None:
        story.append(Paragraph(f"{row_count:,} records analysed", styles["Normal"]))
    story.append(Spacer(1, 12))

    if summary:
        story.append(Paragraph("What your data shows", heading))
        for line in summary.splitlines():
            if line.strip():
                story.append(Paragraph(escape(line.strip()), body))
    if limitations:
        story.append(Paragraph("What these results cover", heading))
        for note in limitations[:8]:
            if note.strip():
                story.append(Paragraph(escape(note.strip()), body))

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
            formatted = _format_metric_value(data)
            rows.append([kpi.get("title", ""), formatted])
        table = Table(rows, colWidths=[9 * cm, 6 * cm])
        table.setStyle(_table_style())
        story.append(KeepTogether([Paragraph("Important numbers", heading), table]))

    findings = _finding_insights(insights)
    if findings:
        story.append(Paragraph("Findings", heading))
        for finding in findings[:10]:
            story.append(Paragraph(f"<b>{finding.get('title', '')}</b>", item_heading))
            story.append(Paragraph(finding.get("description", ""), body))

    recommendations = _recommendation_insights(insights)
    if recommendations:
        story.append(Paragraph("Recommended Actions", heading))
        for rec in recommendations[:8]:
            story.append(Paragraph(f"<b>{rec.get('title', '')}</b>", item_heading))
            story.append(Paragraph(rec.get("description", ""), body))

    definitions = _definition_fields(metadata, charts)
    if definitions:
        story.append(Paragraph("What the fields and codes mean", heading))
        story.append(Paragraph("These explanations come from the supplied data guide.", body))
        for field in definitions:
            definition = field["data_definition"]
            story.append(Paragraph(escape(source_column_label(field)), styles["Heading3"]))
            if _definition_source(definition):
                story.append(Paragraph(escape(f"The source field is {_definition_source(definition)}."), body))
            description = definition.get("description") or field.get("display_description")
            if description:
                story.append(Paragraph(escape(str(description)), body))
            if definition.get("unit"):
                story.append(Paragraph(escape(f"The supplied unit is {definition['unit']}."), body))
            time_basis = definition.get("time_basis") or {}
            if time_basis.get("kind") == "relative_day":
                story.append(Paragraph(escape(
                    f"Days are counted from {time_basis['origin']}. Zero is that starting point. "
                    "Negative numbers are days before it, and positive numbers are days after it."), body))
            codes = definition.get("value_labels") or []
            if codes:
                header = ParagraphStyle("DefinitionTableHeader", parent=body, textColor=colors.white)
                rows = [[Paragraph("Recorded code", header), Paragraph("Meaning from the guide", header)]]
                for code in codes:
                    meaning = str(code["label"])
                    if code.get("description"):
                        meaning += " - " + str(code["description"])
                    rows.append([Paragraph(escape(_code_text(code.get("value"))), body), Paragraph(escape(meaning), body)])
                table = Table(rows, colWidths=[3 * cm, 12 * cm], repeatRows=1)
                table.setStyle(_table_style())
                story.append(table)
            source = definition.get("source") or {}
            for key, wording in (("title", "The supplied guide is"), ("version", "The supplied guide version is"), ("url", "Its source link is")):
                if source.get(key):
                    story.append(Paragraph(escape(f"{wording} {source[key]}."), body))

    if not summary and not kpis and not findings and not recommendations and not visual_charts and not definitions:
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
    limitations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
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
    overview.write(1, 0, "Records analysed")
    overview.write(1, 1, row_count if row_count is not None else "Unknown")
    overview.write(2, 0, "Information fields")
    overview.write(2, 1, column_count if column_count is not None else "Unknown")
    if summary:
        overview.write(4, 0, "What your data shows")
        overview.write(4, 1, summary, wrap_fmt)
        overview.set_row(4, 60)
    if limitations:
        overview.write(6, 0, "What these results cover")
        overview.write(6, 1, "\n".join(note for note in limitations[:8] if note.strip()), wrap_fmt)
        overview.set_row(6, min(200, 22 * len(limitations[:8])))

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
            unit = " (millions)" if data.get("unit") == "million" and "million" not in str(kpi.get("title", "")).lower() else ""
            sheet.write(row, 0, f"{kpi.get('title', '')}{unit}")
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

    definitions = _definition_fields(metadata, charts)
    if definitions:
        sheet = workbook.add_worksheet("Data Definitions")
        headers = ["Report field", "Meaning", "Original source field", "Description", "Recorded code", "Code meaning",
                   "Code description", "Unit", "Time basis", "Supplied guide", "Guide URL", "Guide version", "Definition source"]
        sheet.write_row(0, 0, headers, header_fmt)
        sheet.set_column(0, 2, 26)
        sheet.set_column(3, 3, 65)
        sheet.set_column(4, 4, 18)
        sheet.set_column(5, 8, 35)
        sheet.set_column(9, 12, 45)
        row_number = 1
        for field in definitions:
            definition = field["data_definition"]
            source = definition.get("source") or {}
            time_basis = definition.get("time_basis") or {}
            for code in definition.get("value_labels") or [{}]:
                row = [field["name"], source_column_label(field), _definition_source(definition),
                       field.get("display_description") or definition.get("description") or "",
                       _code_text(code["value"]) if "value" in code else "", code.get("label") or "",
                       code.get("description") or "", definition.get("unit") or "", time_basis.get("origin") or "",
                       source.get("title") or "", source.get("url") or "", source.get("version") or "", "Supplied data guide"]
                for column, value in enumerate(row):
                    sheet.write_string(row_number, column, str(value), wrap_fmt)
                row_number += 1
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, max(row_number - 1, 1), len(headers) - 1)

    add_excel_charts(workbook, normalise_charts(useful_charts(charts or [])))

    workbook.close()
    return buffer.getvalue()
