"""Conservative grouping of geographic label variants without editing source rows."""
from __future__ import annotations

import re

from app.analytics.sql_utils import quote_identifier


def normalized_geography(column: str) -> bool:
    return bool(set(re.findall(r"[a-z]+", column.lower())) & {"region", "state", "country", "city", "town"})


def category_expression(column: str) -> str:
    value = f"CAST({quote_identifier(column)} AS VARCHAR)"
    if normalized_geography(column):
        return f"LOWER(REGEXP_REPLACE(TRIM({value}), '[[:space:]-]+', ' ', 'g'))"
    return value


def category_label(column: str, value: object) -> str:
    text = str(value)
    return text.title() if normalized_geography(column) else text


def category_filter_value(column: str, value: object) -> str:
    text = str(value)
    return re.sub(r"[\s-]+", " ", text.strip()).lower() if normalized_geography(column) else text
