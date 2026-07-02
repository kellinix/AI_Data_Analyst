from __future__ import annotations

"""
Semantic column detection.

The product promise is zero configuration, so the platform needs to infer what
columns mean from names, dtypes, and observed values before any LLM reasoning.
"""

from dataclasses import dataclass
import re
from typing import Any


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,}$")


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
    "age",
    "height",
    "weight",
    "jersey",
    "shirt_number",
    "squad_number",
    "number",
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


def enrich_schema_with_semantics(
    schema: list[dict[str, Any]],
    numeric_stats: dict[str, Any],
    categorical_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return schema rows with semantic_type, confidence, and role metadata."""
    enriched: list[dict[str, Any]] = []
    for column in schema:
        profile = detect_column_semantics(column, numeric_stats, categorical_stats)
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

    if _looks_like_date_name(normalized):
        return _profile("date", 0.9, "Column name looks like a date or time field", "temporal_dimension")

    if normalized in {"source_file", "sheet"}:
        return _profile("source", 0.96, "Column identifies the source table or workbook sheet", "dimension")

    if _looks_like_year(normalized, column, numeric_stats):
        return _profile("year", 0.94, "Column name and values look like calendar years", "temporal_dimension")

    if _looks_like_identifier(normalized):
        return _profile("identifier", 0.9, "Column name looks like a record identifier", "identifier")

    if normalized.startswith("is_") or normalized.startswith("has_"):
        return _profile("boolean", 0.82, "Column name looks like a boolean flag", "flag")

    if "description" in normalized or normalized in {"summary", "title", "headline"}:
        return _profile("text", 0.78, "Column name looks like descriptive text", "text")

    for rule in RULES:
        if any(keyword in normalized for keyword in rule.keywords):
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
        if minimum is not None and maximum is not None and 0 <= minimum <= maximum <= 1:
            return _profile("percentage", 0.72, "Numeric values fall between 0 and 1", "metric")
        return _profile("numeric_metric", 0.7, "Numeric dtype", "metric")

    cat_stats = categorical_stats.get(name, {})
    unique_count = cat_stats.get("unique_count", 0)
    top_values = [str(item.get("value", "")) for item in cat_stats.get("top_values", [])]

    if top_values and sum(EMAIL_RE.match(value) is not None for value in top_values) >= max(1, len(top_values) // 2):
        return _profile("email", 0.9, "Observed values look like email addresses", "identifier")

    if top_values and sum(PHONE_RE.match(value) is not None for value in top_values) >= max(1, len(top_values) // 2):
        return _profile("phone", 0.86, "Observed values look like phone numbers", "identifier")

    if 1 <= unique_count <= 2:
        return _profile("boolean", 0.72, "Low-cardinality binary-like column", "flag")

    if unique_count:
        return _profile("categorical_dimension", 0.66, "Non-numeric grouped values", "dimension")

    return _profile("unknown", 0.4, "Insufficient evidence", "unknown")


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower())


def _looks_like_identifier(normalized: str) -> bool:
    if normalized in {"id", "uuid", "guid"}:
        return True
    return (
        normalized.endswith("_id")
        or normalized.endswith("_uuid")
        or normalized.endswith("_guid")
        or normalized.startswith("id_")
    )


def _looks_like_date_name(normalized: str) -> bool:
    parts = set(normalized.split("_"))
    return (
        "date" in parts
        or "time" in parts
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
    if normalized in {"number"} or "jersey" in parts:
        return True
    if any(keyword in parts for keyword in NUMERIC_ATTRIBUTE_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in ("shirt_number", "squad_number")):
        return True
    if "id" in parts or normalized.endswith("_id") or normalized.startswith("id_"):
        return True
    if minimum is not None and maximum is not None and 1900 <= minimum <= maximum <= 2200:
        return True
    return False


def _looks_like_average_metric(normalized: str) -> bool:
    return any(keyword in normalized for keyword in AVERAGE_METRIC_KEYWORDS)


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
    if semantic_type in {"currency", "percentage"} or column.get("is_numeric"):
        return "metric"
    return "dimension"
