"""Readable range/count charts, preserving every saved plotted count."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.analytics.labels import derive_label, sentence_label


def _range_label(value: Any) -> str:
    text = str(value)
    number = r"(-?[\d,]+(?:\.\d+)?)([KM]?)"
    match = re.fullmatch(number + r"\s*[-–]\s*" + number, text, flags=re.I)
    def expanded(raw: str, suffix: str) -> str:
        value = float(raw.replace(",", "")) * {"": 1, "K": 1_000, "M": 1_000_000}[suffix.upper()]
        return f"{value:,.2f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"
    if match:
        lower, upper = expanded(match[1], match[2]), expanded(match[3], match[4])
        return f"{lower} to {upper}" if lower != upper else f"about {lower}"
    match = re.fullmatch(number + r"\+", text, flags=re.I)
    if match:
        return f"{expanded(match[1], match[2])} and above"
    match = re.fullmatch(number, text, flags=re.I)
    return expanded(match[1], match[2]) if match else text


def _record_wording(chart: dict, context: dict | None) -> dict:
    if not context or context.get("kind") != "weekly_sales":
        return chart
    option = chart.get("echarts_option") or {}
    measure = str(chart.get("yAxis") or "revenue")
    chart["title"] = f"Weekly sales records by {sentence_label(measure)} range"
    chart["description"] = str(chart.get("description") or "").replace("entries", "weekly sales records")
    chart["xAxis"] = "Weekly sales records"
    option["xAxis"]["name"] = "Sales records"
    option["series"][0]["name"] = "Weekly sales records"
    from app.analytics.chart_specs import build_visual_spec
    chart["visual_spec"] = build_visual_spec(chart)
    return chart


def present_histogram(chart: dict[str, Any], context: dict | None = None) -> dict[str, Any]:
    if chart.get("type") == "donut" and context and context.get("kind") == "sales_transaction":
        result = deepcopy(chart)
        group = str((result.get("series") or [result.get("xAxis") or "group"])[0])
        group_label = "payment method" if group == "cash_type" else sentence_label(derive_label(group))
        result["title"] = f"Number of sales records by {group_label}"
        result["description"] = f"Number of sales records for each {group_label}."
        return result
    if chart.get("type") != "histogram":
        return chart
    result = deepcopy(chart)
    option = result.get("echarts_option") or {}
    if option.get("_range_count_presentation"):
        return _record_wording(result, context)
    axis = option.get("xAxis") or {}
    series = option.get("series") or []
    if not isinstance(axis, dict) or not series or not isinstance(series[0], dict):
        return result
    labels, counts = axis.get("data") or [], series[0].get("data") or []
    if not labels or len(labels) != len(counts) or not all(isinstance(v, int | float) and v >= 0 for v in counts):
        return result
    measure = str(axis.get("name") or derive_label(str(chart.get("xAxis") or "value")))
    if result.get("currency") and result["currency"] not in measure:
        measure += f" ({result['currency']})"
    labels = [_range_label(value) for value in labels]
    if not chart.get("title") or re.fullmatch(r"How .+ is spread", str(chart["title"]), flags=re.I):
        result["title"] = f"{measure} ranges"
    result["description"] = (f"Each bar shows how many entries have {sentence_label(measure)} in that range. "
                             "Longer bars mean more entries. Range limits are rounded.")
    total, largest = sum(counts), max(counts)
    if total:
        largest_indices = [i for i, value in enumerate(counts) if value == largest]
        if len(largest_indices) == 1:
            result["description"] += f" Most common range: about {labels[largest_indices[0]]}, with {largest:,.0f} of the {total:,.0f} entries shown."
        else:
            result["description"] += f" {len(largest_indices)} ranges share the highest count of {largest:,.0f} entries."
    if total >= 10_000:
        result["description"] += " This chart covers up to the first 10,000 entries with a recorded value."
    # Only the quantitative axis is now a count. Retain any known currency
    # in the range heading rather than formatting entry counts as money.
    result["currency"] = None
    result["xAxis"], result["yAxis"] = "Entries", measure
    option["xAxis"] = {"type": "value", "name": "Entries", "minInterval": 1, "nameLocation": "middle", "nameGap": 26}
    option["yAxis"] = {"type": "category", "name": "", "inverse": True,
                       "data": labels, "axisLabel": {"interval": 0, "fontSize": 11}}
    option["grid"] = {"left": 132, "right": 40, "top": 24, "bottom": 40, "containLabel": False}
    option["tooltip"] = {"trigger": "axis", "axisPointer": {"type": "shadow"}}
    series[0] = {**series[0], "name": "Entries", "label": {"show": True, "position": "right", "fontSize": 11},
                 "itemStyle": {**(series[0].get("itemStyle") or {}), "borderRadius": [0, 5, 5, 0]}, "barMaxWidth": 22}
    option["series"] = series
    option["_range_count_presentation"] = True
    result["echarts_option"] = option
    from app.analytics.chart_specs import build_visual_spec
    result["visual_spec"] = build_visual_spec(result)
    return _record_wording(result, context)
