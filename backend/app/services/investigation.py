"""Owner-scoped entry investigation and allow-listed comparison calculations."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analytics.category_values import category_expression, category_filter_value, category_label
from app.analytics.data_dictionary import value_aliases, value_display_label
from app.analytics.labels import reader_label, source_column_label
from app.analytics.live_filter import build_where_clause, validate_filters
from app.analytics.measure_grain import (
    annotate_measure_grain,
    is_repeated_lookup,
    lookup_aggregation_message,
)
from app.analytics.measure_semantics import is_power_reading, is_rate_or_average
from app.analytics.percentage_scale import SCALE_WARNING, raw_percentage_label
from app.analytics.plain_language import plain_english
from app.analytics.record_context import identifying_columns, record_context, record_label
from app.analytics.sql_utils import quote_identifier as quote
from app.analytics.summary_evidence import _finite, _format
from app.services.file_processor import FileProcessor

# Unicode White_Space, matching the outer-whitespace rule used by file joins.
_IDENTIFIER_WHITESPACE = (
    " \t\n\r\v\f\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)
_NUMERIC_COMPARISONS = {
    "gt": (">", "greater than"),
    "gte": (">=", "at least"),
    "lt": ("<", "less than"),
    "lte": ("<=", "at most"),
}


class ComparisonFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    column: str
    op: Literal["in", "between", "date_between", "gt", "gte", "lt", "lte"]
    values: list[str | int | float | bool] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def numeric_bound(self) -> ComparisonFilter:
        if self.op in _NUMERIC_COMPARISONS:
            try:
                valid = (len(self.values) == 1 and not isinstance(self.values[0], bool)
                         and isinstance(self.values[0], int | float) and math.isfinite(self.values[0]))
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("A numeric comparison needs exactly one finite number.")
        return self


class ComparisonPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aggregation: Literal["sum", "average", "count", "distinct_count", "weighted_average", "retention"]
    column: str | None = None
    group_by: str | None = None
    weight_column: str | None = None
    date_bucket: Literal["day", "month", "year"] | None = None
    filters: list[ComparisonFilter] = Field(default_factory=list, max_length=8)
    cohort_filters: list[ComparisonFilter] = Field(default_factory=list, max_length=8)
    return_filters: list[ComparisonFilter] = Field(default_factory=list, max_length=8)
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
    return reader_label(str(column or "entries"))


def _field_label(column: str | None, schema: dict[str, dict]) -> str:
    field = schema.get(column or "")
    return reader_label(source_column_label(field), field) if field else label(column)


def _display_number(value: int | float, scale: str | None = None) -> str:
    return f"{value:,.6g}" if scale == "unconfirmed" else _format(value)


def _schema(metadata: dict) -> dict[str, dict]:
    fields = metadata.get("schema") or (metadata.get("data_profile") or {}).get("columns", [])
    return {c["name"]: c for c in annotate_measure_grain(fields, metadata.get("upload_context"), metadata.get("parser"))}


def evidence_revision(analysis_id: Any, rows: int | None, metadata: dict) -> str:
    profile = metadata.get("data_profile") or {}
    checks = [{k: issue.get(k) for k in ("type", "column", "bounds", "affected_rows")}
              for issue in (metadata.get("data_quality") or {}).get("issues", [])]
    return hashlib.sha256(json.dumps([str(analysis_id), rows, profile.get("generated_at"),
        profile.get("dataset"), checks], sort_keys=True, default=str).encode()).hexdigest()


def _verified_binary_flag(column: str, metadata: dict) -> bool:
    profile = metadata.get("data_profile") or {}
    saved = next((field for field in profile.get("columns", []) if field.get("name") == column), {})
    stats = ((metadata.get("numeric_stats") or {}).get(column) or saved.get("numeric_summary")
             or ((profile.get("metrics") or {}).get("numeric_statistics") or {}).get(column) or {})
    count, minimum, maximum = (_finite(stats.get(key)) for key in ("count", "min", "max"))
    if count is None or count <= 0 or minimum not in {0, 1} or maximum not in {0, 1}:
        return False
    if _finite(stats.get("integer_count")) == count or _finite(stats.get("unique_count")) == len({minimum, maximum}):
        return True
    categories = ((metadata.get("categorical_stats") or {}).get(column) or saved.get("categorical_summary")
                  or (profile.get("categories") or {}).get(column) or {})
    values = categories.get("top_values") or []
    try:
        return bool(values) and sum(item["count"] for item in values) == count and all(
            _numeric_filter_value(item["value"]) in {0, 1} for item in values)
    except (KeyError, TypeError, ValueError):
        return False


def _decimal_aggregate(values: list[str | None] | None, operation: str) -> float | None:
    if not values:
        return None
    # Cover the Float64 exponent range and the supported record count without
    # rounding intermediate sums. Convert to the API's float result once.
    with localcontext() as context:
        context.prec = 700
        total, count = Decimal(0), 0
        for value in values:
            if value is None:
                continue
            number = Decimal(value)
            if not number.is_finite():
                # DuckDB converts a Python NaN result to SQL NULL. Infinity
                # remains nonfinite so the comparison's validation rejects it.
                return float("inf")
            total += number
            count += 1
        if not count:
            return None
        return float(total / count if operation == "average" else total)


def _source_measure_basis(plan: ComparisonPlan, schema: dict[str, dict]) -> dict | None:
    """Resolve a repeated measure's recorded source identity without guessing."""
    measure = schema.get(plan.column or "") or {}
    if not is_repeated_lookup(measure):
        return None
    if plan.aggregation not in {"sum", "average"}:
        raise ComparisonUnavailable(lookup_aggregation_message(measure))
    origin = measure.get("measure_grain") or {}
    keys = origin.get("entity_key_columns")
    source = {name: origin.get(name) for name in ("source_table", "source_sheet", "source_role", "relationship_path")}
    valid = (origin.get("key_basis") == "parent_primary" and isinstance(source["source_table"], str) and source["source_table"].strip()
             and isinstance(origin.get("source_column"), str) and origin["source_column"].strip()
             and isinstance(keys, list) and keys and all(isinstance(key, str) and key for key in keys)
             and len(keys) == len(set(keys)))
    if valid:
        for key in keys:
            key_origin = (schema.get(key) or {}).get("measure_grain") or {}
            if (key not in schema or key_origin.get("key_basis") != "parent_primary"
                    or key_origin.get("entity_key_columns") != keys
                    or any(key_origin.get(name) != value for name, value in source.items())):
                valid = False
                break
    if not valid:
        raise ComparisonUnavailable(
            "This number is copied from another table. The saved report does not contain its complete source ID. "
            "Analyse the original related tables again so each source record can be counted once."
        )
    return {"kind": "source_entities", **source, "entity_key_columns": list(keys)}


def validate_plan(plan: ComparisonPlan, metadata: dict) -> tuple[str, str | None, list[dict]]:
    schema = _schema(metadata)
    if plan.aggregation == "retention":
        entity = schema.get(plan.column or "")
        if not entity or entity.get("analysis_role") not in {"identifier", "dimension"}:
            raise ValueError("Retention needs a recorded entity identifier, such as customer ID.")
        if plan.group_by or plan.weight_column or plan.date_bucket:
            raise ValueError("Retention compares distinct entities in two cohorts without grouping or weights.")
        if not plan.cohort_filters or not plan.return_filters:
            raise ValueError("Choose both the starting cohort and the return cohort for retention.")
        _comparison_filters([f.model_dump() for f in plan.return_filters], schema)
        filters = _comparison_filters([f.model_dump() for f in [*plan.filters, *plan.cohort_filters]], schema)
        entity_expression = _identifier_expression(plan.column)
        return entity_expression, None, filters
    if plan.cohort_filters or plan.return_filters:
        raise ValueError("Cohort filters require a retention calculation.")
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
            column = _identifier_expression(plan.column) if measure.get("analysis_role") == "identifier" else quote(plan.column)
            expression = f"COUNT(DISTINCT CASE WHEN TRIM(CAST({column} AS VARCHAR)) <> '' AND LOWER(TRIM(CAST({column} AS VARCHAR))) <> 'unknown' THEN {column} END)"
        else:
            _source_measure_basis(plan, schema)
            if plan.aggregation == "average" and measure.get("is_numeric") and measure.get("analysis_role") == "flag" and not _verified_binary_flag(plan.column, metadata):
                raise ComparisonUnavailable("An average requires saved measurements that verify every supplied flag is 0 or 1.")
            descriptive_average = plan.aggregation == "average" and measure.get("analysis_role") in {"flag", "attribute"}
            if not measure.get("is_numeric") or (measure.get("analysis_role") != "metric" and not descriptive_average):
                raise ValueError("Totals and averages need a measurable number, not an ID or label.")
            if plan.aggregation == "sum" and is_power_reading(plan.column, measure):
                raise ComparisonUnavailable(
                    "Choose average power for these readings. An energy total needs an energy field such as kWh or MWh, "
                    "or known time intervals for every power reading."
                )
            if plan.aggregation == "sum" and is_rate_or_average(plan.column, measure):
                raise ValueError("This measure is a rate or average. Compare its average per entry instead of adding it up.")
            if plan.aggregation == "weighted_average":
                weight = schema.get(plan.weight_column or "")
                if weight and is_repeated_lookup(weight):
                    raise ComparisonUnavailable(lookup_aggregation_message(weight))
                if not weight or not weight.get("is_numeric") or weight.get("analysis_role") != "metric":
                    raise ValueError("Choose a numeric measure for the weights.")
                x, w = quote(plan.column), quote(plan.weight_column)
                expression = f"SUM(CASE WHEN {x} IS NOT NULL AND {w} > 0 THEN {x} * {w} END) / NULLIF(SUM(CASE WHEN {x} IS NOT NULL AND {w} > 0 THEN {w} END), 0)"
            else:
                if plan.weight_column is not None:
                    raise ValueError("Weights require a weighted average.")
                floating = str(measure.get("dtype", "")).casefold() in {"double", "float", "real", "float32", "float64", "double precision"}
                if plan.aggregation == "sum" and not floating:
                    # Preserve native integer/decimal totals and legacy schema
                    # behavior instead of converting their sums to Float64.
                    expression = f"SUM({quote(plan.column)})"
                else:
                    values = f"LIST(CAST({quote(plan.column)} AS VARCHAR)) FILTER (WHERE {quote(plan.column)} IS NOT NULL)"
                    expression = f"vesquiri_decimal_aggregate({values}, '{plan.aggregation}')"
    group = None
    if plan.group_by:
        field = schema.get(plan.group_by)
        relative_day = (field and field.get("analysis_role") == "attribute" and field.get("semantic_type") == "relative_day"
                        and ((field.get("data_definition") or {}).get("time_basis") or {}).get("kind") == "relative_day")
        numeric_group = field and field.get("is_numeric") and (field.get("analysis_role") == "metric" or relative_day)
        if not field or (field.get("analysis_role") not in {"identifier", "dimension", "flag", "temporal_dimension"} and not numeric_group):
            raise ValueError("Choose a grouping field, such as region or category.")
        if plan.date_bucket:
            if not field.get("is_date") or field.get("analysis_role") != "temporal_dimension":
                raise ValueError("Date grouping needs a recognised date field.")
            group = f"CAST(date_trunc('{plan.date_bucket}', {quote(plan.group_by)}) AS VARCHAR)"
        else:
            coded = bool((field.get("data_definition") or {}).get("value_labels"))
            group = _identifier_expression(plan.group_by) if field.get("analysis_role") == "identifier" and not coded else category_expression(plan.group_by, field)
    elif plan.date_bucket:
        raise ValueError("Choose a date field before grouping dates.")
    filters = _comparison_filters([f.model_dump() for f in plan.filters], schema)
    return expression, group, filters


def _comparison_filters(filters: list[dict], schema: dict[str, dict]) -> list[dict]:
    # An owner-scoped question may name an ID, even though IDs are deliberately
    # excluded from general dashboard slicers. Numeric calendar labels such as
    # year also support explicit filters. Leave the saved roles untouched.
    fields = []
    for field in schema.values():
        numeric_calendar = field.get("analysis_role") == "temporal_dimension" and field.get("is_numeric")
        if field.get("analysis_role") == "identifier" or numeric_calendar:
            fields.append({**field, "analysis_role": "dimension"})
        else:
            fields.append(field)
    validated = []
    for selected in filters:
        probe = selected
        if selected["op"] in _NUMERIC_COMPARISONS:
            if len(selected["values"]) != 1:
                raise ValueError("A numeric comparison needs exactly one finite number.")
            # Reuse the dashboard's numeric-field/finite-bound rules without
            # expanding its public filter operations.
            probe = {**selected, "op": "between", "values": selected["values"] * 2}
        if not validate_filters([probe], fields):
            continue
        validated.append(selected)
        field = schema[selected["column"]]
        if _numeric_filter_field(field) and selected["op"] == "in":
            for value in selected["values"]:
                _numeric_filter_value(value, "ID" if field.get("analysis_role") == "identifier" else "calendar value")
    return validated


def _numeric_filter_field(field: dict) -> bool:
    return bool(field.get("is_numeric") and field.get("analysis_role") in {"identifier", "temporal_dimension"})


def _numeric_filter_value(value: Any, kind: str = "ID") -> Decimal:
    try:
        number = Decimal(str(value))
        if isinstance(value, bool) or not number.is_finite():
            raise InvalidOperation
        return number
    except InvalidOperation as exc:
        raise ValueError(f"Choose a finite numeric {kind} from this report.") from exc


def _comparison_where(filters: list[dict], schema: dict[str, dict]) -> tuple[str, list[Any]]:
    clauses, params = [], []
    for selected in filters:
        field = schema[selected["column"]]
        if selected["op"] in _NUMERIC_COMPARISONS:
            operator = _NUMERIC_COMPARISONS[selected["op"]][0]
            clauses.append(f"{quote(selected['column'])} {operator} ?")
            params.append(selected["values"][0])
        elif selected["op"] == "in" and not (field.get("data_definition") or {}).get("value_labels") and (field.get("analysis_role") == "identifier" or _numeric_filter_field(field)):
            placeholders = ", ".join("?" for _ in selected["values"])
            if _numeric_filter_field(field):
                clauses.append(f"{quote(selected['column'])} IN ({placeholders})")
                kind = "ID" if field.get("analysis_role") == "identifier" else "calendar value"
                params.extend(_numeric_filter_value(value, kind) for value in selected["values"])
            else:
                clauses.append(f"{_identifier_expression(selected['column'])} IN ({placeholders})")
                params.extend(str(value).strip(_IDENTIFIER_WHITESPACE) for value in selected["values"])
        else:
            clause, values = build_where_clause([selected], schema)
            clauses.append(clause)
            params.extend(values)
    return " AND ".join(clauses), params


def _identifier_expression(column: str) -> str:
    return f"NULLIF(TRIM(CAST({quote(column)} AS VARCHAR), '{_IDENTIFIER_WHITESPACE}'), '')"


def _identifier_note(plan: ComparisonPlan, schema: dict[str, dict]) -> str:
    fields = [plan.column, plan.group_by, *[f.column for f in [*plan.filters, *plan.cohort_filters, *plan.return_filters]]]
    if any(schema.get(name, {}).get("analysis_role") == "identifier" for name in fields):
        return " Spaces at the start or end of IDs are ignored. Letter case, spaces inside IDs and leading zeros are kept."
    return ""


def _display_group(column: str, value: Any, bucket: str | None = None, field: dict | None = None) -> str | None:
    if value is None:
        return None
    if bucket:
        try:
            moment = datetime.fromisoformat(str(value))
            return moment.strftime({"year": "%Y", "month": "%b %Y", "day": "%d %b %Y"}[bucket]).lstrip("0")
        except ValueError:
            pass
    return category_label(column, value, field)


async def _load(analysis: Any) -> tuple[duckdb.DuckDBPyConnection, int, bool]:
    conn = duckdb.connect(":memory:")
    try:
        conn.create_function("vesquiri_decimal_aggregate", _decimal_aggregate,
                             ["VARCHAR[]", "VARCHAR"], "DOUBLE", null_handling="special")
        path = analysis.file.storage_path
        metadata = analysis.metadata_ or {}
        profile = metadata.get("data_profile") or {}
        processor = FileProcessor(data_dictionary_context=metadata.get("upload_context"),
                                  source_name=getattr(analysis.file, "original_filename", None) or (profile.get("dataset") or {}).get("name"))
        rows, truncated = await processor.read_to_duckdb_ex(conn, path, Path(path).suffix.lower())
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
        source_sample = ((analysis.metadata_ or {}).get("upload_context") or {}).get("source_sample_truncated")
        return conn, rows, truncated or bool(saved_sample.get("sample_truncated")) or bool(source_sample)
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
    plural = (record_context(analysis.metadata_ or {}) or {}).get("plural", "entries")
    text = (f"Based on the first {rows:,} imported {plural}, not the whole file."
            if truncated else f"Based on {rows:,} {plural} in this report.")
    cleaning = ((analysis.metadata_ or {}).get("upload_context") or {}).get("cleaning") or {}
    if cleaning.get("enabled"):
        text += " Uses the copy after cleaning. Entry numbers refer to that copy."
    return text


def _filter_description(selected: dict, schema: dict[str, dict] | None = None) -> str:
    name, values = _field_label(selected["column"], schema or {}), selected["values"]
    if selected["op"] == "date_between":
        start, end = (date.fromisoformat(str(value)).strftime("%d %b %Y").lstrip("0") for value in values)
        return f"{name} was from {start} to {end}"
    if selected["op"] == "between":
        return f"{name} was between {values[0]} and {values[1]}"
    if selected["op"] in _NUMERIC_COMPARISONS:
        return f"{name} was {_NUMERIC_COMPARISONS[selected['op']][1]} {values[0]:,}"
    field = (schema or {}).get(selected["column"], {})
    return f"{name} was " + " or ".join(value_display_label(field, value) or str(value) for value in values)


def _numeric_definition_filters(plan: ComparisonPlan, schema: dict[str, dict]) -> ComparisonPlan:
    """Resolve supplied meanings that cannot be literal numeric/Boolean codes."""
    payload = plan.model_dump()
    for collection in ("filters", "cohort_filters", "return_filters"):
        for selected in payload[collection]:
            field = schema.get(selected["column"], {})
            typed_code = (field.get("is_numeric") or str(field.get("dtype") or "").upper() in {"BOOL", "BOOLEAN"})
            if selected["op"] != "in" or not typed_code:
                continue
            values = []
            for value in selected["values"]:
                try:
                    _comparison_filters([{**selected, "values": [value]}], schema)
                except ValueError:
                    aliases = value_aliases(field, value)
                    if len(aliases) == 1 and aliases[0] is not None:
                        _comparison_filters([{**selected, "values": aliases}], schema)
                        value = aliases[0]
                values.append(value)
            selected["values"] = values
    return ComparisonPlan.model_validate(payload)


def _source_aggregation_relation(
    conn: duckdb.DuckDBPyConnection, plan: ComparisonPlan, schema: dict[str, dict],
    basis: dict, group: str | None, where: str, params: list[Any],
) -> tuple[str, str | None, str]:
    """Return one value per source key and retain the number of supporting rows."""
    keys = [_identifier_expression(name) for name in basis["entity_key_columns"]]
    complete = " AND ".join(f"({key} IS NOT NULL AND LOWER({key}) <> 'unknown')" for key in keys)
    missing = f"{quote(plan.column)} IS NOT NULL AND NOT ({complete})"
    missing_where = f"({where}) AND ({missing})" if where else missing
    if conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {missing_where})", params).fetchone()[0]:
        raise ComparisonUnavailable("Some matching numbers have no complete source ID. Repair those IDs before adding or averaging them.")

    prefix = "__vesquiri_source"
    while any(name.casefold().startswith(prefix.casefold()) for name in schema):
        prefix += "_"
    aliases = [f"{prefix}_key_{index}" for index in range(len(keys))]
    selected_keys = ", ".join(f"{key} AS {quote(alias)}" for key, alias in zip(keys, aliases, strict=True))
    selected_where = f"({where}) AND ({complete})" if where else complete
    chosen = f"WITH chosen AS (SELECT DISTINCT {selected_keys} FROM data WHERE {selected_where}) "
    joining = " AND ".join(f"{key} = chosen.{quote(alias)}" for key, alias in zip(keys, aliases, strict=True))
    column = quote(plan.column)
    # Check all copies of each selected source record, including copies hidden
    # by a fact-row filter. A filter cannot conceal conflicting source values.
    different_values = f"COUNT(DISTINCT {column}) + CASE WHEN COUNT(*) FILTER (WHERE {column} IS NULL) > 0 THEN 1 ELSE 0 END"
    conflict = chosen + f"SELECT EXISTS(SELECT 1 FROM data JOIN chosen ON {joining} GROUP BY {', '.join(keys)} HAVING {different_values} > 1)"
    if conn.execute(conflict, params).fetchone()[0]:
        raise ComparisonUnavailable("Copies of the same source record have different numbers. Repair those source values before adding or averaging them.")
    if group:
        different_groups = f"COUNT(DISTINCT {group}) + CASE WHEN COUNT(*) FILTER (WHERE {group} IS NULL) > 0 THEN 1 ELSE 0 END"
        conflict = f"SELECT EXISTS(SELECT 1 FROM data WHERE {selected_where} GROUP BY {', '.join(keys)} HAVING {different_groups} > 1)"
        if conn.execute(conflict, params).fetchone()[0]:
            raise ComparisonUnavailable("The same source record belongs to several selected groups. Choose a source-level grouping so its whole value is counted once.")
    support = quote(f"{prefix}_entries")
    group_alias = quote(f"{prefix}_group")
    selected_group = f", FIRST({group}) AS {group_alias}" if group else ""
    relation = (f"(SELECT FIRST({column}) AS {column}{selected_group}, COUNT(*) AS {support} "
                f"FROM data WHERE {selected_where} GROUP BY {', '.join(keys)})")
    return relation, group_alias if group else None, support


async def compare(analysis: Any, plan: ComparisonPlan, *, resolve_categories: bool = False) -> dict[str, Any]:
    schema = _schema(analysis.metadata_ or {})
    plan = _numeric_definition_filters(plan, schema)
    expression, group, filters = validate_plan(plan, analysis.metadata_ or {})
    from app.analytics.admission_context import is_admission
    from app.analytics.survey_context import survey_fields
    survey = survey_fields(list(schema.values()))
    percentage = plan.column == "chance_of_admit" and plan.aggregation in {"average", "weighted_average"} and is_admission(list(schema.values()))
    if percentage:
        expression = f"100.0 * ROUND(({expression}), 12)"
    conn, rows, truncated = await _load(analysis)
    try:
        _check_relationship_fields(conn, analysis.metadata_ or {}, plan)
        selected_fields = [item.column for item in [*plan.filters, *plan.cohort_filters, *plan.return_filters]]
        if resolve_categories or any((schema.get(name, {}).get("data_definition") or {}).get("value_labels") for name in selected_fields):
            plan = _resolve_category_filters(conn, plan, schema, resolve_case=resolve_categories)
            _expression, _group, filters = validate_plan(plan, analysis.metadata_ or {})
        if plan.aggregation == "retention":
            return _retention_result(conn, analysis, plan, expression, filters, rows, truncated)
        where, params = _comparison_where(filters, schema)
        if survey and plan.column == survey["percentage"]:
            exclude_average = f"LOWER(CAST({quote(survey['country'])} AS VARCHAR)) <> 'average'"
            where = f"({where}) AND {exclude_average}" if where else exclude_average
        clause = f" WHERE {where}" if where else ""
        if plan.aggregation in {"sum", "average"}:
            column = quote(plan.column)
            numeric = f"TRY_CAST({column} AS DOUBLE)"
            invalid = f"{column} IS NOT NULL AND ({numeric} IS NULL OR NOT isfinite({numeric}))"
            invalid_where = f"({where}) AND ({invalid})" if where else invalid
            if conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {invalid_where})", params).fetchone()[0]:
                raise ValueError("Some values in this measure cannot be used as numbers. Check the file before comparing it.")
        matched = conn.execute("SELECT COUNT(*) FROM data" + clause, params).fetchone()[0]
        basis = _source_measure_basis(plan, schema) if plan.aggregation in {"sum", "average"} else None
        relation, query_group, support = "data" + clause, group, None
        if basis:
            relation, query_group, support = _source_aggregation_relation(
                conn, plan, schema, basis, group, where, params)
        entry_count = f"COALESCE(SUM({support}), 0)" if support else "COUNT(*)"
        supplied = "COUNT(*)" if plan.column is None else f"COUNT({quote(plan.column)})"
        if plan.aggregation == "weighted_average":
            supplied = f"COUNT(CASE WHEN {quote(plan.column)} IS NOT NULL AND {quote(plan.weight_column)} > 0 THEN 1 END)"
        if group:
            sql = f"SELECT {query_group} AS group_name, {expression} AS result, {entry_count} AS entries, {supplied} AS supplied, COUNT(*) AS entities FROM {relation} GROUP BY 1"
            group_count = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
            result = conn.execute(f"SELECT group_name, result, entries, supplied, COUNT(*) OVER (PARTITION BY result) AS tied, entities FROM ({sql}) ranked"
                                  + f" ORDER BY result {plan.order.upper()} NULLS LAST, group_name NULLS LAST LIMIT ?",
                                  [*params, max(plan.limit, 2)]).fetchall()
        else:
            group_count = 1
            result = [(None, *conn.execute(f"SELECT {expression}, {entry_count}, {supplied}, COUNT(*) FROM {relation}", params).fetchone())]
        if any(isinstance(row[1], float) and not math.isfinite(row[1]) for row in result):
            raise ValueError("Some values in this measure cannot be used as numbers. Check the file before comparing it.")
        groups = [{"group": _display_group(plan.group_by, r[0], plan.date_bucket, schema[plan.group_by]) if plan.group_by else None,
                   "group_value": str(r[0]) if r[0] is not None else None,
                   "value": _cell(r[1]), "entries": int(r[2]), "supplied_values": int(r[3])} for r in result[:plan.limit]]
        if basis:
            for row, raw in zip(groups, result, strict=False):
                row["aggregation_entities"] = int(raw[-1])
            entities, supplied_entities, supporting = conn.execute(
                f"SELECT COUNT(*), {supplied}, {entry_count} FROM {relation}", params).fetchone()
            basis = {**basis, "entities": entities, "supplied_entities": supplied_entities,
                     "supporting_entries": supporting, "entries_without_source_id": matched - supporting}
        if plan.group_by:
            for row in groups:
                display = value_display_label(schema[plan.group_by], row["group_value"])
                if display is not None:
                    row["display_label"] = display
        research_labels = {"0": "No research experience", "1": "Research experience recorded"} if percentage and plan.group_by == "research" else {}
        for row in groups:
            row["group"] = research_labels.get(row["group_value"], row["group"])
        operation = {"sum": "Total", "average": "Average", "count": "Entry count", "distinct_count": "Different values for", "weighted_average": "Average"}[plan.aggregation]
        measure_label = _field_label(plan.column, schema) if plan.column else ""
        scale = (schema.get(plan.column or "") or {}).get("percentage_scale")
        if scale == "unconfirmed":
            measure_label = raw_percentage_label(plan.column)
        if percentage:
            measure_label = "recorded admission chance (%)"
        title = f"{operation} {measure_label}".strip()
        lines = []
        for row in groups:
            prefix = f"{row['group'] if row['group'] is not None else 'Not provided'}: " if group else ""
            value = _finite(row["value"])
            lines.append(prefix + (f"{title} is {_display_number(value, scale)}." if value is not None else f"No {measure_label or 'matching entries'} value is available."))
        if not matched:
            lines = ["No entries match this comparison."]
        note = _scope(analysis, rows, truncated) + _identifier_note(plan, schema)
        if basis:
            note += (f" We used each matching record from {basis['source_table']} once. "
                     f"This calculation uses {basis['entities']:,} source records linked to {basis['supporting_entries']:,} report entries. "
                     "Records with the same number are still counted separately when their IDs differ.")
            if basis["entries_without_source_id"]:
                note += f" {basis['entries_without_source_id']:,} entries had no matching source record and were left out."
        if scale == "unconfirmed":
            note += " " + SCALE_WARNING
        if survey and plan.column == survey["percentage"]:
            note += " Supplied Average rows are excluded; these are country percentages, not an overall population estimate."
        if filters:
            note += f" Your choices selected {matched:,} entries."
            note += " We used entries where " + ", and ".join(_filter_description(f, schema) for f in filters) + "."
        if group_count > len(groups):
            note += f" Showing {len(groups)} of {group_count} groups, ordered by the result."
        if plan.aggregation == "weighted_average":
            note += f" Entries with a larger {_field_label(plan.weight_column, schema)} have more say in this average. Only weights above zero are used."
        if plan.aggregation == "distinct_count":
            note += " We counted each different value once. We have not checked who or what each value belongs to."
        if plan.aggregation == "sum":
            note += f" We added the filled-in numbers for {measure_label}. Blank values are left out of the calculation."
        if plan.aggregation == "average":
            note += f" We added the filled-in numbers for {measure_label}. Then we divided by how many numbers there were. Blank values are left out of the calculation."
        answer = "\n\n".join(lines)
        if group:
            title += f" by {_field_label(plan.group_by, schema)}"
            answer = title + ":\n\n" + answer
        ranking = {"tied": int(result[0][4]),
                   "runner_up": {"group": _display_group(plan.group_by, result[1][0], plan.date_bucket, schema[plan.group_by]),
                                 "value": _cell(result[1][1])} if len(result) > 1 else None} if group and result else None
        if ranking and ranking.get("runner_up"):
            runner = ranking["runner_up"]
            runner["group"] = research_labels.get(str(runner["group"]), runner["group"])
            display = value_display_label(schema[plan.group_by], result[1][0])
            if display is not None:
                runner["display_label"] = display
        response = {"title": title, "answer": answer, "scope": note, "groups": groups, "ranking": ranking,
                "evidence_revision": evidence_revision(analysis.id, analysis.row_count, analysis.metadata_ or {}),
                "matched_entries": matched, "group_count": group_count, "plan": plan.model_dump(),
                "record_context": record_context(analysis.metadata_ or {}),
                "measure_label": measure_label, "group_label": _field_label(plan.group_by, schema) if group else None,
                "group_codes_exact": bool((schema.get(plan.group_by or "", {}).get("data_definition") or {}).get("value_labels")),
                "weight_label": _field_label(plan.weight_column, schema) if plan.weight_column else None,
                "percentage_scale": scale,
                "calculation": expression, "source": "analysed_file", "sample_truncated": truncated, "value_unit": "%" if percentage else None}
        if basis:
            response["aggregation_basis"] = basis
        response["answer"] = comparison_answer(response)
        return response
    finally:
        conn.close()


class ComparisonUnavailable(ValueError):
    """A requested comparison needs clarification or repaired source evidence."""


class RelationshipUnavailable(ComparisonUnavailable):
    """Fields on disconnected record types cannot establish a zero result."""


def _resolve_category_filters(
    conn: duckdb.DuckDBPyConnection, plan: ComparisonPlan, schema: dict[str, dict], *, resolve_case: bool = True,
) -> ComparisonPlan:
    """Resolve model label casing only when the recorded category is unique.

    Dashboard slicers retain exact matching. Model-authored filters are checked
    against the analysed file, never accepted as evidence of a missing cohort.
    """
    resolved = plan.model_dump()
    for name in ("filters", "cohort_filters", "return_filters"):
        for selected in resolved[name]:
            if selected["op"] != "in":
                continue
            column = selected["column"]
            expression = category_expression(column, schema[column])
            values = []
            for value in selected["values"]:
                aliases = value_aliases(schema[column], value)
                if schema[column].get("analysis_role") == "identifier" or _numeric_filter_field(schema[column]):
                    predicate, params = _comparison_where([{**selected, "values": [value]}], schema)
                    found = conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {predicate})", params).fetchone()[0]
                    if not found and len(aliases) == 1 and aliases[0] is not None:
                        value = aliases[0]
                        predicate, params = _comparison_where([{**selected, "values": [value]}], schema)
                        found = conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {predicate})", params).fetchone()[0]
                    if not found and resolve_case:
                        kind = "code" if schema[column].get("analysis_role") == "identifier" else "value"
                        choice = "the exact code shown" if kind == "code" else "a recorded value"
                        raise ComparisonUnavailable(f"The requested {_field_label(column, schema)} {kind} {str(value)!r} was not found. Choose {choice} in this report.")
                    values.append(value)
                    continue
                predicate, params = _comparison_where([{**selected, "values": [value]}], schema)
                if conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {predicate})", params).fetchone()[0]:
                    values.append(value)
                    continue
                if len(aliases) == 1 and aliases[0] is not None:
                    raw = aliases[0]
                    predicate, params = _comparison_where([{**selected, "values": [raw]}], schema)
                    if conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {predicate})", params).fetchone()[0]:
                        values.append(raw)
                        continue
                if not resolve_case:
                    values.append(value)
                    continue
                if (schema[column].get("data_definition") or {}).get("value_labels"):
                    raise ComparisonUnavailable(f"The requested {_field_label(column, schema)} code or supplied meaning {str(value)!r} was not found. Choose the exact recorded code or its supplied label.")
                matches = conn.execute(
                    f"SELECT DISTINCT {expression} FROM data WHERE LOWER(TRIM({expression})) = LOWER(TRIM(?)) LIMIT 2",
                    [category_filter_value(column, value, schema[column])]).fetchall()
                if len(matches) != 1:
                    reason = "matches multiple recorded categories" if matches else "does not match a recorded category"
                    raise ComparisonUnavailable(f"The requested {_field_label(column, schema)} value {str(value)!r} {reason}. Choose the exact category shown in this report.")
                values.append(matches[0][0])
            selected["values"] = values
    return ComparisonPlan.model_validate(resolved)


def _check_relationship_fields(conn: duckdb.DuckDBPyConnection, metadata: dict, plan: ComparisonPlan) -> None:
    context = metadata.get("upload_context") or {}
    if not context.get("combined") or context.get("combine_strategy") not in {None, "portfolio"}:
        return
    fields = list(dict.fromkeys(c for c in [plan.column, plan.group_by, plan.weight_column,
        *[f.column for f in [*plan.filters, *plan.cohort_filters, *plan.return_filters]]] if c))
    if len(fields) < 2:
        return
    predicates = [f"{quote(c)} IS NOT NULL AND TRIM(CAST({quote(c)} AS VARCHAR)) <> ''" for c in fields]
    together = " AND ".join(f"({p})" for p in predicates)
    if conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {together})").fetchone()[0]:
        return
    if all(conn.execute(f"SELECT EXISTS(SELECT 1 FROM data WHERE {p})").fetchone()[0] for p in predicates):
        raise RelationshipUnavailable(
            "These fields are stored on separate record types in this older combined report. "
            "Re-analyse the original files to verify their identifier relationship before comparing them."
        )


def _cohort_label(filters: list[ComparisonFilter], fallback: str) -> str:
    periods = [selected for selected in filters if selected.op == "date_between"]
    if len(periods) == 1:
        start, end = periods[0].values
        year = str(start)[:4]
        if start == f"{year}-01-01" and end == f"{year}-12-31":
            return year
    return fallback


def _retention_result(conn: duckdb.DuckDBPyConnection, analysis: Any, plan: ComparisonPlan,
                      entity: str, baseline_filters: list[dict], rows: int, truncated: bool) -> dict:
    schema = _schema(analysis.metadata_ or {})
    return_filters = _comparison_filters([f.model_dump() for f in [*plan.filters, *plan.return_filters]], schema)
    baseline_where, baseline_params = _comparison_where(baseline_filters, schema)
    return_where, return_params = _comparison_where(return_filters, schema)
    valid = f"{entity} IS NOT NULL AND LOWER({entity}) <> 'unknown'"
    # Distinct sets prevent multiple transactions from counting an entity twice.
    cte = (f"WITH baseline AS (SELECT DISTINCT {entity} AS entity FROM data WHERE ({baseline_where}) AND {valid}), "
           f"return_cohort AS (SELECT DISTINCT {entity} AS entity FROM data WHERE ({return_where}) AND {valid}) ")
    denominator, numerator = conn.execute(cte +
        "SELECT COUNT(*), COUNT(return_cohort.entity) FROM baseline LEFT JOIN return_cohort USING (entity)",
        [*baseline_params, *return_params]).fetchone()
    matched, supplied = conn.execute(
        f"SELECT COUNT(*), COUNT(CASE WHEN {valid} THEN 1 END) FROM data WHERE {baseline_where}",
        baseline_params).fetchone()
    value = 100.0 * numerator / denominator if denominator else None
    entity_label = _field_label(plan.column, schema)
    items = f"{entity_label}s" if entity_label.endswith(" ID") else f"different {entity_label} values"
    first = _cohort_label(plan.cohort_filters, "the first group")
    second = _cohort_label(plan.return_filters, "the second group")
    title = f"How many {items} appear in both groups"
    answer = (f"{numerator:,} of {denominator:,} {items} in {first} "
              f"also appear in {second} ({value:.1f}%).") if denominator else (
                  "The first group has no filled-in values to count, so its percentage is unavailable.")
    if value is not None and 1 <= value <= 99:
        answer += f" That is about {value:.0f} out of every 100."
    scope = _scope(analysis, rows, truncated) + _identifier_note(plan, schema)
    scope += f" We counted each different {entity_label} once in each group. Blank values and values marked 'unknown' were left out."
    if re.search(r"(?:^|[\s_])(id|key|code)$", str(plan.column), re.I):
        scope += " An ID is a code in your file. We have not checked who or what each code belongs to."
    if denominator:
        scope += f" We divided {numerator:,} by {denominator:,} and multiplied by 100 to get the percentage."
    for description, selected in (("first", baseline_filters), ("second", return_filters)):
        scope += f" In the {description} group, " + ", and ".join(_filter_description(f, schema) for f in selected) + "."
    return {
        "title": title, "answer": answer, "scope": scope,
        "groups": [{"group": None, "group_value": None, "value": value,
                    "entries": matched, "supplied_values": supplied}],
        "cohort": {"baseline_entities": denominator, "returning_entities": numerator},
        "ranking": None, "matched_entries": matched, "group_count": 1,
        "evidence_revision": evidence_revision(analysis.id, analysis.row_count, analysis.metadata_ or {}),
        "plan": plan.model_dump(), "calculation": "100 * distinct intersecting entities / distinct starting entities",
        "source": "analysed_file", "sample_truncated": truncated, "value_unit": "%",
    }


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
    measure = result.get("measure_label") or label(plan.get("column"))
    scale = result.get("percentage_scale")
    context = result.get("record_context") or {}
    singular, plural = context.get("singular", "entry"), context.get("plural", "entries")
    if result.get("aggregation_basis", {}).get("kind") == "source_entities":
        singular = "source record"
    metric = {"sum": f"total {measure}", "average": f"average {measure} per {singular}",
              "weighted_average": f"{measure}, weighted by {result.get('weight_label') or label(plan.get('weight_column'))}",
              "count": f"number of {plural}", "distinct_count": f"number of different {measure} values"}.get(operation)
    if metric is None:
        return result.get("answer", "")
    suffix = result.get("value_unit") or ""
    if suffix == "%":
        metric = "average recorded admission chance"
    rank = "lowest" if plan.get("order") == "asc" else "highest"
    def group_label(value: Any, display_label: str | None = None) -> str:
        if display_label:
            return display_label
        if value is None:
            return f"Entries without {result.get('group_label') or label(plan['group_by'])}"
        text = str(value) if result.get("group_codes_exact") else _display_group(plan["group_by"], value, plan.get("date_bucket"))
        name = result.get("group_label") or label(plan["group_by"])
        return f"{name[:1].upper() + name[1:]} {text}" if not plan.get("date_bucket") and re.fullmatch(r"-?\d+(?:\.\d+)?", text) else text

    subject = group_label(first.get("group"), first.get("display_label"))
    tied = ranking.get("tied", 1)
    if tied > 1:
        lead = f"{tied:,} groups tie for the {rank} {metric} at {_display_number(value, scale)}{suffix} each."
        visible_ties = sum(row.get("value") == first.get("value") for row in groups)
        if visible_ties < tied:
            lead += f" Showing {visible_ties:,} of these tied groups"
            lead += f", {subject}." if len(groups) == 1 else "."
    elif result.get("group_count") == 1:
        lead = f"{subject} is the only group in this comparison, with {metric} of {_display_number(value, scale)}{suffix}."
    else:
        lead = f"{subject} {'has' if first.get('group') is not None else 'have'} the {rank} {metric}, at {_display_number(value, scale)}{suffix}."
        runner = ranking.get("runner_up") or {}
        runner_value = _finite(runner.get("value"))
        if runner_value is not None:
            other = group_label(runner.get("group"), runner.get("display_label"))
            difference = abs(value - runner_value)
            # Avoid a rounded zero gap between distinct measurements.
            if difference >= .005:
                lead += f" That is {_display_number(difference, scale)}{' percentage points' if suffix == '%' else ''} {'less' if rank == 'lowest' else 'more'} than {other}."
    if len(groups) > 1:
        figures = "\n".join(f"{group_label(row.get('group'), row.get('display_label'))}: {_display_number(row['value'], scale) + suffix if _finite(row.get('value')) is not None else 'Not available'}"
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
            evidence_texts = dict.fromkeys(str(value) for value in (
                data.get("source_evidence"), data.get("evidence"), data.get("problem"),
            ) if value)
            for text in evidence_texts:
                matches = [index for index, issue in enumerate((metadata.get("data_quality") or {}).get("issues") or [])
                           if issue.get("column") == data["column"] and issue.get("description")
                           and plain_english(issue["description"]).lower() in plain_english(text).lower()]
                if len(matches) == 1:
                    return evidence_spec(metadata, issue_index=matches[0])
                if matches:
                    return None
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
        request = request.model_copy(update={"comparison": _numeric_definition_filters(request.comparison, schema)})
        _expression, group, filters = validate_plan(request.comparison, metadata)
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
        if request.kind == "comparison" and request.comparison:
            _check_relationship_fields(conn, metadata, request.comparison)
            selected_fields = [item.column for item in [*request.comparison.filters, *request.comparison.cohort_filters, *request.comparison.return_filters]]
            if any((schema.get(name, {}).get("data_definition") or {}).get("value_labels") for name in selected_fields):
                plan = _resolve_category_filters(conn, request.comparison, schema, resolve_case=False)
                request = request.model_copy(update={"comparison": plan})
                _expression, group, filters = validate_plan(plan, metadata)
            predicate, params = _comparison_where(filters, schema)
            if request.comparison.aggregation == "retention":
                predicate = f"({predicate}) AND {_expression} IS NOT NULL AND LOWER({_expression}) <> 'unknown'"
            if group and request.group_value is not None:
                predicate = (predicate + " AND " if predicate else "") + f"{group} = ?"
                params.append(request.group_value)
            elif group:
                predicate = (predicate + " AND " if predicate else "") + f"{group} IS NULL"
        basis = _source_measure_basis(request.comparison, schema) if request.kind == "comparison" and request.comparison and request.comparison.aggregation in {"sum", "average"} else None
        if basis:
            source_where, source_params = _comparison_where(filters, schema)
            _source_aggregation_relation(conn, request.comparison, schema, basis, group, source_where, source_params)
            keys = [_identifier_expression(name) for name in basis["entity_key_columns"]]
            complete = " AND ".join(f"({key} IS NOT NULL AND LOWER({key}) <> 'unknown')" for key in keys)
            predicate = f"({predicate}) AND ({complete})" if predicate else complete
        columns = list(schema)
        # Entry numbers describe positions in the analysed copy, never Excel
        # row numbers. Exact-repeat numbering excludes the first copy.
        partition = ", ".join(quote(c) for c in columns)
        if request.kind != "comparison" and spec["kind"] == "repeat_values":
            partition = quote(spec["column"])
        cte = f"WITH indexed AS (SELECT *, row_number() OVER () AS {quote(entry_name)} FROM data), numbered AS (SELECT *, row_number() OVER (PARTITION BY {partition} ORDER BY {quote(entry_name)}) AS {quote(repeat_name)} FROM indexed) "
        where = f" WHERE {predicate}" if predicate else ""
        matched = conn.execute(cte + "SELECT COUNT(*) FROM numbered" + where, params).fetchone()[0]
        if basis:
            entity_count = conn.execute(cte + f"SELECT COUNT(*) FROM (SELECT DISTINCT {', '.join(keys)} FROM numbered{where})", params).fetchone()[0]
            basis = {**basis, "entities": entity_count, "supporting_entries": matched}
        if expected is not None and matched != expected:
            raise ValueError("The file no longer matches this saved check. Analyse it again before reviewing these entries.")
        if request.kind == "insight" and not matched:
            raise ValueError("The entry behind this finding could not be found in the saved file.")
        priority = [c for role in ("identifier", "temporal_dimension", "dimension") for c in columns if schema[c].get("analysis_role") == role]
        measure = request.comparison.column if request.comparison else (spec.get("issue") or spec.get("anomaly") or spec).get("column")
        context = record_context(metadata)
        source_keys = basis["entity_key_columns"] if basis else []
        shown = list(dict.fromkeys([*([measure] if measure else []), *source_keys, *identifying_columns(schema, context), *priority, *columns]))[:20]
        selected = ", ".join(quote(c) for c in shown)
        found = conn.execute(cte + f"SELECT {quote(entry_name)}, {selected} FROM numbered{where} ORDER BY {quote(entry_name)} LIMIT ? OFFSET ?", [*params, request.limit, request.offset]).fetchall()
        records = []
        for row in found:
            values = {c: _cell(v) for c, v in zip(shown, row[1:], strict=True)}
            displays = {name: display for name, value in values.items()
                        if (display := value_display_label(schema[name], value)) is not None}
            records.append({"entry_number": row[0], "record_label": record_label(values, schema, context, row[0]), "values": values,
                            **({"display_values": displays} if displays else {})})
        scope = _scope(analysis, rows, truncated)
        if request.comparison:
            scope += _identifier_note(request.comparison, schema)
        if request.comparison and request.comparison.aggregation == "retention":
            scope += " Shows entries from the first group with a filled-in ID. One ID can appear on several entries. We count it only once when working out the percentage."
        if basis:
            scope += (f" These {matched:,} supporting entries link to {basis['entities']:,} records from {basis['source_table']}. "
                      "Each source record was counted once in the calculation. Its number can appear on several supporting entries.")
        if context:
            scope = scope.replace("entry numbers", "record positions").replace("entries", context["plural"])
        return {"matched_entries": matched, "offset": request.offset, "limit": request.limit,
                **({"aggregation_basis": basis} if basis else {}),
                "record_context": context,
                "columns": [{"name": c, "label": _field_label(c, schema), "is_date": bool(schema[c].get("is_date"))} for c in shown],
                "entries": records,
                "scope": scope + (f" Showing {len(shown)} of {len(columns)} fields, with identifying details first." if len(shown) < len(columns) else ""), "sample_truncated": truncated,
                "has_more": request.offset + len(found) < matched}
    finally:
        conn.close()
