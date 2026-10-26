"""Describe records from known fields without inventing people or company names."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def record_context(metadata: dict) -> dict | None:
    schema = metadata.get("schema") or (metadata.get("data_profile") or {}).get("columns") or []
    from app.analytics.survey_context import survey_fields
    survey = survey_fields(schema)
    if survey:
        return metadata.get("record_context") or {"kind": "survey_percentage", "singular": "survey result", "plural": "survey results", "description": "Published survey percentages by country, group, question and answer. Each record is a group result, not an individual respondent. Blank notes are optional.", "label_columns": [survey[k] for k in ("country", "subset", "questioncode", "answer")]}
    from app.analytics.admission_context import is_admission
    if is_admission(schema):
        return metadata.get("record_context") or {"kind": "admission", "singular": "applicant record", "plural": "applicant records", "description": "Applicant scores, grades, research experience and recorded admission chances. Actual admission decisions and dates are not included.", "label_columns": ["serial_no"] if any(c["name"] == "serial_no" for c in schema) else ["gre_score", "cgpa"]}
    fields = {_key(c["name"]): c for c in schema}
    required = {"weekstartdate", "region", "category", "channel", "revenue", "unitssold"}
    if not required.issubset(fields):
        return None
    if not fields["weekstartdate"].get("is_date") or any(
        not fields[name].get("is_numeric") or fields[name].get("analysis_role") != "metric"
        for name in ("revenue", "unitssold")
    ):
        return None
    return {"kind": "weekly_sales", "singular": "weekly sales record", "plural": "weekly sales records",
            "description": "Weekly sales by region, product category and sales channel. Each record lists the week's revenue, units sold and other sales figures.",
            "label_columns": [fields[name]["name"] for name in ("weekstartdate", "region", "category", "channel")]}


def identifying_columns(schema: dict[str, dict], context: dict | None) -> list[str]:
    if context:
        return context["label_columns"]
    names = [name for name in schema if _key(name) in {
        "name", "organisationname", "organizationname", "companyname", "customername", "sitename", "productname"}]
    return list(dict.fromkeys([*names, *[name for name, field in schema.items()
        if field.get("analysis_role") in {"identifier", "temporal_dimension", "dimension"}]]))[:4]


def record_label(values: dict[str, Any], schema: dict[str, dict], context: dict | None, position: int) -> str:
    if context and context.get("kind") == "admission" and values.get("serial_no") is not None:
        return f"Applicant record {values["serial_no"]}"
    parts = []
    for column in identifying_columns(schema, context):
        value = values.get(column)
        if value is None or str(value).strip().lower() in {"", "unknown", "not provided"}:
            continue
        if schema[column].get("is_date"):
            try:
                value = (value if isinstance(value, date) else datetime.fromisoformat(str(value))).strftime("%d %b %Y").lstrip("0")
            except ValueError:
                pass
        elif not context and schema[column].get("analysis_role") == "identifier" and not _key(column).endswith("name"):
            value = f"{column.replace('_', ' ')}: {value}"
        parts.append(str(value)[:120])
    return " · ".join(parts) if parts else f"Record {position:,}"
