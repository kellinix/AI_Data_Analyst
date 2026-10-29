"""Plain business wording for saved reports; measurements are never changed."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime
from typing import Any

from app.analytics.labels import derive_label, sentence_label
from app.analytics.plain_language import plain_english
from app.analytics.record_context import record_context
from app.analytics.summary_evidence import _finite, _format
from app.services.chat_evidence import _friendly_fact

VERSION = "plain_business_v5"


def business_text(text: Any) -> str:
    value = plain_english(str(text or ""))
    replacements = (
        (r"High percentage of missing values in", "Check the blanks in"),
        (r"Potential overstatement of entity coverage in", "Check repeated names or IDs in"),
        (r"Improved data reliability and decision-making\.", "Helps you decide which figures need checking before you use them."),
        (r"Avoids overstating entity coverage\.", "Helps avoid counting the same name or ID more than once."),
        (r"Counts describe entries unless a distinct-value measure is explicitly stated\.", "Counts refer to entries, which may include the same name or ID more than once."),
        (r"No usable date series was detected; this file alone cannot establish growth or change over time\.", "Without usable dates, this file cannot show how things changed over time."),
        (r"Category frequencies describe the composition of this file, not demand, performance or outcomes\.", "Group sizes show what is listed in this file. They do not show demand or performance."),
        (r"Geographic groups combine case, spacing and hyphen variants; source values are preserved and names are not verified against an external geographic reference\.", "Place names that differ only in capital letters, spaces or hyphens were grouped together. Names have not been checked against an official list."),
        (r"\bdistinct recorded values\b|\bdistinct values\b", "different values"),
        (r"\breal-world identity is not verified\b", "the names or IDs have not been independently checked"),
        (r"\breal-world accuracy is not verified\b", "these checks cannot confirm every entry is correct"),
        (r"\bentity coverage\b", "how many different names or IDs are listed"),
        (r"\bsource completeness\b", "information missing from the original file"),
        (r"\bsource coverage\b", "missing information"),
        (r"\bpopulated\b", "filled-in"),
        (r"\bimputed values\b", "values added during cleaning"),
        (r"\bAvg\b", "Average"),
        (r"\bKPIs\b", "key figures"),
        (r"\bmedian\b", "middle value"),
        (r"\bKwh Consumed\b", "electricity used (kWh)"),
        (r"\bExact duplicates removed after normalization\b", "Repeated entries removed after tidying names and formats"),
        (r"\bSimilar entries removed by fuzzy matching\b", "Similar entries removed during cleaning"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.I)
    value = re.sub(
        r"\b\d{4}-\d{2}-\d{2}T00:00:00\b",
        lambda match: datetime.fromisoformat(match.group(0)).strftime("%d %b %Y").lstrip("0"),
        value,
    )
    return value


def _label(column: Any) -> str:
    return sentence_label(business_text(str(column or "figure").replace("_", " ")))


def _field_label(column: Any, metadata: dict[str, Any]) -> str:
    """Resolve a quality issue's original header to its short saved label."""
    name = str(column or "")
    report = (((metadata.get("upload_context") or {}).get("cleaning") or {}).get("report") or {})
    normalized = (report.get("renamed_columns") or {}).get(name, name)
    if str(normalized).lower() == "sot":
        return "shots on target"
    if (record_context(metadata) or {}).get("kind") == "football_player":
        from app.analytics.football_context import LABELS
        if str(normalized).lower() in LABELS:
            return sentence_label(LABELS[str(normalized).lower()])
    for field in metadata.get("schema") or []:
        if field.get("name") == normalized:
            return sentence_label(business_text(str(field.get("display_label") or derive_label(normalized))))
    return sentence_label(business_text(derive_label(normalized)))


def chart_description(text: str | None) -> str | None:
    """Clarify legacy count captions without changing chart values or scope."""
    if text is None:
        return None
    return re.sub(r"^How many (?:fall|falls) into each\b", "Number of entries in each", text, flags=re.I)


def _name_records(text: str, context: dict[str, Any] | None) -> str:
    if not context:
        return text
    singular, plural = context.get("singular", "record"), context.get("plural", "records")
    # Undo plain_english's generic record -> entry conversion without
    # creating phrases such as "player player records".
    as_entries = re.sub(r"\brecords\b", "entries", plural, flags=re.I)
    as_entry = re.sub(r"\brecord\b", "entry", singular, flags=re.I)
    def substitute(pattern: str, replacement: str, value: str) -> str:
        return re.sub(pattern, lambda match: replacement.capitalize()
                      if match.group(0)[0].isupper() else replacement, value, flags=re.I)
    text = substitute(rf"\b{re.escape(as_entries)}\b", plural, text)
    text = substitute(rf"\b{re.escape(as_entry)}\b", singular, text)
    text = substitute(r"\bentries\b", plural, text)
    return substitute(r"\bentry\b", singular, text)


def forecast_wording(data: dict[str, Any]) -> tuple[str, str] | None:
    interval = (data.get("predictions") or {}).get("next_month") or {}
    value = _finite(interval.get("value"))
    if not data.get("metric") or value is None:
        return None
    label = _label(data["metric"])
    lower, upper = _finite(interval.get("lower")), _finite(interval.get("upper"))
    latest = _finite(data.get("latest_value"))
    def estimate(number: float) -> str:
        # Estimates are approximate; extra decimal places suggest precision
        # the model does not have. Retain small values rather than round to 0.
        return f"{number:,.0f}" if abs(number) >= 100 else _format(number)
    months = _finite(data.get("observations"))
    if months is not None and 0 < months < 6:
        return (
            f"Too little history to forecast {label}",
            f"There are only {int(months)} months of figures for {label}. "
            "That is too little to make a dependable estimate for next month. "
            "Review the trend again when more months of figures are available.",
        )
    if (lower is not None and upper is not None and lower <= value <= upper
            and estimate(lower) == estimate(upper)):
        return (
            f"No dependable forecast range for {label}",
            f"The available figures do not show how much next month's {label} could vary. "
            "Wait for more varied monthly results before using a forecast to make plans.",
        )
    monthly_total = data.get("method") == "linear_regression_monthly"
    text = (f"For {label}, next month's total is estimated at about {estimate(value)}."
            if monthly_total else f"For {label}, next month's estimate is about {estimate(value)}.")
    if latest is not None:
        text += f" The latest month's {'total' if monthly_total else 'figure'} was {estimate(latest)}."
    valid_range = lower is not None and upper is not None and lower <= value <= upper
    if valid_range:
        text += f" It could be roughly {estimate(lower)} to {estimate(upper)}."
        if data.get("change_direction_supported") is False or latest is not None and lower <= latest <= upper:
            text += " It is too early to say whether it will rise or fall."
        elif latest is not None:
            text += f" The range points to a possible {'rise' if lower > latest else 'fall'}, though the result may differ."
        if upper - lower >= max(abs(value), 1):
            text += " The range is wide, so avoid relying on the estimate alone."
        text += " Check whether your plans still work at both ends of this range."
    else:
        text += " No usable range is available to show how far the estimate could vary. Avoid making a firm commitment from this estimate alone."
    if monthly_total:
        text += " These are totals across the entries dated in each month."
    text += " Use this as a planning guide, not a promise. Review it when the next month's figures arrive."
    return f"What may happen next for {label}", text


def anomaly_wording(data: dict[str, Any]) -> tuple[str, str] | None:
    items = data.get("anomalies") or [data]
    first = items[0] if items else {}
    value = _finite(first.get("value"))
    column = first.get("column") or first.get("metric")
    if not column or value is None:
        return None
    text = f"One entry lists {_label(column)} as {_format(value)}, which stands out from the other entries."
    context = first.get("context") or {}
    if context:
        details = []
        for key, value in context.items():
            label = "week beginning" if key == "week_start_date" else _label(key)
            if "date" in str(key).lower() and isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value).strftime("%d %b %Y")
                except ValueError:
                    pass
            details.append(f"{label}: {value}")
        text += " Entry details: " + "; ".join(details) + "."
    if len(items) > 1:
        others = list(dict.fromkeys(_label(item.get("column") or item.get("metric")) for item in items[1:]))
        text += " Other figures worth a look: " + ", ".join(others) + "."
    text += " Check these entries against similar ones; a large difference does not automatically mean a mistake."
    return "Entries worth a closer look", text


def present_insight(insight: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    result = deepcopy(insight)
    data = result.get("data") or {}
    if data.get("presentation_version") == VERSION and metadata is None:
        return result
    kind = result.get("type")
    wording = forecast_wording(data) if kind == "forecast" else anomaly_wording(data) if kind == "anomaly" else None
    if wording:
        result["title"], result["description"] = wording
    else:
        result["title"] = business_text(result.get("title"))
        result["description"] = business_text(result.get("description"))
    if kind == "summary" and data.get("column"):
        result["title"] = re.sub(r"^Average\s+Average\b", "Average", result["title"], flags=re.I)
        if data.get("weighted_by"):
            result["description"] = f"Entries with higher {_label(data['weighted_by'])} count more toward this average."
        elif data.get("column") == "chance_of_admit":
            result["description"] = "Average recorded admission chance, not the percentage actually admitted."
        elif data.get("is_percent"):
            result["description"] = "The share of entries where this field is marked 1."
        else:
            result["description"] = "Total across the entries in this file." if data.get("is_total", True) else "Average across the entries in this file."
    if kind == "recommendation":
        source = data.get("confidence_source")
        if str(source or "").startswith("rule:"):
            data.pop("owner", None)
            data.pop("estimated_completion", None)
        title = str(result.get("title") or "").lower()
        if source == "rule:anomaly":
            result["title"] = "Check the entry that stands out"
            result["description"] = "Find the entry described below and compare it with similar entries. Confirm whether the difference is expected or needs correcting."
            data["expected_impact"] = "Helps you decide whether to correct the entry or look into what happened."
        elif source == "rule:data_quality" and ("different" in title or "entity" in title):
            result["title"] = "Check how many different names or IDs are listed"
            result["description"] = "The same name or ID can appear more than once. Compare the number of entries with the number of different values before comparing groups. Check whether different values really refer to different people, places or organisations."
            data["expected_impact"] = "Helps avoid counting the same name or ID more than once."
        elif source == "rule:data_quality":
            result["title"] = "Check the information behind these figures"
            result["description"] = "Review the items below with the person who maintains this file. Decide which missing details are needed and which differences are expected before using the figures to make decisions."
            data["expected_impact"] = "Helps you decide which figures you can use and what needs checking first."
        elif source == "rule:tracking":
            result["title"] = re.sub(r"^Track (.+) regularly$", r"Keep an eye on \1", result["title"], flags=re.I)
            result["description"] = "Compare this figure with the next report before deciding whether anything has changed."
            data["expected_impact"] = "Helps you spot a change that may need attention."
        elif source == "rule:forecast":
            result["description"] = "Use the estimate below to consider whether plans need adjusting. Review it again when the next month's figures arrive."
            data["expected_impact"] = "Helps you prepare while allowing for the estimate to change."
        for key in ("evidence", "problem", "expected_impact"):
            if isinstance(data.get(key), str):
                data[key] = business_text(data[key])
        if metadata is not None:
            _contextual_action(result, data, metadata)
            record_kind = (record_context(metadata) or {}).get("kind")
            if record_kind == "shipment" and source == "rule:forecast" and data.get("column") == "amount":
                result["title"] = re.sub(r"\bAmount\b", "shipment amount", str(result.get("title") or ""), flags=re.I)
            if record_kind == "sales_transaction":
                result["title"] = re.sub(r"\bMoney\b", "sales amount", str(result.get("title") or ""), flags=re.I)
                if isinstance(data.get("evidence"), str):
                    data["evidence"] = re.sub(r"\bMoney\b", "sales amount", data["evidence"], flags=re.I)
    if metadata is not None:
        context = record_context(metadata)
        for key in ("title", "description"):
            if isinstance(result.get(key), str):
                result[key] = _name_records(result[key], context)
                if (context or {}).get("kind") == "football_player":
                    result[key] = re.sub(r"\bsot\b", "shots on target", result[key], flags=re.I)
        for key in ("evidence", "problem", "expected_impact"):
            if isinstance(data.get(key), str):
                data[key] = _name_records(data[key], context)
                if (context or {}).get("kind") == "football_player":
                    data[key] = re.sub(r"\bsot\b", "shots on target", data[key], flags=re.I)
    data["presentation_version"] = VERSION
    result["data"] = data
    return result


def _contextual_action(result: dict, data: dict, metadata: dict) -> None:
    """Make actions specific only when saved measurements establish their meaning."""
    from app.services.investigation import evidence_spec, supporting_figures

    if "source_evidence" not in data:
        data["source_evidence"] = data.get("evidence")
    spec = evidence_spec(metadata, result)
    figures = supporting_figures(metadata, result)
    if figures:
        data["supporting_figures"] = figures
    source = data.get("confidence_source")
    if spec and spec["kind"] == "anomaly":
        item = spec["anomaly"]
        measure, value = _field_label(item.get("column"), metadata), _finite(item.get("value"))
        if value is not None:
            result["title"] = f"Review the {measure} entry of {_format(value)}"
            result["description"] = (f"Open the supporting entry and check {measure} against the original file. "
                                     "Compare it with entries for similar dates or groups. If the difference is expected, keep it; correct it only if the source confirms a mistake.")
            data["evidence"] = anomaly_wording(item)[1]
    elif spec and spec["kind"] == "repeat_values":
        measure = _field_label(spec["column"], metadata)
        result["title"] = f"Check repeated {measure} values before counting"
        result["description"] = (f"Open the repeated {measure} entries. Decide whether you want to count entries or different names or IDs, "
                                 "then use the same method for every group. A repeated value may represent separate activity.")
        data["expected_impact"] = "Helps you avoid treating several entries for the same name or ID as several different people, places or organisations."
    elif source == "rule:data_quality":
        issue = spec["issue"] if spec and spec["kind"] == "quality" else None
        if issue is None and figures and (figures.get("context") or {}).get("Field"):
            field = figures["context"]["Field"]
            issue = next((item for item in ((metadata.get("data_quality") or {}).get("source_quality") or {}).get("issues", [])
                          if _label(item.get("column")) == _label(field)), None)
        if issue:
            measure, kind = _field_label(issue.get("column"), metadata), issue.get("type")
            data["evidence"] = _quality_issue(issue)["description"]
            if kind in {"missing_values", "empty_field"}:
                result["title"] = f"Decide whether the blank {measure} details are needed"
                result["description"] = (f"Ask the person who maintains the file whether {measure} is required for this decision. "
                                         "If it is, recover the missing details from the original source before comparing groups. If it is optional, leave it blank rather than guessing.")
                if not spec:
                    data["evidence"] += " These blanks were in the original file, before cleaning."
            elif kind == "duplicates":
                result["title"] = "Check repeated entries before including them in totals"
                result["description"] = "Open the repeated entries and check whether they record separate activity or the same activity twice. Remove a copy only after confirming it is an accidental repeat."
            else:
                result["title"] = f"Review the flagged {measure} entries"
                result["description"] = f"Open the affected entries and check {measure} against the original source. Keep valid differences; correct only confirmed mistakes before using the figures."
    elif source == "rule:tracking" and spec and figures:
        measure = _label(spec["column"])
        result["title"] = f"Use {measure} as a starting point for the next review"
        result["description"] = (f"Keep this report's {measure} figure and compare it with the next report using the same time period, groups and calculation. "
                                 "A difference between unlike reports would not show a reliable change.")
    elif source == "rule:forecast" and figures:
        measure = (figures.get("context") or {}).get("Measure")
        forecast = next((item for item in metadata.get("forecasts") or [] if _label(item.get("metric")) == _label(measure)), None)
        wording = forecast_wording(forecast) if forecast else None
        if wording:
            data["column"] = forecast["metric"]
            if wording[0].startswith("What may happen next"):
                result["title"] = f"Check next month's plans for {_label(measure)}"
                result["description"] = wording[1]
                data["expected_impact"] = "Helps you see whether plans need room for a different result, without treating the estimate as certain."
            else:
                short_history = wording[0].startswith("Too little history")
                result["title"] = (
                    f"Wait for more history before forecasting {_label(measure)}"
                    if short_history else f"Wait for a usable range before forecasting {_label(measure)}"
                )
                result["description"] = wording[1]
                data["evidence"] = (
                    f"Only {forecast['observations']} months of figures are available for this forecast."
                    if short_history
                    else "The saved forecast range does not show meaningful variation."
                )
                data["source_evidence"] = data["evidence"]
                data["problem"] = "This file does not yet support a dependable forecast for this figure."
                data["supporting_figures"] = {
                    "basis": "The saved figures do not support a dependable prediction range.",
                    "figures": [{"label": "Months of figures", "value": forecast.get("observations")}],
                    "context": {"Measure": _label(measure)},
                }
                data["expected_impact"] = "Helps avoid making plans from an estimate the file cannot support."


def _quality_issue(issue: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(issue)
    count = issue.get("affected_rows")
    count_text = f"{int(count):,}" if _finite(count) is not None else "Some"
    kind = issue.get("type")
    if kind == "missing_values":
        text = f"{count_text} entries have this information left blank. Check whether it is needed for your decision."
        if issue.get("unpublished"):
            text = f"{count_text} survey results have no published percentage. These values were left empty and are excluded from the chart."
    elif kind == "empty_field":
        text = "This field is completely blank. Check whether you need it; it may not apply to this file."
    elif kind == "duplicates":
        text = f"{count_text} entries repeat another entry exactly. Check whether they are intended before counting them."
    elif kind in {"outliers", "wide_spread"}:
        measure = _label(issue.get("column_label") or issue.get("column"))
        bounds = issue.get("bounds") or {}
        lower, upper = _finite(bounds.get("lower")), _finite(bounds.get("upper"))
        below, above = _finite(issue.get("below_range_rows")), _finite(issue.get("above_range_rows"))
        def boundary(value: float) -> str:
            # The underlying check uses full precision. "About" makes clear
            # that these readable limits are rounded, not business targets.
            return f"about {_format(value * issue.get("display_multiplier", 1))}{issue.get("display_unit", "")}"
        if (lower is not None and upper is not None and below is not None and above is not None
                and below >= 0 and above >= 0 and count is not None and below + above == count):
            parts = []
            if below:
                parts.append(f"{int(below):,} {'entry has' if below == 1 else 'entries have'} {measure} below {boundary(lower)}")
            if above:
                parts.append(f"{int(above):,} {'entry has' if above == 1 else 'entries have'} {measure} above {boundary(upper)}")
            text = "; ".join(parts) + "."
            text = text[:1].upper() + text[1:]
        elif kind == "wide_spread" and upper is not None:
            text = f"{count_text} {'entry has' if count == 1 else 'entries have'} {measure} above {boundary(upper)}."
        elif lower is not None and upper is not None:
            text = (f"{count_text} {'entry has' if count == 1 else 'entries have'} {measure} "
                    f"below {boundary(lower)} or above {boundary(upper)}.")
        else:
            text = f"{count_text} entries were flagged for review of {measure}, but the comparison limits were not saved."
        text += " Check whether these differences are expected before correcting anything."
    elif kind == "negative_financial_values":
        text = f"{count_text} amounts are below zero. Check whether they are refunds, adjustments or mistakes."
    else:
        text = business_text(issue.get("description"))
    result["description"] = text
    return result


def present_metadata(metadata: dict[str, Any] | None, summary: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not metadata:
        return metadata, summary
    result = deepcopy(metadata)
    if result.get("presentation_version") == VERSION:
        context = record_context(result)
        if context and summary:
            summary = _name_records(summary, context)
        return result, summary
    checks = (result.get("analysis_evidence") or {}).get("summary_checks") or {}
    facts = checks.get("facts") or []
    if (checks.get("method") == "measured_facts_v1" and isinstance(facts, list) and facts
            and all(isinstance(f, dict) and isinstance(f.get("text"), str) for f in facts)
            and "\n".join(f["text"] for f in facts) == summary):
        try:
            visible_facts = [fact for fact in facts if not (
                str(fact.get("id", "")).startswith("identity_")
                and (fact.get("values") or {}).get("repeated_records") == 0
            )]
            sentences = [_friendly_fact(fact) for fact in visible_facts]
        except (KeyError, TypeError, ValueError):
            sentences = []
        if sentences:
            for fact, sentence in zip(visible_facts, sentences, strict=True):
                fact["text"] = sentence
            summary = "\n".join(sentences)
    evidence = result.get("analysis_evidence") or {}
    context = record_context(result)
    evidence["limitations"] = [_name_records(business_text(note), context)
                               for note in evidence.get("limitations", [])]
    for change in (evidence.get("cleaning") or {}).get("row_changes", []):
        change["reason"] = business_text(change.get("reason"))
    for item in evidence.get("entity_counts", []):
        item["count_basis"] = "Different names or IDs are counted separately; they have not been independently checked."
    quality = result.get("data_quality")
    if isinstance(quality, dict):
        from app.analytics.admission_context import FIELDS, is_admission
        if is_admission(result.get("schema") or []):
            for issue in quality.get("issues", []):
                if issue.get("column") in FIELDS:
                    issue["column_label"] = FIELDS[issue["column"]][0]
                    if issue["column"] == "chance_of_admit":
                        issue["display_multiplier"], issue["display_unit"] = 100, "%"
        quality["issues"] = [_quality_issue(issue) for issue in quality.get("issues", [])]
        issues = quality["issues"]
        quality["headline"] = "A few things are worth checking" if issues else "No problems found by these checks"
        quality["scope"] = "We checked for blanks, repeated entries and unusual numbers. Review limits come from patterns in this file, not business targets. These checks cannot confirm that every entry is correct."
        quality["score_explanation"] = "The score drops when checks find blanks or other items to review. A completely blank field may be optional, so it is listed separately."
        source = quality.get("source_quality")
        if isinstance(source, dict):
            source["issues"] = [_quality_issue(issue) for issue in source.get("issues", [])]
            source["scope"] = "This describes missing information in your original file, before cleaning. Blank fields may be optional."
    if context and summary:
        summary = _name_records(summary, context)
    result["presentation_version"] = VERSION
    return result, summary
