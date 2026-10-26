"""Turn saved dashboard chart values into PDF drawings and editable Excel charts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from reportlab.lib import colors
from reportlab.platypus import Flowable
from xlsxwriter import Workbook

from app.analytics.histogram_presentation import present_histogram
from app.analytics.line_presentation import present_time_line
from app.services.report_language import chart_description

PALETTE = ("#7350D8", "#15B8A6", "#F28B6B", "#E5AE3E", "#4F6FE1", "#A7CF32")


@dataclass
class ExportChart:
    kind: str
    title: str
    description: str
    categories: list[str]
    series: list[tuple[str, list[float | None]]]
    points: list[tuple[float, float]]
    horizontal: bool
    stacked: bool
    x_label: str
    y_label: str
    palette: list[str]
    connect_line: bool


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _text(value: Any) -> str:
    return str(value) if value is not None else ""


def _color(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else None


def normalise_charts(charts: list[dict[str, Any]] | None) -> list[ExportChart]:
    """Read only populated ECharts data; never infer missing chart values."""
    result: list[ExportChart] = []
    for raw in charts or []:
        if not isinstance(raw, dict):
            continue
        raw = present_time_line(present_histogram(raw))
        kind = raw.get("type")
        if kind not in {"line", "bar", "donut", "scatter", "histogram"}:
            continue
        option = raw.get("echarts_option") or {}
        if not isinstance(option, dict):
            continue
        option_series = [s for s in (option.get("series") or []) if isinstance(s, dict)]
        x_axis = option.get("xAxis") if isinstance(option.get("xAxis"), dict) else {}
        y_axis = option.get("yAxis") if isinstance(option.get("yAxis"), dict) else {}
        horizontal = kind in {"bar", "histogram"} and y_axis.get("type") == "category"
        palette = [_color(value) for value in (raw.get("color_scheme") or [])]
        palette = [value for value in palette if value] or list(PALETTE)
        categories: list[str] = []
        series: list[tuple[str, list[float | None]]] = []
        points: list[tuple[float, float]] = []
        if kind == "donut":
            data = option_series[0].get("data", []) if option_series else []
            for item in data:
                if isinstance(item, dict) and (value := _number(item.get("value"))) is not None:
                    categories.append(_text(item.get("name")))
                    series.append((_text(item.get("name")), [value]))
        elif kind == "scatter":
            data = option_series[0].get("data", []) if option_series else []
            for item in data:
                if isinstance(item, list | tuple) and len(item) >= 2:
                    x, y = _number(item[0]), _number(item[1])
                    if x is not None and y is not None:
                        points.append((x, y))
        else:
            axis = y_axis if horizontal else x_axis
            categories = [_text(value) for value in axis.get("data", [])]
            for index, item in enumerate(option_series):
                data = item.get("data", [])
                values = [_number(value) for value in data[: len(categories)]]
                values.extend([None] * (len(categories) - len(values)))
                series.append((_text(item.get("name") or f"Series {index + 1}"), values))
        if not points and not any(value is not None for _, values in series for value in values):
            continue
        result.append(ExportChart(
            kind=kind,
            title=_text(raw.get("title") or "Chart"),
            description=_text(chart_description(raw.get("description"))),
            categories=categories,
            series=series,
            points=points,
            horizontal=horizontal,
            stacked=any(item.get("stack") for item in option_series),
            x_label=_text(x_axis.get("name") or raw.get("xAxis")),
            y_label=_text(y_axis.get("name") or raw.get("yAxis")),
            palette=palette,
            connect_line=not (kind == "line" and option_series and
                              (option_series[0].get("lineStyle") or {}).get("opacity") == 0),
        ))
    return result


def _short(value: str, limit: int = 22) -> str:
    text = value.encode("latin-1", "replace").decode("latin-1")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _range(values: list[float], include_zero: bool = True) -> tuple[float, float]:
    low = min(values + ([0] if include_zero else []))
    high = max(values + ([0] if include_zero else []))
    if low == high:
        delta = abs(low) * 0.1 or 1
        return low - delta, high + delta
    return low, high


def _tick(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:.0f}" if abs(value) >= 10 else f"{value:.2g}"


class PdfChart(Flowable):
    """Compact, vector chart drawn from the same values as the dashboard."""

    def __init__(self, chart: ExportChart) -> None:
        super().__init__()
        self.chart = chart
        self.width = 460
        self.height = (max(220, len(chart.categories) * 23 + 45) if chart.horizontal
                       else max(250, len(chart.categories) * 18 + 38) if chart.kind == "donut"
                       else 250)

    def draw(self) -> None:
        if self.chart.kind == "donut":
            self._donut()
        elif self.chart.kind == "scatter":
            self._scatter()
        elif self.chart.horizontal:
            self._horizontal()
        else:
            self._axes()

    def _grid(self, x: float, y: float, width: float, height: float, low: float, high: float) -> None:
        c = self.canv
        c.setFont("Helvetica", 7)
        for tick in range(5):
            line_y = y + height * tick / 4
            c.setStrokeColor(colors.HexColor("#E8E0F0"))
            c.line(x, line_y, x + width, line_y)
            c.setFillColor(colors.HexColor("#716B86"))
            c.drawRightString(x - 5, line_y - 2, _tick(low + (high - low) * tick / 4))

    def _axes(self) -> None:
        chart, c = self.chart, self.canv
        x0, y0, w, h = 58, 38, 384, 185
        values = [value for _, data in chart.series for value in data if value is not None]
        if chart.stacked:
            values.extend(sum(max(0, data[i] or 0) for _, data in chart.series)
                          for i in range(len(chart.categories)))
        low, high = _range(values)
        self._grid(x0, y0, w, h, low, high)
        count = len(chart.categories)
        if not count:
            return
        for index in {0, count // 2, count - 1}:
            x = x0 + w * (index / max(1, count - 1) if chart.kind == "line" else (index + .5) / count)
            c.setFillColor(colors.HexColor("#716B86"))
            c.setFont("Helvetica", 7)
            c.drawCentredString(x, y0 - 13, _short(chart.categories[index], 16))
        baseline = y0 + h * (0 - low) / (high - low)
        for series_index, (name, data) in enumerate(chart.series):
            color = colors.HexColor(chart.palette[series_index % len(chart.palette)])
            c.setStrokeColor(color)
            c.setFillColor(color)
            if chart.kind == "line":
                previous = None
                for index, value in enumerate(data):
                    if value is None:
                        previous = None
                        continue
                    point = (x0 + w * index / max(1, count - 1), y0 + h * (value - low) / (high - low))
                    if previous and chart.connect_line:
                        c.setLineWidth(1.8)
                        c.line(*previous, *point)
                    c.circle(*point, 1.7, fill=1, stroke=0)
                    previous = point
            else:
                group_width = w / count
                bar_width = group_width * .7 / (1 if chart.stacked else len(chart.series))
                for index, value in enumerate(data):
                    if value is None:
                        continue
                    start = sum(max(0, item[1][index] or 0) for item in chart.series[:series_index]) if chart.stacked else 0
                    y_start = y0 + h * (start - low) / (high - low) if chart.stacked else baseline
                    y_value = y0 + h * (start + value - low) / (high - low) if chart.stacked else y0 + h * (value - low) / (high - low)
                    x = x0 + group_width * (index + .15) + (0 if chart.stacked else series_index * bar_width)
                    c.rect(x, min(y_start, y_value), max(1, bar_width - 1), abs(y_value - y_start), fill=1, stroke=0)
            if len(chart.series) > 1:
                legend_x = x0 + (series_index % 3) * 125
                legend_y = 237 - (series_index // 3) * 11
                c.rect(legend_x, legend_y, 7, 7, fill=1, stroke=0)
                c.setFillColor(colors.HexColor("#29213F"))
                c.setFont("Helvetica", 7)
                c.drawString(legend_x + 10, legend_y, _short(name, 17))

    def _horizontal(self) -> None:
        chart, c = self.chart, self.canv
        x0, y0, w = 145, 25, 295
        count = len(chart.categories)
        values = [value for _, data in chart.series for value in data if value is not None]
        low, high = _range(values)
        baseline = x0 + w * (0 - low) / (high - low)
        for index, label in enumerate(chart.categories):
            y = y0 + (index + .5) * 23
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#29213F"))
            c.drawRightString(x0 - 9, y - 2, _short(label, 25))
            for series_index, (_, data) in enumerate(chart.series):
                value = data[index]
                if value is None:
                    continue
                end = x0 + w * (value - low) / (high - low)
                c.setFillColor(colors.HexColor(chart.palette[series_index % len(chart.palette)]))
                c.rect(min(baseline, end), y - 5, max(1, abs(end - baseline)), 10, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#E8E0F0"))
        c.line(baseline, y0, baseline, y0 + count * 23)
        c.setFillColor(colors.HexColor("#716B86"))
        c.setFont("Helvetica", 7)
        c.drawString(x0, y0 - 12, _tick(low))
        c.drawRightString(x0 + w, y0 - 12, _tick(high))

    def _donut(self) -> None:
        chart, c = self.chart, self.canv
        total = sum(values[0] or 0 for _, values in chart.series)
        if total <= 0:
            return
        angle = 90.0
        center_y = self.height / 2
        for index, (name, values) in enumerate(chart.series):
            value = values[0] or 0
            extent = 360 * value / total
            c.setFillColor(colors.HexColor(chart.palette[index % len(chart.palette)]))
            c.wedge(40, center_y - 95, 230, center_y + 95, angle, extent, fill=1, stroke=0)
            angle += extent
            legend_y = self.height - 37 - index * 18
            c.rect(250, legend_y, 8, 8, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#29213F"))
            c.setFont("Helvetica", 8)
            c.drawString(263, legend_y + 1, f"{_short(name, 23)}  {_tick(value)}")
        c.setFillColor(colors.white)
        c.circle(135, center_y, 51, fill=1, stroke=0)

    def _scatter(self) -> None:
        chart, c = self.chart, self.canv
        x0, y0, w, h = 58, 30, 384, 190
        xs, ys = [point[0] for point in chart.points], [point[1] for point in chart.points]
        x_low, x_high = _range(xs, include_zero=False)
        y_low, y_high = _range(ys, include_zero=False)
        self._grid(x0, y0, w, h, y_low, y_high)
        c.setFillColor(colors.HexColor(chart.palette[0]))
        for x, y in chart.points:
            c.circle(x0 + w * (x - x_low) / (x_high - x_low),
                     y0 + h * (y - y_low) / (y_high - y_low), 1.8, fill=1, stroke=0)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#716B86"))
        c.drawString(x0, y0 - 14, _tick(x_low))
        c.drawRightString(x0 + w, y0 - 14, _tick(x_high))


def add_excel_charts(workbook: Workbook, charts: list[ExportChart]) -> None:
    """Add native Excel charts and the exact source values used by each chart."""
    if not charts:
        return
    display = workbook.add_worksheet("Charts")
    data = workbook.add_worksheet("Chart Data")
    display.set_column(0, 0, 17)
    display.set_column(1, 12, 12)
    data.set_column(0, 0, 32)
    data.set_column(1, 8, 18)
    title_fmt = workbook.add_format({"bold": True, "font_size": 14, "font_color": "#29213F"})
    heading_fmt = workbook.add_format({"bold": True, "bg_color": "#302056", "font_color": "#FFFFFF"})
    chart_row, data_row = 0, 0
    for chart in charts:
        display.write_string(chart_row, 0, chart.title, title_fmt)
        if chart.description:
            display.write_string(chart_row + 1, 0, chart.description)
        data.write_string(data_row, 0, chart.title, heading_fmt)
        data.write_string(data_row + 1, 0, chart.x_label or "Category", heading_fmt)
        if chart.kind == "scatter":
            data.write_string(data_row + 1, 1, chart.y_label or "Value", heading_fmt)
            for index, (x, y) in enumerate(chart.points, start=data_row + 2):
                data.write_number(index, 0, x)
                data.write_number(index, 1, y)
            excel_chart = workbook.add_chart({"type": "scatter"})
            excel_chart.add_series({
                "name": chart.title,
                "categories": ["Chart Data", data_row + 2, 0, data_row + 1 + len(chart.points), 0],
                "values": ["Chart Data", data_row + 2, 1, data_row + 1 + len(chart.points), 1],
                "marker": {"type": "circle", "size": 4, "border": {"color": chart.palette[0]}, "fill": {"color": chart.palette[0]}},
                "line": {"none": True},
            })
            data_row += len(chart.points) + 4
        else:
            if chart.kind == "donut":
                categories = chart.categories
                series = [("Records", [values[0] for _, values in chart.series])]
            else:
                categories, series = chart.categories, chart.series
            for col, (name, _) in enumerate(series, start=1):
                data.write_string(data_row + 1, col, name, heading_fmt)
            for index, category in enumerate(categories, start=data_row + 2):
                data.write_string(index, 0, category)
                for col, (_, values) in enumerate(series, start=1):
                    if values[index - data_row - 2] is not None:
                        data.write_number(index, col, values[index - data_row - 2])
            kind = {"line": "line", "bar": "bar" if chart.horizontal else "column", "histogram": "bar" if chart.horizontal else "column", "donut": "doughnut"}[chart.kind]
            options = {"type": kind}
            if chart.stacked and kind in {"bar", "column"}:
                options["subtype"] = "stacked"
            excel_chart = workbook.add_chart(options)
            for col, (_name, _) in enumerate(series, start=1):
                series_config: dict[str, Any] = {
                    "name": ["Chart Data", data_row + 1, col],
                    "categories": ["Chart Data", data_row + 2, 0, data_row + 1 + len(categories), 0],
                    "values": ["Chart Data", data_row + 2, col, data_row + 1 + len(categories), col],
                    "fill": {"color": chart.palette[(col - 1) % len(chart.palette)]},
                    "line": {"color": chart.palette[(col - 1) % len(chart.palette)]},
                }
                if chart.kind == "donut":
                    series_config["points"] = [
                        {"fill": {"color": chart.palette[index % len(chart.palette)]}}
                        for index in range(len(categories))
                    ]
                elif chart.kind == "line" and not chart.connect_line:
                    series_config["line"] = {"none": True}
                    series_config["marker"] = {
                        "type": "circle", "size": 5,
                        "border": {"color": chart.palette[(col - 1) % len(chart.palette)]},
                        "fill": {"color": chart.palette[(col - 1) % len(chart.palette)]},
                    }
                excel_chart.add_series(series_config)
            if chart.kind == "donut":
                excel_chart.set_hole_size(55)
            data_row += len(categories) + 4
        excel_chart.set_title({"name": chart.title})
        excel_chart.set_legend({"position": "bottom"} if len(chart.series) > 1 or chart.kind == "donut" else {"none": True})
        if chart.kind != "donut":
            excel_chart.set_x_axis({"name": chart.x_label})
            excel_chart.set_y_axis({"name": chart.y_label})
        excel_chart.set_size({"width": 680, "height": 340})
        display.insert_chart(chart_row + 2, 0, excel_chart)
        chart_row += 23
