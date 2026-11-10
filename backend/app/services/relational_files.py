"""Conservative transaction/lookup enrichment with an auditable record grain."""
from __future__ import annotations

import re
from typing import Any

import polars as pl


def _identifier_columns(frame: pl.DataFrame) -> dict[str, str]:
    names: dict[str, list[str]] = {}
    for column in frame.columns:
        words = re.sub(r"([a-z])([A-Z])", r"\1_\2", column).lower()
        parts = re.findall(r"[a-z0-9]+", words)
        if len(parts) > 1 and parts[-1] in {"id", "key", "code"}:
            names.setdefault("".join(parts), []).append(column)
    return {name: columns[0] for name, columns in names.items() if len(columns) == 1}


def _key(frame: pl.DataFrame, column: str) -> pl.Series:
    # Keep case and leading zeroes. Only surrounding whitespace is insignificant.
    values = frame[column].cast(pl.String).str.strip_chars()
    return values.replace("", None)


def _relationship(fact: pl.DataFrame, lookup: pl.DataFrame) -> tuple[str, str] | None:
    left, right = _identifier_columns(fact), _identifier_columns(lookup)
    candidates = []
    for name in left.keys() & right.keys():
        foreign, primary = _key(fact, left[name]), _key(lookup, right[name])
        if primary.null_count() or primary.n_unique() != len(primary):
            continue
        # One-to-one and many-to-many relationships need an explicit grain choice.
        supplied = foreign.drop_nulls()
        if supplied.n_unique() == len(supplied):
            continue
        if supplied.is_in(primary.implode()).any():
            candidates.append((left[name], right[name]))
    return candidates[0] if len(candidates) == 1 else None


def enrich_related_files(frames: list[pl.DataFrame]) -> tuple[pl.DataFrame | None, dict[str, Any]]:
    """Join only a single unambiguous fact table to unique-key lookup tables.

    Same-schema files are partitions of the same record type. Unrelated or
    ambiguous tables retain the caller's portfolio behaviour with a limitation.
    No fact aggregation, inner joins or many-to-many expansion is permitted.
    """
    partitions: dict[tuple[str, ...], list[pl.DataFrame]] = {}
    for frame in frames:
        signature = tuple(sorted(c for c in frame.columns if c != "Source file"))
        partitions.setdefault(signature, []).append(frame)
    tables = [pl.concat(group, how="diagonal_relaxed") for group in partitions.values()]
    if len(tables) < 2:
        return None, {"status": "stacked", "reason": "Files have the same fields and were appended."}

    roots = []
    for index, fact in enumerate(tables):
        links = [(other, _relationship(fact, lookup)) for other, lookup in enumerate(tables) if other != index]
        if all(link is not None for _, link in links):
            roots.append((index, links))
    if len(roots) != 1:
        return None, {
            "status": "unresolved",
            "reason": "Different record types were appended. No unambiguous many-to-one identifier relationship connects all files. Cross-table comparisons require a verified relationship.",
        }

    index, links = roots[0]
    combined = tables[index]
    resolution: dict[str, Any] = {
        "status": "enriched", "grain": "One entry per source transaction",
        "fact_files": combined["Source file"].unique(maintain_order=True).to_list() if "Source file" in combined.columns else [],
        "input_rows": sum(len(frame) for frame in frames), "row_count": len(combined), "joins": [],
    }
    for other, (foreign_column, primary_column) in links:
        lookup = tables[other]
        foreign, primary = _key(combined, foreign_column), _key(lookup, primary_column)
        matched = int(foreign.is_in(primary.implode()).fill_null(False).sum())
        unused = int((~primary.is_in(foreign.drop_nulls().unique().implode())).sum())
        key_name = "__relationship_key"
        while key_name in combined.columns or key_name in lookup.columns:
            key_name += "_"
        source_files = lookup["Source file"].unique(maintain_order=True).to_list() if "Source file" in lookup.columns else []
        payload = lookup.drop([c for c in (primary_column, "Source file") if c in lookup.columns])
        used = set(combined.columns) | set(payload.columns)
        renames = {}
        for column in payload.columns:
            if column in combined.columns:
                replacement = f"{column} related {other + 1}"
                while replacement in used:
                    replacement += "_"
                renames[column] = replacement
                used.add(replacement)
        payload = payload.rename(renames).with_columns(primary.alias(key_name))
        combined = combined.with_columns(foreign.alias(key_name)).join(
            payload, on=key_name, how="left", validate="m:1", maintain_order="left",
        ).drop(key_name)
        resolution["joins"].append({
            "foreign_key": foreign_column, "lookup_key": primary_column,
            "lookup_files": source_files, "lookup_rows": len(lookup),
            "matched_entries": matched, "unmatched_entries": len(combined) - matched,
            "lookup_only_entries": unused, "renamed_fields": renames,
        })
    return combined, resolution
