"""Admission-score context, guarded by the complete known field combination."""
from __future__ import annotations

from typing import Any

FIELDS = {
    "gre_score": ("GRE score", 340), "toefl_score": ("TOEFL score", 120),
    "university_rating": ("University rating", 5),
    "sop": ("Statement of purpose rating", 5),
    "lor": ("Recommendation letter rating", 5),
    "cgpa": ("Undergraduate grade average", 10),
    "research": ("Research experience (0=no, 1=yes)", None),
    "chance_of_admit": ("Recorded admission chance", None),
}


def is_admission(schema: list[dict[str, Any]]) -> bool:
    fields = {c["name"]: c for c in schema}
    return set(FIELDS).issubset(fields) and all(fields[name].get("is_numeric") for name in FIELDS)


def clarify_statistics(statistics: dict[str, Any]) -> None:
    if not is_admission(statistics.get("schema") or []):
        return
    for field in statistics["schema"]:
        if field["name"] not in FIELDS:
            continue
        label, maximum = FIELDS[field["name"]]
        field["display_label"] = label
        field["display_description"] = f"Score out of {maximum}." if maximum else (
            "Recorded chance on a 0 to 1 scale, not an observed admission outcome."
            if field["name"] == "chance_of_admit" else "Research experience code: 0=no, 1=yes.")
        if field["name"] == "cgpa":
            field["semantic_type"] = "average_metric"
    for field in (statistics.get("data_profile") or {}).get("columns", []):
        if field.get("name") in FIELDS:
            field["display_label"] = FIELDS[field["name"]][0]
    for field in (statistics.get("semantic_display") or {}).get("columns", []):
        if field.get("name") in FIELDS:
            field["label"] = FIELDS[field["name"]][0]
    statistics["record_context"] = {"kind": "admission", "singular": "applicant record", "plural": "applicant records",
        "description": "Applicant test scores, academic grades, application ratings, research experience and recorded admission chance. The file does not contain actual admission decisions or dates.",
        "label_columns": ["serial_no"] if any(c["name"] == "serial_no" for c in statistics["schema"]) else ["gre_score", "cgpa"]}


def clarify_chart(chart: dict[str, Any]) -> None:
    option = chart.get("echarts_option") or {}
    columns = option.get("_columns") or {}
    if chart.get("type") == "bar":
        group = columns.get("x")
        title = FIELDS.get(group, (group, None))[0]
        chart["title"] = f"Average recorded admission chance by {title.lower()}"
        chart["description"] = "Average recorded chance for each group, not the share actually admitted. Labels show the number of applicants; small groups give less reliable comparisons."
        maximum = FIELDS.get(group, (None, None))[1]
        if maximum:
            chart["description"] += f" Ratings are out of {maximum}."
        option["_percentageValues"] = True
        option["xAxis"]["name"] = "Recorded admission chance (%)"
        option["yAxis"]["name"] = title
    elif chart.get("type") == "scatter":
        chart["title"] = "Academic grades and recorded admission chance"
        chart["description"] = "Higher undergraduate grades tend to accompany higher recorded admission chances in this file. This does not prove that changing grades causes admission or predict an individual decision."
        option["xAxis"].update({"name": "Undergraduate grade average (out of 10)", "scale": True})
        option["yAxis"].update({"name": "Recorded admission chance", "min": 0, "max": 1, "_percentage": True})


def admission_summary(statistics: dict[str, Any]) -> str:
    stats = statistics["numeric_stats"]
    rows = statistics.get("row_count") or stats["cgpa"]["count"]
    return (f"This file describes {rows:,} applicant records, including grades, test scores and recorded admission chances.\n"
        f"Average recorded admission chance is {round(stats['chance_of_admit']['mean'], 12) * 100:.2f}%. This is not an actual acceptance rate.\n"
        f"Average undergraduate grade is {stats['cgpa']['mean']:.2f} out of 10.\n"
        f"Average GRE score is {stats['gre_score']['mean']:.2f} out of 340; average TOEFL score is {stats['toefl_score']['mean']:.2f} out of 120.\n"
        "Compare recorded admission chances across application ratings and research experience. The file has no dates or actual admission decisions, so it cannot show trends or prove causes.")
