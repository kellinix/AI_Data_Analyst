"""Conservative report selection: omit filler without deleting saved evidence."""
from __future__ import annotations

from typing import Any


def useful_charts(charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_measures = any(c.get("type") in {"line", "bar", "stacked_bar", "scatter"} for c in charts)
    result = []
    seen = set()
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        kind = chart.get("type")
        if kind == "histogram":
            continue
        if kind == "bar":
            series = (chart.get("echarts_option") or {}).get("series") or []
            categories = next((item.get("data") for item in (
                (chart.get("echarts_option") or {}).get("xAxis"),
                (chart.get("echarts_option") or {}).get("yAxis"),
            ) if isinstance(item, dict) and item.get("type") == "category"), None)
            if isinstance(categories, list) and len(categories) == 1 and series:
                continue
        if kind == "scatter" and "weak relationship" in str(chart.get("description", "")).lower():
            continue
        if kind in {"pie", "donut"} and has_measures:
            series = (chart.get("echarts_option") or {}).get("series") or []
            data = series[0].get("data", []) if series else []
            values = [d.get("value") for d in data if isinstance(d, dict)]
            if len(values) >= 2 and len(values) == len(data) and len(set(values)) == 1:
                continue
        key = (kind, chart.get("xAxis"), chart.get("yAxis"), tuple(chart.get("series") or []), chart.get("title"))
        if key not in seen:
            result.append(chart)
            seen.add(key)
    return result


def useful_insights(insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for insight in insights:
        title = str(insight.get("title") or "").strip().lower()
        if insight.get("type") != "summary" and insight.get("importance") == "low":
            continue
        if insight.get("type") == "recommendation" and title.startswith("track ") and title.endswith(" regularly"):
            continue
        if insight.get("type") == "recommendation" and (insight.get("data") or {}).get("confidence_source") == "rule:tracking":
            continue
        key = (insight.get("type"), title, str(insight.get("description") or "").strip().lower())
        if key not in seen:
            result.append(insight)
            seen.add(key)
    return result
