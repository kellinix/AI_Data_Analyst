"""Keep repeated lookup values from becoming transaction-level measures."""
from __future__ import annotations

import re
from typing import Any


def annotate_measure_grain(
    schema: list[dict[str, Any]], context: Any = None, parser: Any = None,
) -> list[dict[str, Any]]:
    context = context if isinstance(context, dict) else {}
    cleaning = context.get("cleaning") or {}
    report = (cleaning.get("report") or {}) if isinstance(cleaning, dict) else {}
    parser = parser if isinstance(parser, dict) else {}
    candidates = [
        context.get("relationship_resolution"),
        parser.get("relationship_resolution"),
        (report.get("parser") or {}).get("relationship_resolution"),
    ]
    def merge_origins(previous, supplied):
        previous = previous if isinstance(previous, dict) else {}
        supplied = supplied if isinstance(supplied, dict) else {}
        merged = {**previous, **supplied}
        identity = ["source_table", "source_column", "source_sheet", "source_role", "relationship_path", "entity_key_columns"]
        if any(key in previous and key in supplied and previous[key] != supplied[key] for key in identity):
            merged.update(key_basis="conflicting_sources", entity_key_columns=[])
        if previous.get("kind") == "lookup" or supplied.get("kind") == "lookup":
            merged["kind"] = "lookup"
        if previous.get("repeated") is True or supplied.get("repeated") is True:
            merged["repeated"] = True
        return merged

    origins = {}
    for resolution in candidates:
        if isinstance(resolution, dict):
            for name, origin in (resolution.get("field_origins") or {}).items():
                origins[name] = merge_origins(origins.get(name), origin)
    renames = report.get("renamed_columns") or {}
    names = {field["name"] for field in schema}
    canonical = {}
    for name in names:
        canonical.setdefault(re.sub(r"[^a-z0-9]", "", name.casefold()), []).append(name)

    def mapped_column(name):
        mapped = renames.get(name, name)
        if mapped not in names:
            matches = canonical.get(re.sub(r"[^a-z0-9]", "", mapped.casefold()), [])
            mapped = matches[0] if len(matches) == 1 else None
        return mapped

    def mapped_origin(origin):
        mapped = dict(origin) if isinstance(origin, dict) else {}
        if "entity_key_columns" in mapped:
            entity_keys = []
            for original_key in origin.get("entity_key_columns", []):
                cleaned_key = mapped_column(original_key)
                entity_keys.append(cleaned_key if cleaned_key is not None else original_key)
            mapped["entity_key_columns"] = entity_keys
        return mapped

    selected = {}
    for name, origin in origins.items():
        mapped = mapped_column(name)
        if mapped and isinstance(origin, dict):
            selected[mapped] = mapped_origin(origin)
    linked_keys = set()
    for resolution in candidates:
        if not isinstance(resolution, dict) or resolution.get("status") != "enriched":
            continue
        for link in resolution.get("joins") or []:
            linked_keys.update(mapped_column(key) for key in link.get("foreign_keys", []))
    annotated = []
    for field in schema:
        origin = merge_origins(mapped_origin(field.get("measure_grain")), selected.get(field["name"]))
        if field["name"] in linked_keys:
            origin["relationship_key"] = True
        annotated.append({**field, "measure_grain": origin} if origin else dict(field))
    return annotated


def is_repeated_lookup(field: dict[str, Any]) -> bool:
    origin = field.get("measure_grain") or {}
    return isinstance(origin, dict) and origin.get("kind") == "lookup" and origin.get("repeated") is True


def analytical_schema(schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [field for field in schema if not (field.get("is_numeric") and is_repeated_lookup(field))]


def analytical_numeric_statistics(schema: list[dict[str, Any]], numeric_stats: dict[str, Any]) -> dict[str, Any]:
    repeated = {field["name"] for field in schema if is_repeated_lookup(field)}
    safe = {}
    for name, stats in numeric_stats.items():
        if stats.get("weight_column") in repeated:
            safe[name] = {key: value for key, value in stats.items()
                          if key not in {"weighted_mean", "weight_column"}}
        else:
            safe[name] = stats
    return safe


def analytical_statistics(statistics: dict[str, Any]) -> dict[str, Any]:
    schema = analytical_schema(statistics.get("schema") or [])
    names = {field["name"] for field in schema}
    numeric = analytical_numeric_statistics(
        statistics.get("schema") or [], statistics.get("numeric_stats") or {},
    )
    return {
        **statistics,
        "schema": schema,
        "numeric_stats": {name: values for name, values in numeric.items() if name in names},
    }


def lookup_aggregation_message(field: dict[str, Any]) -> str:
    source = (field.get("measure_grain") or {}).get("source_table") or "another source table"
    return (f"This number comes from {source}. One source row appears in several entries in this report. "
            "Its total or average needs a calculation that counts each source row once. "
            "That source-level calculation is currently unavailable in this combined report.")
