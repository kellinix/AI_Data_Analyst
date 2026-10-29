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
    if {"appointmentdate", "clinic", "appointmentstatus", "waitminutes"}.issubset(fields):
        return {"kind": "clinic_appointment", "singular": "appointment record", "plural": "appointment records",
                "description": "Each row describes a scheduled clinic appointment, its recorded status and wait time where supplied. A cancelled appointment may have no wait time.",
                "label_columns": [fields[key]["name"] for key in ("appointmentdate", "clinic", "appointmentstatus")]}
    if {"batchdate", "productline", "unitsproduced"}.issubset(fields):
        return {"kind": "factory_batch", "singular": "production batch", "plural": "production batches",
                "description": "Each row lists one production batch with its date, product line and recorded output.",
                "label_columns": [fields[key]["name"] for key in ("batchdate", "productline", "shift") if key in fields]}
    if {"readingdate", "site", "kwhconsumed"}.issubset(fields):
        return {"kind": "energy_reading", "singular": "energy reading", "plural": "energy readings",
                "description": "Each row lists a dated site reading of electricity use in kilowatt-hours. Summed use describes the readings in this file.",
                "label_columns": [fields[key]["name"] for key in ("readingdate", "site")]}
    if {"applicationdate", "department", "hiringstage", "hired"}.issubset(fields):
        return {"kind": "hiring_application", "singular": "job application", "plural": "job applications",
                "description": "Each row lists one job application, its date, department and recorded hiring status. A recorded status does not explain why a decision was made.",
                "label_columns": [fields[key]["name"] for key in ("applicationdate", "department", "hiringstage")]}
    from app.analytics.football_context import is_football
    if is_football(schema):
        return {"kind": "football_player", "singular": "player record", "plural": "player records",
                "description": "Each row lists a football player, team, competition and recorded playing statistics. A player may appear in more than one row.",
                "label_columns": [fields[key]["name"] for key in ("player", "squad", "comp") if key in fields]}
    if {"shipmentid", "shipdate", "amount", "boxes"}.issubset(fields):
        return {"kind": "shipment", "singular": "shipment record", "plural": "shipment records",
                "description": "Each row lists a shipment, its date, recorded amount and boxes. The amount is not labelled as profit.",
                "label_columns": [fields[key]["name"] for key in ("shipmentid", "shipdate", "orderstatus") if key in fields]}
    if {"gmppidnumber", "projectname", "department"}.issubset(fields):
        return {"kind": "government_project", "singular": "project record", "plural": "project records",
                "description": "Each row describes a reported major government project, with its published dates, financial figures and delivery assessment where supplied.",
                "label_columns": [fields[key]["name"] for key in ("projectname", "department", "gmppidnumber") if key in fields]}
    if "route" in fields and ("sponsorname" in fields or "organisationname" in fields):
        name = "sponsorname" if "sponsorname" in fields else "organisationname"
        return {"kind": "sponsor_register", "singular": "sponsor register record", "plural": "sponsor register records",
                "description": "Each row lists a sponsor organisation and a recorded route or status. The register does not say how many people each sponsor employs or teaches.",
                "label_columns": [fields[key]["name"] for key in (name, "route", "status") if key in fields]}
    if {"organisationname", "totalcosused"}.issubset(fields):
        return {"kind": "sponsorship_use", "singular": "sponsorship-use record", "plural": "sponsorship-use records",
                "description": "Each row lists an organisation and its recorded certificate-of-sponsorship use. The same organisation may appear in more than one year.",
                "label_columns": [fields[key]["name"] for key in ("organisationname", "sheet") if key in fields]}
    required = {"weekstartdate", "region", "category", "channel", "revenue", "unitssold"}
    if required.issubset(fields) and fields["weekstartdate"].get("is_date") and all(
        fields[name].get("is_numeric") and fields[name].get("analysis_role") == "metric"
        for name in ("revenue", "unitssold")
    ):
        return {"kind": "weekly_sales", "singular": "weekly sales record", "plural": "weekly sales records",
                "description": "Weekly sales by region, product category and sales channel. Each record lists the week's revenue, units sold and other sales figures.",
                "label_columns": [fields[name]["name"] for name in ("weekstartdate", "region", "category", "channel")]}

    date_fields = [field for field in schema if field.get("is_date") and _key(field["name"]) in {"date", "datetime", "transactiondate", "saledate"}]
    amount_fields = [fields[key] for key in ("money", "amount", "total", "sales", "revenue")
                     if key in fields and fields[key].get("is_numeric") and fields[key].get("analysis_role") == "metric"]
    transaction_fields = ("invoiced", "invoiceid", "payment", "paymentmethod", "cashtype", "productline", "coffeename")
    if date_fields and amount_fields and any(key in fields for key in transaction_fields):
        labels = [date_fields[0]["name"]]
        labels.extend(fields[key]["name"] for key in transaction_fields if key in fields)
        return {"kind": "sales_transaction", "singular": "sales record", "plural": "sales records",
                "description": "Each row lists a dated sale with an amount and payment, product or invoice details. Repeated invoice IDs may refer to more than one row.",
                "label_columns": labels[:4]}
    return None


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
