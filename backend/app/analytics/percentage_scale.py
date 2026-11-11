"""Keep an unknown percentage representation from becoming a confident claim."""
from __future__ import annotations

import json
import re
from typing import Any

from app.analytics.labels import derive_label

SCALE_WARNING = (
    "These values may be out of 1 or out of 100. The scale has not been confirmed. "
    "We show the numbers as supplied. Check the source definition before using a percent sign."
)


def named_percentage(column: str) -> bool:
    return bool("%" in column or re.search(r"(?:^|_)(?:pct|percent|percentage)(?:_|$)", column.lower()))


def ambiguous_percentage(column: str, stats: dict[str, Any]) -> bool:
    minimum, maximum = stats.get("min"), stats.get("max")
    bounded = minimum is not None and maximum is not None and -1 <= minimum <= maximum <= 1
    lower_quartile, upper_quartile = stats.get("p25"), stats.get("p75")
    central_fraction = lower_quartile is not None and upper_quartile is not None and -1 <= lower_quartile <= upper_quartile <= 1
    return bool(named_percentage(column) and (bounded or central_fraction))


def raw_percentage_label(column: str) -> str:
    label = re.sub(r"\b(?:pct|percent|percentage)\b|%", "", derive_label(column), flags=re.I)
    return (" ".join(label.split()) or "Value") + " (raw scale)"


def clarify_percentage_display(statistics: dict, display: dict, charts: list[dict]) -> None:
    """Set labels and warnings before the shared chart display layer runs."""
    names = {column["name"] for column in statistics.get("schema", []) if column.get("percentage_scale") == "unconfirmed"}
    if not names:
        return
    replacements = {}
    for item in display.get("columns", []):
        if item.get("name") in names:
            replacement = raw_percentage_label(item["name"])
            replacements[str(item.get("label") or derive_label(item["name"]))] = replacement
            item["label"] = replacement
            item["description"] = SCALE_WARNING
    chart_warnings = set()
    source_charts = {chart.get("id"): chart for chart in charts}
    for chart in charts:
        references = json.dumps([chart.get("xAxis"), chart.get("yAxis"), chart.get("series"), (chart.get("echarts_option") or {}).get("_columns")])
        if any(json.dumps(name) in references for name in names):
            chart_warnings.add(chart.get("id"))
            option = chart.setdefault("echarts_option", {})
            option["_display_warnings"] = list(dict.fromkeys([*(option.get("_display_warnings") or []), SCALE_WARNING]))
    for item in display.get("charts", []):
        if item.get("id") not in chart_warnings:
            continue
        for field in ("title", "description"):
            text = str(item.get(field) or "")
            for original, replacement in sorted(replacements.items(), key=lambda pair: len(pair[0]), reverse=True):
                text = re.sub(re.escape(original), lambda _, replacement=replacement: replacement, text, flags=re.I)
            item[field] = text
        from app.services.semantic_wrangler import _friendly_chart_title

        labels = {column["name"]: column["label"] for column in display.get("columns", [])}
        item["title"] = _friendly_chart_title(source_charts[item["id"]], labels)
        item["description"] = (item["description"] + " " + SCALE_WARNING).strip()
