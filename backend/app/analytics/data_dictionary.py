"""Bind provided definitions to recorded source identities without editing data."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

from app.schemas.data_dictionary import DataDictionary


def _basename(value: Any) -> str:
    return PurePosixPath(str(value or "").replace("\\", "/")).name


def _value_key(field: dict[str, Any], value: Any) -> tuple[str, Any]:
    if value is None:
        return "null", ""
    if str(field.get("dtype") or "").upper() in {"BOOLEAN", "BOOL"} and value in ("true", "false"):
        return "bool", value == "true"
    if field.get("is_numeric") and not isinstance(value, bool):
        try:
            number = Decimal(str(value))
            if number.is_finite():
                return "number", number
        except InvalidOperation:
            pass
    return type(value).__name__, value


def value_definition(field: dict[str, Any], value: Any) -> dict[str, Any] | None:
    """Read one unambiguous meaning using this field's normal category rules."""
    key = _value_key(field, value)
    matches = [entry for entry in (field.get("data_definition") or {}).get("value_labels", [])
               if isinstance(entry, dict) and _value_key(field, entry.get("value")) == key]
    return matches[0] if len(matches) == 1 else None


def value_label(field: dict[str, Any], value: Any) -> str | None:
    definition = value_definition(field, value)
    return str(definition["label"]) if definition else None


def value_display_label(field: dict[str, Any], value: Any) -> str | None:
    """Show a supplied meaning beside the exact code supplied in its guide."""
    definition = value_definition(field, value)
    if definition is None:
        return None
    raw = definition["value"]
    code = raw if isinstance(raw, str) and raw else json.dumps(raw, ensure_ascii=False, allow_nan=False)
    label = str(definition["label"])
    return label if label == code else f"{label} ({code})"


def value_aliases(field: dict[str, Any], requested_label: Any) -> list[Any]:
    """Return a raw value only when a supplied friendly label has one meaning."""
    label = str(requested_label).strip().casefold()
    matches = [entry for entry in (field.get("data_definition") or {}).get("value_labels", [])
               if isinstance(entry, dict) and str(entry.get("label") or "").strip().casefold() == label]
    return [matches[0]["value"]] if len(matches) == 1 else []


def _identities(
    field: dict[str, Any], context: dict[str, Any], file_name: str | None, parser: dict[str, Any],
) -> list[dict[str, Any]]:
    origin = field.get("measure_grain") or {}
    if origin.get("key_basis") == "conflicting_sources":
        return []
    cleaning = context.get("cleaning") or {}
    report = cleaning.get("report") or {}
    originals = [original for original, cleaned in (report.get("renamed_columns") or {}).items()
                 if cleaned == field["name"]]
    if len(originals) > 1:
        return []
    fallback_file = cleaning.get("source_filename") or file_name
    if not fallback_file and len(context.get("source_files") or []) == 1:
        fallback_file = context["source_files"][0].get("name")
    identities = []
    for item in origin.get("source_origins") or [origin]:
        source_file = item.get("source_file") or item.get("source_table") or fallback_file
        sheet = item.get("source_sheet")
        # A standalone workbook's parser records sheet names as source_table.
        if not item.get("source_file") and fallback_file and str(fallback_file).lower().endswith((".xls", ".xlsx")):
            source_file = fallback_file
            sheet = sheet or item.get("source_table")
            included_sheets = parser.get("included_sheets") or []
            if sheet is None and len(included_sheets) == 1:
                sheet = included_sheets[0]
            if sheet is None and len(included_sheets) > 1:
                return []
        identities.append({"source_table": _basename(source_file), "source_sheet": sheet,
                           "source_column": item.get("source_column") or (originals[0] if originals else field["name"]),
                           "source_role": item.get("source_role"), "source_file_id": item.get("source_file_id")})
    return identities


def apply_data_dictionary(
    schema: list[dict[str, Any]], context: Any, *, file_name: str | None = None,
    parser: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Apply exact source-scoped labels, refusing uncertain or conflicting matches."""
    if not isinstance(context, dict) or "data_dictionary" not in context:
        return [dict(field) for field in schema]
    dictionary = DataDictionary.model_validate(context["data_dictionary"])
    result = [dict(field) for field in schema]
    identities = [_identities(field, context, file_name, parser or {}) for field in result]
    assigned: set[int] = set()
    for entry in dictionary.fields:
        source_files = [item for item in context.get("source_files") or [] if item.get("name") == entry.source_table]
        if len(source_files) > 1:
            raise ValueError(f"The guide file name {entry.source_table} belongs to more than one upload. Use distinct original file names.")
        matches = []
        scopes = set()
        for index, candidates in enumerate(identities):
            matching = [identity for identity in candidates
                        if identity["source_table"] == entry.source_table
                        and identity["source_column"] == entry.source_column
                        and (entry.source_sheet is None or identity["source_sheet"] == entry.source_sheet)
                        and (entry.source_role is None or identity["source_role"] == entry.source_role)]
            if not matching:
                continue
            if len(matching) != len(candidates):
                raise ValueError(f"The guide for {entry.source_table} / {entry.source_column} matches only part of a combined field. Give each source a separate field.")
            if len({(identity["source_sheet"], identity["source_role"]) for identity in matching}) > 1:
                raise ValueError(f"The guide field {entry.source_table} / {entry.source_column} contains more than one source role or sheet. Keep those fields separate before adding their definitions.")
            for identity in matching:
                scopes.add((identity["source_table"], identity["source_sheet"], identity["source_file_id"]))
            matches.append((index, matching[0]))
        if not matches:
            raise ValueError(f"The guide field {entry.source_table} / {entry.source_column} does not match an original source field. Check its file name, sheet, column and role.")
        if len(scopes) != 1:
            raise ValueError(f"The guide field {entry.source_table} / {entry.source_column} is ambiguous. Specify its sheet and use distinct original file names.")
        for index, identity in matches:
            if index in assigned:
                raise ValueError(f"More than one guide entry defines {entry.source_table} / {entry.source_column}. Keep one definition for each source field and role.")
            assigned.add(index)
            field = result[index]
            keys = [_value_key(field, value.value) for value in entry.values]
            if len(keys) != len(set(keys)):
                raise ValueError(f"The guide for {entry.source_column} gives more than one meaning to the same recorded code.")
            labels = [value.label.strip().casefold() for value in entry.values]
            if len(labels) != len(set(labels)):
                raise ValueError(f"The guide for {entry.source_column} uses one label for different recorded codes. Give each code a distinct label.")
            if entry.time_basis and not field.get("is_numeric"):
                raise ValueError(f"Relative days need a numeric source field. {entry.source_column} is not numeric.")
            definition = entry.model_dump(mode="json", exclude_none=True, exclude={"values"})
            definition.update({key: value for key, value in identity.items() if value is not None and key != "source_file_id"})
            definition.update(value_labels=[value.model_dump(mode="json") for value in entry.values],
                              numeric_values=bool(field.get("is_numeric")), provenance="owner_supplied")
            field["data_definition"] = definition
            if entry.label:
                field["display_label"] = entry.label
            if entry.description:
                field["display_description"] = entry.description
            if entry.time_basis:
                field["is_date"] = False
                field["semantic_type"] = "relative_day"
                field["analysis_role"] = "attribute"
                origin_note = f"Days from {entry.time_basis.origin}. Day 0 is the starting day."
                field["display_description"] = " ".join(filter(None, [entry.description, origin_note]))
    return result
