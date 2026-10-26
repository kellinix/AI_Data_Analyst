"""Safe comparisons for published, question-level survey percentage tables."""
from __future__ import annotations

from typing import Any

from app.analytics.sql_utils import quote_identifier as quote


def survey_fields(schema: list[dict[str, Any]]) -> dict[str, str] | None:
    names = {c["name"].lower().replace("_", ""): c["name"] for c in schema}
    if not {"questioncode", "questionlabel", "answer", "percentage", "subset"}.issubset(names):
        return None
    country = next((names[n] for n in ("countrycode", "country", "countryname") if n in names), None)
    return {"country": country, **{n: names[n] for n in ("questioncode", "questionlabel", "answer", "percentage", "subset")}} if country else None


def clarify_survey(statistics: dict[str, Any]) -> None:
    fields = survey_fields(statistics.get("schema") or [])
    if not fields:
        return
    labels = {fields[k]: v for k, v in {"country": "Country", "questioncode": "Survey question", "questionlabel": "Question wording",
        "answer": "Answer", "percentage": "Published percentage", "subset": "Survey group"}.items()}
    for col in statistics["schema"]:
        col["display_label"] = labels.get(col["name"], col["name"].replace("_", " ").title())
        if col["name"] in {fields[k] for k in ("country", "subset", "answer")}:
            col["analysis_role"], col["semantic_type"] = "dimension", "categorical_dimension"
        if col["name"] == fields["questioncode"]:
            col["analysis_role"], col["semantic_type"] = "dimension", "categorical_code"
        if col["name"] in {fields["questionlabel"], "notes"}:
            col["analysis_role"], col["semantic_type"] = "text", "free_text"
        if col["name"] == fields["percentage"]:
            col["analysis_role"], col["semantic_type"] = "metric", "percentage"
    quality = statistics.get("data_quality") or {}
    numbers = (statistics.get("numeric_stats") or {}).get(fields["percentage"], {})
    lower, upper = numbers.get("min"), numbers.get("max")
    valid_range = lower is not None and upper is not None and 0 <= lower <= upper <= 100
    quality["issues"] = [i for i in quality.get("issues", []) if not (
        i.get("column") in {"notes", "note", "comments", "comment", "remarks"} or
        valid_range and i.get("column") == fields["percentage"] and i.get("type") in {"outliers", "wide_spread"})]
    for issue in quality["issues"]:
        issue["column_label"] = labels.get(issue.get("column"), issue.get("column"))
        if issue.get("column") == fields["percentage"] and issue.get("type") == "missing_values":
            issue["unpublished"] = True
    from app.analytics.data_quality import _quality_score
    if statistics.get("row_count"):
        quality["score"] = _quality_score(statistics["row_count"], quality["issues"])
    quality["issue_count"] = len(quality.get("issues", []))
    statistics["entity_counts"] = []
    statistics["record_context"] = {"kind": "survey_percentage", "singular": "survey result", "plural": "survey results",
        "description": "Published survey percentages by country, survey group, question and answer. Each record is a result for a group, not an individual respondent. Missing percentages remain unpublished; blank notes are optional.",
        "label_columns": [fields[k] for k in ("country", "subset", "questioncode", "answer")]}


def survey_catalog(statistics: dict[str, Any], conn: Any) -> None:
    fields = survey_fields(statistics.get("schema") or [])
    if not fields:
        return
    rows = conn.execute(f"SELECT {quote(fields['questioncode'])}, MIN({quote(fields['questionlabel'])}), COUNT(*) FROM data GROUP BY 1 ORDER BY 1 LIMIT 100").fetchall()
    count = conn.execute(f"SELECT COUNT(DISTINCT {quote(fields['questioncode'])}) FROM data").fetchone()[0]
    statistics["categorical_stats"][fields["questioncode"]] = {"unique_count": count,
        "top_values": [{"value": code, "label": f"{code}: {wording}", "count": count} for code, wording, count in rows]}
    rows = conn.execute(f"SELECT {quote(fields['answer'])}, COUNT(*) FROM data WHERE {quote(fields['answer'])} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 100").fetchall()
    count = conn.execute(f"SELECT COUNT(DISTINCT {quote(fields['answer'])}) FROM data").fetchone()[0]
    statistics["categorical_stats"][fields["answer"]] = {"unique_count": count,
        "top_values": [{"value": answer, "count": count} for answer, count in rows]}


def populate_survey(conn: Any, chart: dict[str, Any], filter_sql: str, params: list[Any]) -> bool:
    option = chart["echarts_option"]
    fields = option["_columns"]["survey_fields"]
    country, percent = quote(fields["country"]), quote(fields["percentage"])
    conditions = [filter_sql] if filter_sql else []
    values = list(params)
    defaults = option["_columns"].get("default_scope")
    if not defaults:
        supplied_scope = " AND ".join(f"{quote(fields[k])} IS NOT NULL" for k in ("questioncode", "answer", "subset"))
        first = conn.execute(f"SELECT {', '.join(quote(fields[k]) for k in ('questioncode', 'answer', 'subset'))} FROM data WHERE {percent} IS NOT NULL AND {supplied_scope} AND LOWER(CAST({country} AS VARCHAR)) <> 'average' LIMIT 1").fetchone()
        if not first:
            chart["title"] = "Published survey percentages by country"
            chart["description"] = "No published percentages with a complete question, answer and survey group are available for comparison."
            option["yAxis"]["data"], option["series"][0]["data"] = [], []
            return True
        defaults = dict(zip((fields[k] for k in ("questioncode", "answer", "subset")), first, strict=True))
        option["_columns"]["default_scope"] = defaults
    for column, value in defaults.items():
        if quote(column) not in filter_sql:
            conditions.append(f"{quote(column)} = ?")
            values.append(value)
    conditions += [f"{percent} IS NOT NULL", f"LOWER(CAST({country} AS VARCHAR)) <> 'average'"]
    where = " WHERE " + " AND ".join(f"({c})" for c in conditions)
    scope = conn.execute(f"SELECT {', '.join('COUNT(DISTINCT '+quote(fields[k])+')' for k in ('questioncode', 'answer', 'subset'))} FROM data{where}", values).fetchone()
    rows = []
    if scope == (1, 1, 1):
        rows = conn.execute(f"SELECT {country}, MIN({percent}), MAX({percent}) FROM data{where} GROUP BY 1 ORDER BY 2 DESC LIMIT 15", values).fetchall()
        if any(row[1] != row[2] for row in rows):
            rows = []
    option["yAxis"]["data"] = [str(row[0]) for row in rows][::-1]
    option["series"][0]["data"] = [float(row[1]) for row in rows][::-1]
    option["_percentageValues"] = True
    option["series"][0]["label"] = {"show": True, "position": "right", "formatter": "{c}%"}
    option.pop("_group_counts", None)
    if rows:
        detail = conn.execute(f"SELECT {', '.join(quote(fields[k]) for k in ('questionlabel', 'answer', 'subset'))} FROM data{where} LIMIT 1", values).fetchone()
        chart["title"] = "Published survey percentages by country"
        chart["description"] = f"Question: {detail[0]} Answer: {detail[1]}. Survey group: {detail[2]}. Shows up to 15 highest published country percentages. The supplied Average row is excluded; no overall average is calculated."
    else:
        chart["description"] = "Choose one question, one answer and one survey group to compare published country percentages. No result is shown when the selection is empty, mixes different results or contains conflicting values."
    return True
