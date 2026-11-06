"""Truthful, repeatable coverage notes for both original and filtered charts."""

from typing import Any


def disclose_chart_coverage(chart: dict[str, Any]) -> None:
    option = chart.get("echarts_option") or {}
    description = str(chart.get("description") or "").strip()
    previous = option.pop("_coverage_note", "")
    if previous and description.endswith(previous):
        description = description[:-len(previous)].strip()
    notes = []
    coverage = option.get("_scatter_coverage")
    if coverage:
        if coverage["missing"]:
            count = coverage["missing"]
            notes.append(f"{count:,} {'entry' if count == 1 else 'entries'} with a missing coordinate {'is' if count == 1 else 'are'} excluded.")
        if coverage["eligible"] > coverage["sampled"]:
            notes.append(f"The plot uses the first {coverage['sampled']:,} complete entries out of {coverage['eligible']:,}; it is not the full dataset.")
    excluded = option.get("_excluded_points") or 0
    if excluded:
        notes.append(f"{excluded:,} {'entry' if excluded == 1 else 'entries'} with zero or negative values on a logarithmic axis {'is' if excluded == 1 else 'are'} excluded from the plot; these are not missing values.")
    if "_category_total" in option:
        notes.append(f"Shares use all {option['_category_total']:,} entries in this view.")
        missing = option.get("_missing_category_count", 0)
        if missing:
            notes.append(f"{missing:,} entries have no recorded category and are shown separately.")
    if notes:
        if description and description[-1] not in ".!?":
            description += "."
        note = " ".join(notes)
        chart["description"] = f"{description} {note}".strip()
        option["_coverage_note"] = note
    else:
        chart["description"] = description
