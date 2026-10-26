"""Owner-scoped entry investigation and allow-listed comparison calculations."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from app.analytics.category_values import category_expression, category_label
from app.analytics.live_filter import build_where_clause, validate_filters
from app.analytics.plain_language import plain_english
from app.analytics.record_context import identifying_columns, record_context, record_label
from app.analytics.sql_utils import quote_identifier as quote
from app.analytics.summary_evidence import _finite, _format
from app.services.file_processor import FileProcessor


class ComparisonFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    column: str
    op: Literal["in", "between", "date_between"]
    values: list[str | int | float | bool] = Field(min_length=1, max_length=50)


class ComparisonPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aggregation: Literal["sum", "average", "count", "distinct_count", "weighted_average"]
    column: str | None = None
    group_by: str | None = None
    weight_column: str | None = None
    date_bucket: Literal["day", "month", "year"] | None = None
    filters: list[ComparisonFilter] = Field(default_factory=list, max_length=8)
    order: Literal["desc", "asc"] = "desc"
    limit: int = Field(default=10, ge=1, le=50)


class EntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["quality", "insight", "comparison"]
    issue_index: int | None = Field(default=None, ge=0)
    insight_id: str | None = None
    comparison: ComparisonPlan | None = None
    group_value: str | None = None
    evidence_revision: str | None = None
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=25, ge=1, le=100)


def label(column: Any) -> str:
    text = str(column or "entries").replace("_", " ")
    return re.sub(r"\bpct\b", "percentage", re.sub(r"\bavg\b", "average", text, flags=re.I), flags=re.I)


def _schema(metadata: dict) -> dict[str, dict]:
    return {c["name"]: c for c in metadata.get("schema") or (metadata.get("data_profile") or {}).get("columns", [])}


def evidence_revision(analysis_id: Any, rows: int | None, metadata: dict) -> str:
    profile = metadata.get("data_profile") or {}
    checks = [{k: issue.get(k) for k in ("type", "column", "bounds", "affected_rows")}
              for issue in (metadata.get("data_quality") or {}).get("issues", [])]
    return hashlib.sha256(json.dumps([str(analysis_id), rows, profile.get("generated_at"),
        profile.get("dataset"), checks], sort_keys=True, default=str).encode()).hexdigest()


def validate_plan(plan: ComparisonPlan, metadata: dict) -> tuple[str, str | None, list[dict]]:
    schema = _schema(metadata)
    from app.analytics.survey_context import survey_fields
    survey = survey_fields(list(schema.values()))
    if survey and plan.column == survey["percentage"] and plan.aggregation in {"average", "weighted_average"}:
        if plan.group_by != survey["country"]:
            raise ValueError("Compare survey percentages by country. An overall percentage cannot be calculated without respondent counts or survey weights.")
        selected = {f.column: f for f in plan.filters}
        if any(survey[k] not in selected or selected[survey[k]].op != "in" or len(selected[survey[k]].values) != 1 for k in ("questioncode", "answer", "subset")):
            raise ValueError("Choose one survey question, one answer and one survey group before comparing percentages. Percentages from different questions cannot be averaged together.")
    measure = schema.get(plan.column or "")
    if plan.aggregation != "weighted_average" and plan.weight_column is not None:
        raise ValueError("Weights require a weighted average.")
    if plan.aggregation == "count":
        if plan.column is not None or plan.weight_column is not None:
            raise ValueError("Entry counts do not take a measure or weight.")
        expression = "COUNT(*)"
    else:
        if measure is None:
            raise ValueError("Choose a measure from this report.")
        if plan.aggregation == "distinct_count":
            column = quote(plan.column)
            expression = f"COUNT(DISTINCT CASE WHEN TRIM(CAST({column} AS VARCHAR)) <> '' AND LOWER(TRIM(CAST({column} AS VARCHAR))) <> 'unknown' THEN {column} END)"
        else:
            if not measure.get("is_numeric") or measure.get("analysis_role") != "metric":
                raise ValueError("Totals and averages need a measurable number, not an ID or label.")
            if plan.aggregation == "sum" and (measure.get("semantic_type") in {"percentage", "average_metric"}
                    or plan.column.lower() in {"cgpa", "gpa"}
                    or re.search(r"(?:^|_)(?:pct|percent|percentage|rate)(?:_|$)|%", plan.column, re.I)):
                raise ValueError("This measure is a rate or average. Compare its average per entry instead of adding it up.")
            if plan.aggregation == "weighted_average":
                weight = schema.get(plan.weight_column or "")
                if not weight or not weight.get("is_numeric") or weight.get("analysis_role") != "metric":
                    raise ValueError("Choose a numeric measure for the weights.")
                x, w = quote(plan.column), quote(plan.weight_column)
                expression = f"SUM(CASE WHEN {x} IS NOT NULL AND {w} > 0 THEN {x} * {w} END) / NULLIF(SUM(CASE WHEN {x} IS NOT NULL AND {w} > 0 THEN {w} END), 0)"
            else:
                if plan.weight_column is not None:
                    raise ValueError("Weights require a weighted average.")
                expression = f"{'SUM' if plan.aggregation == 'sum' else 'AVG'}({quote(plan.column)})"
    group = None
    if plan.group_by:
        field = schema.get(plan.group_by)
        if not field or field.get("analysis_role") not in {"dimension", "flag", "temporal_dimension"}:
            raise ValueError("Choose a grouping field, such as region or category.")
        if plan.date_bucket:
            if not field.get("is_date") or field.get("analysis_role") != "temporal_dimension":
                raise ValueError("Date grouping needs a recognised date field.")
            group = f"CAST(date_trunc('{plan.date_bucket}', {quote(plan.group_by)}) AS VARCHAR)"
        else:
            group = category_expression(plan.group_by)
    elif plan.date_bucket:
        raise ValueError("Choose a date field before grouping dates.")
    filters = validate_filters([f.model_dump() for f in plan.filters], list(schema.values()))
    return expression, group, filters


async def _load(analysis: Any) -> tuple[duckdb.DuckDBPyConnection, int, bool]:
    conn = duckdb.connect(":memory:")
    try:
        path = analysis.file.storage_path
        rows, truncated = await FileProcessor().read_to_duckdb_ex(conn, path, Path(path).suffix.lower())
        actual = {r[0] for r in conn.execute("DESCRIBE data").fetchall()}
        if not _schema(analysis.metadata_ or {}):
            raise ValueError("This older report has no saved field definitions. Analyse it again before reviewing entries.")
        if not set(_schema(analysis.metadata_ or {})).issubset(actual):
            raise ValueError("The saved file no longer matches this report. Analyse it again before comparing entries.")
        saved_sample = ((analysis.metadata_ or {}).get("data_profile") or {}).get("dataset") or {}
        expected_rows = saved_sample.get("row_count") if saved_sample.get("sample_truncated") else analysis.row_count
        if expected_rows is None:
            expected_rows = analysis.row_count
        if expected_rows is not None and rows != expected_rows:
            raise ValueError("The saved file's entry count has changed. Analyse it again before comparing entries.")
        return conn, rows, truncated or bool(saved_sample.get("sample_truncated"))
    except Exception:
        conn.close()
        raise


def _cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _cell(float(value))
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _scope(analysis: Any, rows: int, truncated: bool) -> str:
    text = (f"Based on the first {rows:,} imported entries, not the whole file."
            if truncated else f"Based on {rows:,} entries in this report.")
    cleaning = ((analysis.metadata_ or {}).get("upload_context") or {}).get("cleaning") or {}
    if cleaning.get("enabled"):
        text += " Uses the copy after cleaning; entry numbers refer to that copy."
    return text


async def compare(analysis: Any, plan: ComparisonPlan) -> dict[str, Any]:
    expression, group, filters = validate_plan(plan, analysis.metadata_ or {})
    from app.analytics.admission_context import is_admission
    from app.analytics.survey_context import survey_fields
    survey = survey_fields(list(_schema(analysis.metadata_ or {}).values()))
    percentage = plan.column == "chance_of_admit" and plan.aggregation in {"average", "weighted_average"} and is_admission(list(_schema(analysis.metadata_ or {}).values()))
    if percentage:
        expression = f"100.0 * ROUND(({expression}), 12)"
    where, params = build_where_clause(filters)
    if survey and plan.column == survey["percentage"]:
        exclude_average = f"LOWER(CAST({quote(survey['country'])} AS VARCHAR)) <> 'average'"
        where = f"({where}) AND {exclude_average}" if where else exclude_average
    clause = f" WHERE {where}" if where else ""
    conn, rows, truncated = await _load(analysis)
    try:
        matched = conn.execute("SELECT COUNT(*) FROM data" + clause, params).fetchone()[0]
        supplied = "COUNT(*)" if plan.column is None else f"COUNT({quote(plan.column)})"
        if plan.aggregation == "weighted_average":
            supplied = f"COUNT(CASE WHEN {quote(plan.column)} IS NOT NULL AND {quote(plan.weight_column)} > 0 THEN 1 END)"
        if group:
            sql = f"SELECT {group} AS group_name, {expression} AS result, COUNT(*) AS entries, {supplied} AS supplied FROM data{clause} GROUP BY 1"
            group_count = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
            result = conn.execute(f"SELECT *, COUNT(*) OVER (PARTITION BY result) AS tied FROM ({sql}) ranked"
                                  + f" ORDER BY result {plan.order.upper()} NULLS LAST, group_name NULLS LAST LIMIT ?",
                                  [*params, max(plan.limit, 2)]).fetchall()
        else:
            group_count = 1
            result = [(None, *conn.execute(f"SELECT {expression}, COUNT(*), {supplied} FROM data{clause}", params).fetchone())]
        if any(isinstance(row[1], float) and not math.isfinite(row[1]) for row in result):
            raise ValueError("Some values in this measure cannot be used as numbers. Check the file before comparing it.")
        groups = [{"group": category_label(plan.group_by, r[0]) if r[0] is not None and plan.group_by else None,
                   "group_value": str(r[0]) if r[0] is not None else None,
                   "value": _cell(r[1]), "entries": int(r[2]), "supplied_values": int(r[3])} for r in result[:plan.limit]]
        research_labels = {"0": "No research experience", "1": "Research experience recorded"} if percentage and plan.group_by == "research" else {}
        for row in groups:
            row["group"] = research_labels.get(row["group_value"], row["group"])
        operation = {"sum": "Total", "average": "Average", "count": "Entry count", "distinct_count": "Different values for", "weighted_average": "Average"}[plan.aggregation]
        measure_label = label(plan.column) if plan.column else ""
        if percentage:
            measure_label = "recorded admission chance (%)"
        title = f"{operation} {measure_label}".strip()
        lines = []
        for row in groups:
            prefix = f"{row['group'] if row['group'] is not None else 'Not provided'}: " if group else ""
            value = _finite(row["value"])
            lines.append(prefix + (f"{title} is {_format(value)}." if value is not None else f"No {measure_label or 'matching entries'} value is available."))
        if not matched:
            lines = ["No entries match this comparison."]
        note = _scope(analysis, rows, truncated)
        if survey and plan.column == survey["percentage"]:
            note += " Supplied Average rows are excluded; these are country percentages, not an overall population estimate."
        if filters:
            note += f" Selected filters match {matched:,} entries."
            note += " Filters: " + "; ".join(f"{label(f['column'])}: {', '.join(str(v) for v in f['values'])}" for f in filters) + "."
        if group_count > len(groups):
            note += f" Showing {len(groups)} of {group_count} groups, ordered by the result."
        if plan.aggregation == "weighted_average":
            note += f" Entries with higher {label(plan.weight_column)} count more toward this average; only positive weights are used."
        if plan.aggregation == "distinct_count":
            note += " Different recorded values are counted separately; identity is not independently checked."
        if plan.aggregation in {"sum", "average"}:
            note += " Blank values are left out of the calculation."
        answer = "\n\n".join(lines)
        if group:
            title += f" by {label(plan.group_by)}"
            answer = title + ":\n\n" + answer
        ranking = {"tied": int(result[0][4]),
                   "runner_up": {"group": category_label(plan.group_by, result[1][0]) if result[1][0] is not None else None,
                                 "value": _cell(result[1][1])} if len(result) > 1 else None} if group and result else None
        if ranking and ranking.get("runner_up"):
            runner = ranking["runner_up"]
            runner["group"] = research_labels.get(str(runner["group"]), runner["group"])
        response = {"title": title, "answer": answer, "scope": note, "groups": groups, "ranking": ranking,
                "evidence_revision": evidence_revision(analysis.id, analysis.row_count, analysis.metadata_ or {}),
                "matched_entries": matched, "group_count": group_count, "plan": plan.model_dump(),
                "calculation": expression, "source": "analysed_file", "sample_truncated": truncated, "value_unit": "%" if percentage else None}
        response["answer"] = comparison_answer(response)
        return response
    finally:
        conn.close()


def comparison_answer(result: dict) -> str:
    """Lead with the measured ranking, including ties beyond the displayed limit."""
    groups, plan = result.get("groups") or [], result.get("plan") or {}
    if not plan.get("group_by") or not groups or not result.get("matched_entries"):
        return result.get("answer", "")
    first = groups[0]
    value = _finite(first.get("value"))
    if value is None:
        return "There are no usable values for this comparison."
    ranking = result.get("ranking")
    # Older replies can be presented again only when the full ranking is saved.
    if ranking is None:
        if result.get("group_count") != len(groups):
            return result.get("answer", "")
        ranking = {"tied": sum(row.get("value") == first.get("value") for row in groups),
                   "runner_up": groups[1] if len(groups) > 1 else None}
    operation = plan.get("aggregation")
    measure = label(plan.get("column"))
    metric = {"sum": f"total {measure}", "average": f"average {measure} per entry",
              "weighted_average": f"{measure}, weighted by {label(plan.get('weight_column'))}",
              "count": "number of entries", "distinct_count": f"number of different {measure} values"}.get(operation)
    if metric is None:
        return result.get("answer", "")
    suffix = result.get("value_unit") or ""
    if suffix == "%":
        metric = "average recorded admission chance"
    rank = "lowest" if plan.get("order") == "asc" else "highest"
    def group_label(value: Any) -> str:
        if value is None:
            return f"Entries without {label(plan['group_by'])}"
        text = str(value)
        return f"{label(plan['group_by']).capitalize()} {text}" if re.fullmatch(r"-?\d+(?:\.\d+)?", text) else text

    subject = group_label(first.get("group"))
    tied = ranking.get("tied", 1)
    if tied > 1:
        lead = f"{tied:,} groups tie for the {rank} {metric} at {_format(value)}{suffix} each."
    elif result.get("group_count") == 1:
        lead = f"{subject} is the only group in this comparison, with {metric} of {_format(value)}{suffix}."
    else:
        lead = f"{subject} {'has' if first.get('group') is not None else 'have'} the {rank} {metric}, at {_format(value)}{suffix}."
        runner = ranking.get("runner_up") or {}
        runner_value = _finite(runner.get("value"))
        if runner_value is not None:
            other = group_label(runner.get("group"))
            difference = abs(value - runner_value)
            # Avoid a rounded zero gap between distinct measurements.
            if difference >= .005:
                lead += f" That is {_format(difference)}{' percentage points' if suffix == '%' else ''} {'less' if rank == 'lowest' else 'more'} than {other}."
    if len(groups) > 1:
        figures = "\n".join(f"{group_label(row.get('group'))}: {_format(row['value']) + suffix if _finite(row.get('value')) is not None else 'Not available'}"
                            for row in groups)
        lead += "\n\n" + figures
    return lead


def evidence_spec(metadata: dict, insight: dict | None = None, issue_index: int | None = None) -> dict | None:
    """Resolve links from saved evidence, never from client-supplied SQL or bounds."""
    if issue_index is not None:
        issues = (metadata.get("data_quality") or {}).get("issues") or []
        if issue_index >= len(issues):
            return None
        issue = issues[issue_index]
        if issue.get("type") in {"missing_values", "empty_field", "outliers", "wide_spread", "negative_financial_values", "duplicates"}:
            return {"kind": "quality", "issue": issue, "expected": issue.get("affected_rows")}
        return None
    if not insight:
        return None
    data = insight.get("data") or {}
    if insight.get("type") == "anomaly":
        return {"kind": "anomaly", "anomaly": (data.get("anomalies") or [data])[0]}
    if insight.get("type") == "recommendation":
        source = data.get("confidence_source")
        if source == "rule:anomaly" and metadata.get("anomalies"):
            return {"kind": "anomaly", "anomaly": metadata["anomalies"][0]}
        if source == "rule:data_quality" and data.get("column"):
            evidence = str(data.get("source_evidence") or data.get("evidence") or data.get("problem") or "")
            for index, issue in enumerate((metadata.get("data_quality") or {}).get("issues") or []):
                if (issue.get("column") == data["column"] and issue.get("description")
                        and plain_english(issue["description"]).lower() in plain_english(evidence).lower()):
                    return evidence_spec(metadata, issue_index=index)
            for entity in (metadata.get("analysis_evidence") or {}).get("entity_counts", []):
                if entity.get("column") == data["column"] and entity.get("repeated_records", 0) > 0 and "repeat" in evidence.lower():
                    return {"kind": "repeat_values", "column": data["column"], "expected": entity["repeated_records"]}
        if source == "rule:tracking":
            kpis = ((metadata.get("data_profile") or {}).get("metrics") or {}).get("kpis") or []
            if kpis and kpis[0].get("column") in _schema(metadata):
                return {"kind": "all", "column": kpis[0]["column"]}
    return None


def supporting_figures(metadata: dict, insight: dict) -> dict | None:
    data = insight.get("data") or {}
    source = data.get("confidence_source")
    spec = evidence_spec(metadata, insight)
    if spec and spec["kind"] == "anomaly":
        item = spec["anomaly"]
        return {"basis": "This is one entry, not the result for its whole group.",
                "figures": [{"label": label(item.get("column")), "value": item.get("value")}],
                "context": {label(k): str(v) for k, v in (item.get("context") or {}).items()}}
    if spec and spec["kind"] == "quality":
        issue = spec["issue"]
        return {"basis": f"Saved file check for {label(issue.get('column'))}.",
                "figures": [{"label": "Entries flagged", "value": issue.get("affected_rows")}], "context": {}}
    if spec and spec["kind"] == "repeat_values":
        entity = next(e for e in (metadata.get("analysis_evidence") or {}).get("entity_counts", []) if e["column"] == spec["column"])
        return {"basis": "Different recorded values are counted separately; identity is not independently checked.",
                "figures": [{"label": title, "value": entity.get(key)} for title, key in [
                    ("Entries with a value", "populated_records"), ("Different recorded values", "distinct_values"),
                    ("Entries repeating a value", "repeated_records")]], "context": {"Field": label(entity["column"])}}
    if source == "rule:tracking" and spec:
        kpi = metadata["data_profile"]["metrics"]["kpis"][0]
        return {"basis": "This is the saved figure used by the recommendation.",
                "figures": [{"label": label(kpi["column"]), "value": kpi.get("value")}], "context": {}}
    if source == "rule:data_quality" and not spec:
        evidence = str(data.get("source_evidence") or data.get("evidence") or "")
        field = label(evidence.partition(":")[0]).lower()
        for issue in ((metadata.get("data_quality") or {}).get("source_quality") or {}).get("issues", []):
            if field == label(issue.get("column")).lower() and _finite(issue.get("affected_rows")) is not None:
                return {"basis": "This describes blanks in the original file, before cleaning. Filled-in values cannot identify those original blank cells.",
                        "figures": [{"label": "Blank entries before cleaning", "value": issue["affected_rows"]}],
                        "context": {"Field": label(issue.get("column"))}}
    if source == "rule:forecast":
        def key(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", value.lower())
        for forecast in metadata.get("forecasts") or []:
            direction = "increase" if (forecast.get("change_percent_next_month") or 0) > 0 else "decline"
            if data.get("column") != forecast.get("metric") and key(str(insight.get("title"))) != key(f"Prepare for {label(forecast.get('metric'))} {direction}"):
                continue
            month = (forecast.get("predictions") or {}).get("next_month") or {}
            figures = [{"label": title, "value": value} for title, value in [
                ("Latest month", forecast.get("latest_value")), ("Next-month estimate", month.get("value")),
                ("Lower estimate", month.get("lower")), ("Upper estimate", month.get("upper"))] if _finite(value) is not None]
            return {"basis": f"Based on {forecast.get('observations', 'the saved')} months of data. Estimates are a planning guide, not a promise.",
                    "figures": figures, "context": {"Measure": label(forecast.get("metric"))}}
    return None


def _entry_predicate(spec: dict, schema: dict[str, dict], repeat_name: str) -> tuple[str, list[Any]]:
    if spec["kind"] == "all":
        return "", []
    if spec["kind"] == "repeat_values":
        if spec["column"] not in schema:
            raise ValueError("This identity field is no longer available.")
        column = quote(spec["column"])
        return f"{quote(repeat_name)} > 1 AND {column} IS NOT NULL AND TRIM(CAST({column} AS VARCHAR)) <> '' AND LOWER(TRIM(CAST({column} AS VARCHAR))) <> 'unknown'", []
    if spec["kind"] == "quality":
        issue = spec["issue"]
        column, kind = issue.get("column"), issue["type"]
        if kind == "duplicates":
            return f"{quote(repeat_name)} > 1", []
        if column not in schema:
            raise ValueError("The field for this check is no longer available.")
        q = quote(column)
        if kind in {"missing_values", "empty_field"}:
            return f"{q} IS NULL", []
        if not schema[column].get("is_numeric"):
            raise ValueError("This check does not identify a numeric measure.")
        if kind == "negative_financial_values":
            return f"{q} < 0", []
        bounds = issue.get("bounds") or {}
        low, high = _finite(bounds.get("lower")), _finite(bounds.get("upper"))
        if low is None or high is None or low >= high:
            raise ValueError("This older check did not save its comparison limits. Analyse the file again to identify the entries.")
        return f"({q} < ? OR {q} > ?)", [low, high]
    anomaly = spec["anomaly"]
    column = anomaly.get("column")
    if column not in schema or _finite(anomaly.get("value")) is None:
        raise ValueError("The entry behind this finding was not saved.")
    clauses, params = [f"{quote(column)} = ?"], [anomaly["value"]]
    for key, value in (anomaly.get("context") or {}).items():
        if key not in schema:
            raise ValueError("The entry details no longer match the saved file.")
        clauses.append(f"CAST({quote(key)} AS VARCHAR) IS NOT DISTINCT FROM ?")
        params.append(str(value) if value is not None else None)
    return " AND ".join(clauses), params


async def entries(analysis: Any, request: EntryRequest) -> dict[str, Any]:
    metadata = analysis.metadata_ or {}
    if request.evidence_revision and request.evidence_revision != evidence_revision(analysis.id, analysis.row_count, metadata):
        raise ValueError("This report has changed since the finding was shown. Refresh it before opening the supporting entries.")
    schema = _schema(metadata)
    entry_name, repeat_name = "__zephyr_entry", "__zephyr_repeat"
    while entry_name in schema:
        entry_name += "_"
    while repeat_name in schema:
        repeat_name += "_"
    expected = None
    if request.kind == "comparison":
        if not request.comparison:
            raise ValueError("Choose a comparison first.")
        _expression, group, filters = validate_plan(request.comparison, metadata)
        predicate, params = build_where_clause(filters)
        if group and request.group_value is not None:
            predicate = (predicate + " AND " if predicate else "") + f"{group} = ?"
            params.append(request.group_value)
        elif group:
            predicate = (predicate + " AND " if predicate else "") + f"{group} IS NULL"
    else:
        insight = next((i for i in analysis.insights if str(i.id) == request.insight_id), None) if request.kind == "insight" else None
        spec = evidence_spec(metadata, {"type": insight.type, "data": insight.data} if insight else None,
                             request.issue_index if request.kind == "quality" else None)
        if spec is None:
            raise ValueError("This finding does not have a saved entry link.")
        predicate, params = _entry_predicate(spec, schema, repeat_name)
        expected = spec.get("expected")
    conn, rows, truncated = await _load(analysis)
    try:
        columns = list(schema)
        # Entry numbers describe positions in the analysed copy, never Excel
        # row numbers. Exact-repeat numbering excludes the first copy.
        partition = ", ".join(quote(c) for c in columns)
        if request.kind != "comparison" and spec["kind"] == "repeat_values":
            partition = quote(spec["column"])
        cte = f"WITH indexed AS (SELECT *, row_number() OVER () AS {quote(entry_name)} FROM data), numbered AS (SELECT *, row_number() OVER (PARTITION BY {partition} ORDER BY {quote(entry_name)}) AS {quote(repeat_name)} FROM indexed) "
        where = f" WHERE {predicate}" if predicate else ""
        matched = conn.execute(cte + "SELECT COUNT(*) FROM numbered" + where, params).fetchone()[0]
        if expected is not None and matched != expected:
            raise ValueError("The file no longer matches this saved check. Analyse it again before reviewing these entries.")
        if request.kind == "insight" and not matched:
            raise ValueError("The entry behind this finding could not be found in the saved file.")
        priority = [c for role in ("identifier", "temporal_dimension", "dimension") for c in columns if schema[c].get("analysis_role") == role]
        measure = request.comparison.column if request.comparison else (spec.get("issue") or spec.get("anomaly") or spec).get("column")
        context = record_context(metadata)
        shown = list(dict.fromkeys([*([measure] if measure else []), *identifying_columns(schema, context), *priority, *columns]))[:20]
        selected = ", ".join(quote(c) for c in shown)
        found = conn.execute(cte + f"SELECT {quote(entry_name)}, {selected} FROM numbered{where} ORDER BY {quote(entry_name)} LIMIT ? OFFSET ?", [*params, request.limit, request.offset]).fetchall()
        records = []
        for row in found:
            values = {c: _cell(v) for c, v in zip(shown, row[1:], strict=True)}
            records.append({"entry_number": row[0], "record_label": record_label(values, schema, context, row[0]), "values": values})
        scope = _scope(analysis, rows, truncated)
        if context:
            scope = scope.replace("entry numbers", "record positions").replace("entries", context["plural"])
        return {"matched_entries": matched, "offset": request.offset, "limit": request.limit,
                "record_context": context,
                "columns": [{"name": c, "label": label(c), "is_date": bool(schema[c].get("is_date"))} for c in shown],
                "entries": records,
                "scope": scope + (f" Showing {len(shown)} of {len(columns)} fields, with identifying details first." if len(shown) < len(columns) else ""), "sample_truncated": truncated,
                "has_more": request.offset + len(found) < matched}
    finally:
        conn.close()
