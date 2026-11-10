"""
Semantic column detection.

The product promise is zero configuration, so the platform needs to infer what
columns mean from names, dtypes, and observed values before any LLM reasoning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.analytics.measure_semantics import (
    FLOW_KEYWORDS,
    NON_ADDITIVE_KEYWORDS,
    VOLUME_KEYWORDS,
    calendar_component,
    is_additive_flow,
)
from app.analytics.percentage_scale import SCALE_WARNING, ambiguous_percentage, named_percentage
from app.analytics.text_matching import contains_keyword

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,}$")
DATE_VALUE_RE = re.compile(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}")


@dataclass(frozen=True)
class SemanticRule:
    semantic_type: str
    keywords: tuple[str, ...]
    confidence: float


RULES: tuple[SemanticRule, ...] = (
    SemanticRule("currency", ("revenue", "sales", "profit", "price", "amount", "cost", "expense", "gmv", "arr", "mrr"), 0.92),
    SemanticRule("percentage", ("percent", "percentage", "rate", "margin", "conversion", "churn", "retention"), 0.88),
    SemanticRule("country", ("country", "nation", "market"), 0.86),
    SemanticRule("city", ("city", "town", "metro"), 0.84),
    SemanticRule("product", ("product", "sku", "item", "style", "model"), 0.88),
    SemanticRule("category", ("category", "segment", "channel", "type", "class"), 0.84),
    SemanticRule("department", ("department", "team", "division", "function"), 0.84),
    SemanticRule("employee_name", ("employee", "staff", "rep", "agent", "owner", "manager"), 0.78),
    SemanticRule("customer_id", ("customer_id", "client_id", "account_id", "user_id", "buyer_id"), 0.92),
    SemanticRule("invoice_id", ("invoice", "order_id", "transaction_id", "receipt", "booking_id"), 0.9),
    SemanticRule("email", ("email", "e-mail"), 0.95),
    SemanticRule("phone", ("phone", "mobile", "telephone"), 0.94),
)

NUMERIC_ATTRIBUTE_KEYWORDS = (
    "height",
    "age",
    "latitude",
    "longitude",
    "lat",
    "lon",
    "lng",
    "coord",
)

AVERAGE_METRIC_KEYWORDS = (
    "accuracy",
    "rating",
    "score",
    "percentage",
    "percent",
    "pct",
    "rate",
    "ratio",
    "speed",
    "stamina",
    "impact",
    "resistance",
    "creativity",
    "consistency",
)

SPORT_COUNT_COLUMNS = {
    "mp", "starts", "gls", "ast", "g_a", "g_pk", "pk", "pkatt",
    "crdy", "crdr", "g_a_pk", "saves", "ga", "sota", "cs",
    "sh", "sot", "compl", "subs", "unsub", "fls", "fld",
    "off", "crs", "int", "tklw", "og",
}


def enrich_schema_with_semantics(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
    categorical_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return schema rows with semantic_type, confidence, and role metadata."""
    enriched: list[dict[str, Any]] = []
    from app.analytics.survey_context import survey_fields
    survey = survey_fields(schema)
    for column in schema:
        profile = detect_column_semantics(column, numeric_stats, categorical_stats)
        if (column.get("is_numeric") and ambiguous_percentage(column["name"], numeric_stats.get(column["name"], {}))
                and not (survey and column["name"] == survey["percentage"])):
            profile.update({"percentage_scale": "unconfirmed", "display_warning": SCALE_WARNING})
        enriched.append({**column, **profile})
    return enriched


def detect_column_semantics(
    column: dict[str, Any],
    numeric_stats: dict[str, Any],
    categorical_stats: dict[str, Any],
) -> dict[str, Any]:
    name = str(column["name"])
    normalized = _normalize(name)

    if column.get("is_date"):
        return _profile("date", 0.98, "Date or timestamp dtype", "temporal_dimension")

    if _looks_like_date_name(normalized) and _has_date_like_values(column, name, categorical_stats):
        return _profile("date", 0.9, "Column name looks like a date or time field", "temporal_dimension")

    if normalized in {"source_file", "sheet"}:
        return _profile("source", 0.96, "Column identifies the source table or workbook sheet", "dimension")
    if not column.get("is_numeric") and (normalized in {"season", "seasons", "academic_year", "school_year"}):
        return _profile("season", 0.95, "Named season or academic-period labels", "dimension")

    if re.fullmatch(r"column_\d+", normalized):
        return _profile("unknown", 0.95, "Unnamed source column needs a supplied label", "unknown")

    if normalized in {"store", "store_number", "store_no", "store_num", "branch", "branch_number", "branch_no", "shop", "shop_number"}:
        return _profile("categorical_dimension", 0.94, "Column identifies a location or store group", "dimension")
    if normalized in {"shift", "hiring_stage", "appointment_status"}:
        return _profile("categorical_dimension", 0.94, "Named operational group, not a yes/no flag", "dimension")

    if _looks_like_year(normalized, column, numeric_stats):
        return _profile("year", 0.94, "Column name and values look like calendar years", "temporal_dimension")

    if column.get("is_numeric"):
        component = calendar_component(normalized, numeric_stats.get(name, {}))
        if component:
            return _profile(component, 0.94, "Calendar component, not a measurable quantity", "dimension")
        stats = numeric_stats.get(name, {})
        if stats.get("aggregation_warning"):
            return _profile("unresolved_duration", 0.9, stats["aggregation_warning"]["description"], "unresolved")
        # Explicit code vocabulary wins over activity words (e.g. click_code).
        # Bare singular activity words with a tiny bounded integer domain can
        # also be ratings. Plurals and explicit count/total names remain counts.
        words = set(normalized.split("_"))
        singular_activity = {word[:-1] for word in VOLUME_KEYWORDS if word.endswith("s")}
        if _looks_like_categorical_code(column, stats) and (
            words & {"code", "grade", "level", "condition"}
            or normalized in singular_activity and 3 <= stats.get("unique_count", 0) <= 5
            and 0 <= stats.get("min", -1) <= stats.get("max", 6) <= 5
        ):
            return _profile("categorical_code", 0.85, "Bounded repeated codes; additive meaning is not established", "dimension")

    if _looks_like_identifier(normalized):
        return _profile("identifier", 0.9, "Column name looks like a record identifier", "identifier")
    if column.get("is_numeric") and (normalized.startswith("number_of_") or normalized.endswith("_count")):
        return _profile("count", 0.9, "Explicit count of items or people, rather than their identifier", "metric")

    if normalized in SPORT_COUNT_COLUMNS:
        return _profile("numeric_metric", 0.7, "A short numeric field name does not establish its unit or whether values can be added", "metric")
    if column.get("is_numeric") and named_percentage(normalized):
        return _profile("percentage", 0.94, "Column explicitly names a percentage, rather than an amount of money", "metric")

    if column.get("is_numeric") and contains_keyword(normalized, VOLUME_KEYWORDS) and is_additive_flow(normalized):
        return _profile("count", 0.88, "Named count of activity", "metric")

    if normalized.startswith("is_") or normalized.startswith("has_") or normalized.endswith("_flag"):
        return _profile("boolean", 0.82, "Column name looks like a boolean flag", "flag")

    if "description" in normalized or normalized in {"summary", "title", "headline"}:
        return _profile("text", 0.78, "Column name looks like descriptive text", "text")

    for rule in RULES:
        if contains_keyword(normalized, rule.keywords):
            return _profile(
                rule.semantic_type,
                rule.confidence,
                f"Column name matches {rule.semantic_type} vocabulary",
                _role_for(rule.semantic_type, column),
            )

    if column.get("is_numeric"):
        stats = numeric_stats.get(name, {})
        minimum = stats.get("min")
        maximum = stats.get("max")
        if _looks_like_numeric_attribute(normalized, minimum, maximum):
            return _profile("numeric_attribute", 0.84, "Numeric descriptor, not an additive metric", "attribute")
        if _looks_like_average_metric(normalized):
            return _profile("average_metric", 0.78, "Numeric performance score or rate", "metric")
        if _looks_like_categorical_code(column, stats):
            if stats.get("unique_count", 0) <= 2:
                return _profile("boolean", 0.8, "Integer column with only two repeated values", "flag")
            return _profile("categorical_code", 0.78, "Small set of repeated integer codes, not a measurable quantity", "dimension")
        if minimum is not None and maximum is not None and 0 <= minimum <= maximum <= 1:
            return _profile("numeric_metric", 0.7, "Numeric values between 0 and 1 do not establish a percentage scale", "metric")
        if _looks_like_row_sequence(normalized, stats):
            return _profile("row_sequence", 0.85, "Unique consecutive integers starting at zero or one; likely row numbering, not a measure", "identifier")
        return _profile("numeric_metric", 0.7, "Numeric dtype", "metric")

    cat_stats = categorical_stats.get(name, {})
    unique_count = cat_stats.get("unique_count", 0)
    top_values = [str(item.get("value", "")) for item in cat_stats.get("top_values", [])]

    if top_values and sum(EMAIL_RE.match(value) is not None for value in top_values) >= max(1, len(top_values) // 2):
        return _profile("email", 0.9, "Observed values look like email addresses", "identifier")

    if top_values and sum(PHONE_RE.match(value) is not None and len(re.sub(r"\D", "", value)) >= 7 for value in top_values) >= max(1, len(top_values) // 2):
        return _profile("phone", 0.86, "Observed values look like phone numbers", "identifier")

    if 1 <= unique_count <= 2:
        return _profile("boolean", 0.72, "Low-cardinality binary-like column", "flag")

    if unique_count:
        return _profile("categorical_dimension", 0.66, "Non-numeric grouped values", "dimension")

    return _profile("unknown", 0.4, "Insufficient evidence", "unknown")


def _normalize(value: str) -> str:
    separated = re.sub(r"([a-z])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "_", separated.lower()).strip("_")


def _looks_like_identifier(normalized: str) -> bool:
    if is_serial_identifier(normalized):
        return True
    if normalized in {"id", "uuid", "guid", "shipmentid", "spid", "pid", "gid", "gmppidnumber"}:
        return True
    if normalized.startswith("rk_stats_"):
        return True
    compact = normalized.replace("_", "")
    if compact in {"flight", "registration", "sku", "trackingnumber"}:
        return True
    if re.fullmatch(r"(?:employee|staff|customer|client|patient|donor|student|member|user|account|order|invoice|shipment|product|supplier|vendor|booking|flight|policy|claim|transaction|ticket|asset|application)(?:id|number|num|no|code|key)", compact):
        return True
    return (
        normalized.endswith("_id")
        or normalized.endswith("_uuid")
        or normalized.endswith("_guid")
        or normalized.startswith("id_")
    )


def is_serial_identifier(column: str) -> bool:
    """Row numbering is not an entity identity or a business measure."""
    return re.fullmatch(
        r"(?:sr|sr_no|sr_number|s_no|sno|serial|serial_no|serial_number|row_no|row_number|record_no|record_number|rk|rank)(?:_\d+)?",
        _normalize(column),
    ) is not None


def _has_date_like_values(
    column: dict[str, Any], name: str, categorical_stats: dict[str, Any]
) -> bool:
    """Whether a date-ish *name* is backed by date-ish values.

    Numeric columns keep the name-only rule (a date can legitimately arrive as
    20260710). Text columns must show dates in their observed values: prose
    names like "...assessment of the project at a fixed point in time..."
    otherwise turned a Red/Amber/Green rating into the dashboard's time axis.
    """
    if column.get("is_numeric"):
        return True
    top_values = (categorical_stats.get(name) or {}).get("top_values") or []
    values = [str(item.get("value", "")) for item in top_values if isinstance(item, dict)]
    if not values:
        return False
    return sum(bool(DATE_VALUE_RE.search(value)) for value in values) / len(values) >= 0.5


def _looks_like_date_name(normalized: str) -> bool:
    parts = set(normalized.split("_"))
    return (
        "date" in parts
        or "timestamp" in parts
        or normalized.endswith("_at")
        or normalized in {"period", "month", "datetime"}
    )


def _looks_like_numeric_attribute(
    normalized: str,
    minimum: Any,
    maximum: Any,
) -> bool:
    parts = set(normalized.split("_"))
    if "market_value" in normalized:
        return False
    if any(keyword in parts for keyword in NUMERIC_ATTRIBUTE_KEYWORDS):
        return True
    if "id" in parts or normalized.endswith("_id") or normalized.startswith("id_"):
        return True
    if minimum is not None and maximum is not None and 1900 <= minimum <= maximum <= 2200:
        return True
    return False


def _looks_like_average_metric(normalized: str) -> bool:
    return any(keyword in normalized for keyword in AVERAGE_METRIC_KEYWORDS)


def _looks_like_categorical_code(column: dict[str, Any], stats: dict[str, Any]) -> bool:
    """Columns whose values are a small set of repeated integer codes
    (e.g. 0/1 flags or 0-4 category codes) are labels, not quantities —
    summing, averaging, or outlier-scanning them produces nonsense.

    The file loader parses CSVs permissively and stores numbers as DOUBLE,
    so integer-ness is judged from the observed values, not the dtype."""
    unique_count = stats.get("unique_count")
    count = stats.get("count") or 0
    minimum = stats.get("min")
    maximum = stats.get("max")
    if not unique_count or minimum is None or maximum is None:
        return False
    if unique_count > 12 or maximum - minimum > 20:
        return False
    if stats.get("integer_count") is not None and stats["integer_count"] != count:
        return False
    if "int" not in str(column.get("dtype", "")).lower() and not (
        float(minimum).is_integer() and float(maximum).is_integer()
    ):
        return False
    # Require enough repetition that the small domain isn't just a tiny sample.
    return count >= unique_count * 5


def _looks_like_row_sequence(name: str, stats: dict[str, Any]) -> bool:
    # A measurement can happen to run 1..N. A recognised quantity, unit or
    # duration name provides stronger evidence than the sequence pattern.
    if contains_keyword(name, (*FLOW_KEYWORDS, *NON_ADDITIVE_KEYWORDS,
                              "total", "count", "quantity", "units", "measurement", "reading",
                              "temperature", "pressure", "weight", "rainfall", "humidity",
                              "distance", "energy", "power", "elapsed", "days", "hours",
                              "minutes", "seconds", "kg", "mm", "cm", "rpm", "mw", "kwh")):
        return False
    count = stats.get("count") or 0
    return (
        count >= 20 and stats.get("unique_count") == count
        and stats.get("integer_count") == count
        and stats.get("min") in {0, 1}
        and stats.get("max") == stats["min"] + count - 1
    )


def _looks_like_year(
    normalized: str,
    column: dict[str, Any],
    numeric_stats: dict[str, Any],
) -> bool:
    if normalized not in {"year", "fiscal_year", "calendar_year"} and not normalized.endswith("_year"):
        return False
    if not column.get("is_numeric"):
        return True
    stats = numeric_stats.get(column["name"], {})
    minimum = stats.get("min")
    maximum = stats.get("max")
    if minimum is None or maximum is None:
        return True
    return 1900 <= minimum <= maximum <= 2200


def _profile(semantic_type: str, confidence: float, reason: str, role: str) -> dict[str, Any]:
    return {
        "semantic_type": semantic_type,
        "semantic_confidence": confidence,
        "semantic_reason": reason,
        "analysis_role": role,
    }


def _role_for(semantic_type: str, column: dict[str, Any]) -> str:
    if semantic_type in {"customer_id", "invoice_id", "email", "phone", "employee_name"}:
        return "identifier"
    if semantic_type in {"country", "city", "product", "category", "department"}:
        return "dimension"
    # Only a numeric column can be a metric. The name alone used to be enough,
    # so "Departmental Narrative on Budgeted Whole Life Costs" — free text —
    # was typed currency and carried analysis_role=metric into the profile the
    # AI reads.
    if not column.get("is_numeric"):
        return "text" if semantic_type == "text" else "dimension"
    return "metric"
