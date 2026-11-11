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
            notes.append(f"{count:,} {'entry is' if count == 1 else 'entries are'} missing one of the two figures and {'is' if count == 1 else 'are'} left out.")
        if coverage["eligible"] > coverage["sampled"]:
            notes.append(f"The chart shows the first {coverage['sampled']:,} of {coverage['eligible']:,} entries with both figures filled in.")
    excluded = option.get("_excluded_points") or 0
    if excluded:
        notes.append(f"The scale uses multiplying steps to fit very different sizes. {excluded:,} {'entry has' if excluded == 1 else 'entries have'} supplied values of zero or less and {'is' if excluded == 1 else 'are'} left out of this chart.")
    if "_category_total" in option:
        notes.append(f"Percentages use all {option['_category_total']:,} entries in this view.")
        missing = option.get("_missing_category_count", 0)
        if missing:
            notes.append(f"{missing:,} entries have no recorded category and are shown separately.")
    groups = option.get("_group_scope") or {}
    if groups.get("limit"):
        measure = {"sum": "totals", "average": "averages", "count": "entry counts", "percent_rate": "percentages"}.get(groups.get("order_by"), "figures")
        notes.append(f"This chart shows up to {groups['limit']} groups with the highest {measure}.")
    elif groups.get("category_limit"):
        notes.append(f"Up to {groups['category_limit']} main groups are chosen using their totals across all colour groups.")
        notes.append(f"We show up to {groups['series_limit']} named colour groups, sorted by their recorded names.")
        if groups.get("series_groups", 0) > groups["series_limit"]:
            notes.append("The bars use only the displayed colour groups.")
        if groups.get("unreported_series"):
            notes.append("The supplied 'Not reported' group is also shown.")
    if groups:
        notes.append("We use entries with both group labels and figures supplied." if groups.get("requires_value")
                     else "We count entries with a supplied group label.")
    if notes:
        if description and description[-1] not in ".!?":
            description += "."
        note = " ".join(notes)
        chart["description"] = f"{description} {note}".strip()
        option["_coverage_note"] = note
    else:
        chart["description"] = description
