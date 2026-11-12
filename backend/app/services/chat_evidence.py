"""Bound chat claims to saved measurements, with no model-authored factual prose."""

from __future__ import annotations

import re
from typing import Any

from app.analytics.labels import reader_label
from app.analytics.measure_grain import is_repeated_lookup
from app.analytics.measure_semantics import is_power_reading, is_rate_or_average
from app.analytics.percentage_scale import raw_percentage_label
from app.analytics.summary_evidence import _finite, _format, build_summary_facts
from app.services.summary_refresh import saved_measurements

UNAVAILABLE = (
    "I can't answer that from the information in this report. "
    "Try asking for a total, an average, or how many entries fall into a group."
)


def _label(column: Any) -> str:
    return reader_label(str(column))


def _fact_key(fact: dict[str, Any]) -> tuple[Any, ...]:
    values = fact.get("values") or {}
    if values.get("column") and values.get("operation"):
        return ("metric", values["column"], values["operation"], values.get("weighted_by"))
    if values.get("column") and "category" in values:
        return ("category", values["column"], str(values["category"]))
    return ("id", fact["id"])


def _unique_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for fact in facts:
        key = _fact_key(fact)
        # KPI facts preserve verified currency/rate units. Prefer them over
        # raw statistics when both describe the same field and operation.
        if key not in unique or str(fact["id"]).startswith("metric_"):
            unique[key] = fact
    return list(unique.values())


def _friendly_fact(fact: dict[str, Any]) -> str:
    values = fact.get("values") or {}
    column = _label(values.get("display_label") or values.get("column", ""))
    operation = values.get("operation")
    if column and operation and _finite(values.get("value")) is not None:
        display = values.get("display_value")
        if not display:
            # Earlier audited replies did not save display_value separately.
            # Recover only their server-rendered amount, retaining currency/%.
            match = re.search(r"(?:sums to|averages) (.+?) (?:across|when weighted by)", fact.get("text", ""))
            display = match[1] if match and str(fact["id"]).startswith("metric_") else _format(values["value"])
        phrases = {"total": "Total" if column.lower() == "total" else f"Total {column}", "mean": f"Average {column}",
                   "weighted_mean": f"Average {column}", "min": f"The lowest {column}",
                   "max": f"The highest {column}"}
        if operation == "total" and values.get("verified_binary_count"):
            return f"{display} entries have {column} set to 1."
        if operation in phrases:
            if values.get("column") == "hired" and values.get("is_percent"):
                return f"{display} of the job applications are marked as hired."
            text = f"{phrases[operation]} is {display}."
            if values.get("weighted_by"):
                weight_label = values.get("weight_display_label") or values["weighted_by"]
                text += f" Entries with higher {_label(weight_label)} count more toward this average."
            if values.get("display_warning"):
                text += " " + values["display_warning"]
            return text
    if column and "category" in values:
        count, total = int(values["count"]), int(values["denominator"])
        return (f"Of the {total:,} entries, {count:,} show '{values['category']}' "
                f"as the {column.lower()} ({count / total:.1%}).")
    if column and "distinct_values" in values:
        if column.endswith(" ID"):
            return (f"The file lists {int(values['distinct_values']):,} different {column}s. "
                    "An ID is a code used in your file. We have not checked who or what each code belongs to.")
        return (f"The file contains {int(values['distinct_values']):,} different values for {column}. "
                "The names or IDs have not been independently checked.")
    if fact["id"] == "records":
        if values.get("sampled"):
            return (f"This is based on the first {int(values['records']):,} entries imported from the file, "
                    "so it may not represent the whole file.")
        return f"Your file has {int(values['records']):,} entries."
    if fact["id"] == "cleaning":
        text = (f"These figures use the file after cleaning: {int(values['output_rows']):,} entries, "
                f"down from {int(values['input_rows']):,}.")
        if not values.get("reconciled"):
            text += " The cleaning report does not explain every removed entry."
        return text
    if fact["id"] == "imputation":
        return (f"{int(values['filled_cells']):,} missing cells were filled during cleaning. "
                "These added values were not in your original file.")
    if fact["id"] == "capping":
        return (f"Cleaning adjusted {int(values['capped_values']):,} unusually high or low values, "
                "so totals and averages may differ from your original file.")
    if fact["id"] == "missing":
        location = "original file" if "source_quality" in fact.get("source", "") else "file"
        if values.get("missing_kind") == "supplied_marker":
            return (f"{column[:1].upper() + column[1:]} contains {int(values['missing_values']):,} supplied missing-value markers "
                    f"in the {location}; these were not blank cells. Check the source definitions before comparing groups.")
        status = "is blank" if values.get("missing_kind") == "literal_blank" else "has missing information"
        return (f"{column[:1].upper() + column[1:]} {status} in {int(values['missing_values']):,} entries in the {location}. "
                "Check whether this information is needed before using it to make decisions.")
    if fact["id"] == "snapshot":
        return "This file does not have usable dates, so it cannot show how things changed over time."
    if str(fact["id"]).startswith("forecast_"):
        return (f"For {column}, next month's estimate ranges from {_format(float(values['lower']))} "
                f"to {_format(float(values['upper']))}. This includes the latest month's "
                f"{_format(float(values['latest']))}, so we cannot tell whether it will rise or fall.")
    return fact["text"]


def explain_fact(fact: dict[str, Any]) -> str:
    """Explain a saved calculation without asking a model to rewrite its facts."""
    values = fact.get("values") or {}
    column = _label(values.get("display_label") or values.get("column", "this field"))
    operation = values.get("operation")
    if operation == "total":
        if values.get("verified_binary_count"):
            return f"We counted entries where {column} is 1. Entries marked 0 or missing are not included."
        return f"We added the filled-in numbers for {column}."
    if operation == "mean":
        return (f"We added the filled-in numbers for {column}. "
                "Then we divided the total by how many numbers there were.")
    if operation == "weighted_mean":
        weight = _label(values.get("weighted_by") or "weight")
        return f"Numbers with a larger {weight} have more say in this average. Only weights above zero are used."
    if operation in {"min", "max"}:
        size = "smallest" if operation == "min" else "largest"
        return f"We found the {size} filled-in number for {column}."
    if "category" in values:
        return (f"We counted entries marked {values['category']!r} in {column}. "
                "The percentage shows how much of the whole group this is. Percent means out of 100.")
    if "distinct_values" in values:
        return f"We counted each different {column} once. We counted repeated values only once."
    if fact.get("id") == "records":
        return "We counted the rows used in this report. Each row is one entry in the file."
    if fact.get("id") == "cleaning":
        return "We compared the number of entries before and after cleaning."
    if fact.get("id") == "imputation":
        return "We counted empty cells that were filled during cleaning. These added numbers were missing from the original file."
    if fact.get("id") == "snapshot":
        return "We looked for dates that could show change over time. The file does not have usable dates for this."
    return "This statement uses the saved figures for this report. Check the source details before using it to make a decision."


def friendly_chat_content(facts: list[dict[str, Any]]) -> str:
    """Keep audit calculations internal; present one plain statement per claim."""
    selected = _unique_facts(facts)
    # A whole-file count is context, not another answer to every question.
    # Sampling remains visible because it changes how the answer can be used.
    if len(selected) > 1:
        selected = [fact for fact in selected
                    if fact["id"] != "records" or (fact.get("values") or {}).get("sampled")]
    return "\n\n".join(_friendly_fact(fact) for fact in selected)


def build_chat_facts(analysis: Any) -> list[dict[str, Any]]:
    try:
        stats, kpis = saved_measurements(analysis)
    except ValueError:
        return []
    metadata = analysis.metadata_ or {}
    facts = build_summary_facts(stats, kpis, stats["forecasts"], metadata.get("upload_context"))
    # Only measured summary facts survive; old summary/insight prose and user
    # upload instructions cannot become evidence for another answer.
    schema = {column["name"]: column for column in stats["schema"]}
    scope = facts[0]["scope"]

    def add(text: str, source: str, calculation: str, values: dict[str, Any]) -> None:
        facts.append({"id": f"saved_{len(facts)}", "text": text, "source": source,
                      "calculation": calculation, "values": values,
                      "scope": scope, "required": False})

    for column, values in list(stats["numeric_stats"].items())[:30]:
        field = schema.get(column, {})
        if field.get("analysis_role") not in {"metric", "flag"} or is_repeated_lookup(field):
            continue
        count = _finite(values.get("count"))
        if count is None or count <= 0:
            continue
        for operation, phrase in (("total", "sums to"), ("mean", "has an arithmetic average of"),
                                  ("min", "has a smallest supplied value of"),
                                  ("max", "has a largest supplied value of")):
            if operation == "total" and (is_power_reading(column, field) or is_rate_or_average(column, field)):
                continue
            value = _finite(values.get(operation))
            if value is None:
                continue
            add(f"'{column}' {phrase} {_format(value)} across {int(count):,} supplied values "
                f"in the {scope}, in the field's stored units.",
                f"numeric_stats.{column}.{operation}",
                f"{operation.upper()}({column}), excluding missing values",
                {"column": column, "operation": operation, "value": value, "count": int(count),
                 "display_label": raw_percentage_label(column) if field.get("percentage_scale") == "unconfirmed" else None,
                 "display_warning": field.get("display_warning")})
    rows = stats["row_count"] or 0
    for column, category in list(stats["categorical_stats"].items())[:30]:
        if schema.get(column, {}).get("analysis_role") not in {"dimension", "flag"} or rows <= 0:
            continue
        for item in category.get("top_values", [])[:10]:
            count = _finite(item.get("count"))
            if count is None or not 0 <= count <= rows:
                continue
            add(f"'{column}' has {int(count):,} records labelled '{item['value']}' "
                f"({count / rows:.1%} of all {rows:,} records in the {scope}).",
                f"categorical_stats.{column}.top_values", "Category count / all analysed records * 100",
                {"column": column, "category": item["value"], "count": int(count), "denominator": rows})
    for fact in facts:
        values = fact.get("values") or {}
        column = values.get("column")
        numeric = stats["numeric_stats"].get(column, {})
        low, high = _finite(numeric.get("min")), _finite(numeric.get("max"))
        # A flag-like name alone does not prove 0/1 coding. Both endpoints
        # and the exact distinct count must establish that no other codes exist.
        if (values.get("operation") == "total" and schema.get(column, {}).get("analysis_role") == "flag"
                and low in (0, 1) and high in (0, 1)
                and numeric.get("unique_count") == (1 if low == high else 2)
                and _finite(values.get("value")) == _finite(numeric.get("total"))):
            values["verified_binary_count"] = True
    return _unique_facts(facts)


def render_chat_answer(payload: Any, facts: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Reject malformed selections and unknown IDs rather than pass through prose."""
    base = {"method": "measured_chat_facts_v1", "free_form_used": False}
    if not isinstance(payload, dict) or payload.get("answer_kind") not in {"measured", "unavailable"}:
        return UNAVAILABLE, {**base, "status": "failed", "reason": "invalid_selection"}
    ids = payload.get("fact_ids")
    if not isinstance(ids, list) or len(ids) > 6 or any(not isinstance(id, str) for id in ids):
        return UNAVAILABLE, {**base, "status": "failed", "reason": "invalid_selection"}
    by_id = {fact["id"]: fact for fact in facts}
    if payload["answer_kind"] == "unavailable":
        return UNAVAILABLE, {**base, "status": "unsupported", "facts": []}
    if not ids or any(id not in by_id for id in ids):
        return UNAVAILABLE, {**base, "status": "failed", "reason": "unknown_fact"}
    chosen = list(dict.fromkeys(ids))
    # Counts/sampling, material source gaps, imputation and cleaning disclosures
    # cannot be dropped just because the model chose a headline measure.
    chosen.extend(fact["id"] for fact in facts if fact.get("required") and fact["id"] not in chosen)
    selected = [by_id[id] for id in chosen]
    content = friendly_chat_content(selected)
    return content, {**base, "status": "succeeded", "presentation": "plain_business_v1", "facts": selected}
