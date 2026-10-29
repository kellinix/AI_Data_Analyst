"""Use football terms only when the complete player-stat schema is present."""

from __future__ import annotations

from typing import Any

LABELS = {
    "player": "Player", "squad": "Team", "comp": "Competition",
    "pos": "Position", "gls": "Goals", "ast": "Assists",
    "mp": "Matches played", "starts": "Match starts", "min": "Minutes played",
    "90s": "Full-match equivalents",
    "sot": "Shots on target", "pk": "Penalty goals",
}


def is_football(schema: list[dict[str, Any]]) -> bool:
    fields = {item["name"] for item in schema}
    return {"player", "squad", "comp", "pos"}.issubset(fields) and bool(fields & {"gls", "ast", "mp"})


def football_kpis(statistics: dict[str, Any]) -> list[dict[str, Any]]:
    stats = statistics["numeric_stats"]
    result = []
    for column in ("gls", "ast"):
        value = stats.get(column, {}).get("total")
        if value is not None:
            result.append({"column": column, "kpi_type": "other", "value": value,
                           "is_total": True, "is_currency": False,
                           "count": stats[column].get("count", 0)})
    return result


def football_summary(statistics: dict[str, Any]) -> str:
    rows = int(statistics.get("row_count") or 0)
    kpis = football_kpis(statistics)
    lines = [f"This file has {rows:,} player records. A player may appear in more than one record."]
    for item in kpis:
        label = LABELS[item["column"]].lower()
        lines.append(
            f"The records list {item['value']:,.0f} {label} across "
            f"{item['count']:,} records with this figure supplied."
        )
    lines.append("These are totals from the supplied player records, not a count of unique players or a team's results.")
    return "\n".join(lines)


def clarify_football_display(display: dict[str, Any]) -> None:
    for item in display.get("columns", []):
        if item.get("name") in LABELS:
            item["label"] = LABELS[item["name"]]


def clarify_football_chart(chart: dict[str, Any]) -> None:
    measure, group = chart.get("xAxis"), chart.get("yAxis")
    if chart.get("type") != "bar" or measure not in {"gls", "ast"} or group not in {"comp", "pos"}:
        return
    chart["title"] = f"{LABELS[measure]} by {LABELS[group].lower()}"
    chart["description"] = (
        f"Recorded {LABELS[measure].lower()} across player records in each "
        f"{LABELS[group].lower()}. A player may appear in more than one record."
    )
    option = chart.get("echarts_option") or {}
    if isinstance(option.get("xAxis"), dict):
        option["xAxis"]["name"] = LABELS[measure]
    if isinstance(option.get("yAxis"), dict):
        option["yAxis"]["name"] = LABELS[group]
