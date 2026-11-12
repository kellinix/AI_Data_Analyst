"""Conservative transaction/lookup enrichment with an auditable record grain."""
from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path
from typing import Any

import polars as pl

from app.analytics.identifier_names import canonical_identifier_name

KeyLink = tuple[tuple[str, ...], tuple[str, ...]]
_GENERIC_KEYS = {"id", "key", "code", "uuid", "guid"}
_ENTITY_KEYS = {"store", "branch", "shop", "dept", "department"}


def _bare_name(column: str) -> str:
    return re.sub(r"[^a-z0-9]", "", column.casefold())


def _unique_bare_names(frame: pl.DataFrame) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for column in frame.columns:
        grouped.setdefault(_bare_name(column), []).append(column)
    return {name: columns[0] for name, columns in grouped.items() if len(columns) == 1}


def _identifier_columns(frame: pl.DataFrame) -> dict[str, str]:
    names: dict[str, list[str]] = {}
    for column in frame.columns:
        name = canonical_identifier_name(column)
        if name:
            names.setdefault(name, []).append(column)
    return {name: columns[0] for name, columns in names.items() if len(columns) == 1}


def _key(frame: pl.DataFrame, column: str) -> pl.Series:
    # Keep case and leading zeroes. Only surrounding whitespace is insignificant.
    values = frame[column].cast(pl.String).str.strip_chars()
    return values.replace(["", r"\N"], None)


def _keys(frame: pl.DataFrame, columns: tuple[str, ...]) -> pl.DataFrame:
    return pl.DataFrame({f"key_{index}": _key(frame, column)
                         for index, column in enumerate(columns)})


def _table_entities(name: str) -> set[str]:
    stem = re.sub(r"([a-z])([A-Z])", r"\1_\2", Path(name).stem).lower()
    words = re.findall(r"[a-z0-9]+", stem)
    if words and words[-1].isdigit():
        words.pop()
    if not words:
        return set()
    variants = {words[-1]}
    if words[-1].endswith("ies"):
        variants.add(words[-1][:-3] + "y")
    if words[-1].endswith("s") and not words[-1].endswith("ss"):
        variants.add(words[-1][:-1])
    if words[-1].endswith(("ches", "shes", "sses", "xes", "zes")):
        variants.add(words[-1][:-2])
    return variants | {"".join([*words[:-1], word]) for word in variants}


def _valid_link(fact: pl.DataFrame, lookup: pl.DataFrame, link: KeyLink, allow_unique: bool) -> bool:
    foreign, primary = _keys(fact, link[0]), _keys(lookup, link[1])
    if any(primary.null_count().row(0)) or primary.n_unique() != primary.height:
        return False
    supplied = foreign.drop_nulls()
    matched = supplied.join(primary, on=primary.columns, how="semi")
    if not allow_unique and matched.n_unique() == matched.height:
        return False
    return matched.height > 0


def _candidate_relationships(
    fact: pl.DataFrame, lookup: pl.DataFrame, *, allow_unique: bool = False, lookup_name: str = "",
) -> list[KeyLink]:
    left, right = _identifier_columns(fact), _identifier_columns(lookup)
    pairs = [(left[name], right[name]) for name in sorted((left.keys() & right.keys()) - _GENERIC_KEYS)]
    pairs.extend((foreign, primary) for name, foreign in left.items()
                 for parent, primary in right.items()
                 if parent not in _GENERIC_KEYS and name != parent and name.endswith(parent)
                 and any(parent.endswith(marker) for marker in _GENERIC_KEYS))
    entities = _table_entities(lookup_name)
    # A bare parent ID needs its table name. Independent sequential row IDs
    # from two unrelated tables must never become a relationship by overlap.
    for marker in sorted(right.keys() & _GENERIC_KEYS):
        pairs.extend((column, right[marker]) for name, column in left.items()
                     if name not in _GENERIC_KEYS and name.endswith(marker)
                     and any(name[:-len(marker)].endswith(entity) for entity in entities))
        # Exports often call the child field PATIENT and the parent field Id.
        # Require the parent filename to name that exact entity; value overlap
        # alone must never link unrelated sequential IDs.
        pairs.extend((column, right[marker]) for column in fact.columns
                     if _bare_name(column) in entities)
    left_bare = _unique_bare_names(fact)
    right_bare = _unique_bare_names(lookup)
    pairs.extend((left_bare[name], right_bare[name])
                 for name in sorted(left_bare.keys() & right_bare.keys() & _ENTITY_KEYS))
    pairs = list(dict.fromkeys(pairs))
    singles = [((foreign,), (primary,)) for foreign, primary in pairs]
    candidates = [link for link in singles if _valid_link(fact, lookup, link, allow_unique)]
    # Search only minimal composite identifier keys. Never build a key from
    # arbitrary descriptive values just because their combination is unique.
    unique_parent_columns = {link[1][0] for link in singles
                             if _valid_link(fact, lookup, link, True)}
    remaining = [pair for pair in pairs if pair[1] not in unique_parent_columns]
    entity_pairs = set(remaining)
    # A dated entity table may need Store+Date, not Store alone. Dates can
    # extend a named entity key, never establish an unrelated link by themselves.
    if remaining:
        for name in sorted(left_bare.keys() & right_bare.keys() & {"date", "week", "period", "timestamp"}):
            foreign, primary = left_bare[name], right_bare[name]
            values = _key(lookup, primary).drop_nulls()
            if values.len() and values.str.contains(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?$").all():
                remaining.append((foreign, primary))
    if len(remaining) <= 8:
        for size in (2, 3):
            for selected in combinations(remaining, size):
                if not any(pair in entity_pairs for pair in selected):
                    continue
                if len({pair[0] for pair in selected}) != size or len({pair[1] for pair in selected}) != size:
                    continue
                link = (tuple(pair[0] for pair in selected), tuple(pair[1] for pair in selected))
                if any(set(existing[0]) <= set(link[0]) and set(existing[1]) <= set(link[1])
                       for existing in candidates):
                    continue
                if _valid_link(fact, lookup, link, allow_unique):
                    candidates.append(link)
    return candidates


def _role_prefix(link: KeyLink, lookup_name: str) -> str | None:
    prefixes = set()
    entities = _table_entities(lookup_name)
    for foreign, primary in zip(*link, strict=True):
        child, parent = canonical_identifier_name(foreign), canonical_identifier_name(primary)
        if not child or not parent:
            continue
        if child == parent:
            continue
        if child.endswith(parent) and parent not in _GENERIC_KEYS:
            prefixes.add(child[:-len(parent)])
        elif parent in _GENERIC_KEYS and child.endswith(parent):
            base = child[:-len(parent)]
            matches = [entity for entity in entities if base.endswith(entity)]
            if matches:
                prefixes.add(base[:-len(max(matches, key=len))])
    prefixes.discard("")
    return next(iter(prefixes)) if len(prefixes) == 1 else None


def _role_label(link: KeyLink) -> str:
    foreign = next((foreign for foreign, primary in zip(*link, strict=True)
                    if canonical_identifier_name(foreign) != canonical_identifier_name(primary)), link[0][0])
    column = re.sub(r"([a-z])([A-Z])", r"\1 \2", foreign)
    column = re.sub(r"[_\s]+", " ", column).strip()
    column = re.sub(r"(?i)\s*(?:id|key|code|uuid|guid)$", "", column).strip()
    return re.sub(r"(?i)^(?:id|key|code|uuid|guid)\s+", "", column) or foreign


def _separate_roles(candidates: list[KeyLink], lookup_name: str, declared: bool) -> bool:
    if len(candidates) < 2:
        return False
    foreign = [frozenset(link[0]) for link in candidates]
    if len(set(foreign)) != len(foreign):
        return False
    if declared:
        return True
    primary = {frozenset(link[1]) for link in candidates}
    prefixes = [_role_prefix(link, lookup_name) for link in candidates]
    return len(primary) == 1 and any(prefixes) and len(set(prefixes)) == len(prefixes)


def _relationship(fact: pl.DataFrame, lookup: pl.DataFrame, *, allow_unique: bool = False, lookup_name: str = "") -> KeyLink | None:
    candidates = _candidate_relationships(fact, lookup, allow_unique=allow_unique, lookup_name=lookup_name)
    return candidates[0] if len(candidates) == 1 else None


def _conflicting_identifier_associations(
    fact: pl.DataFrame, lookup: pl.DataFrame, candidates: list[KeyLink],
) -> bool:
    left = pl.DataFrame({f"foreign_{index}_{part}": _key(fact, column)
                         for index, (columns, _) in enumerate(candidates) for part, column in enumerate(columns)})
    right = pl.DataFrame({f"primary_{index}_{part}": _key(lookup, column)
                          for index, (_, columns) in enumerate(candidates) for part, column in enumerate(columns)})
    for index in range(len(candidates)):
        left_keys = [f"foreign_{index}_{part}" for part in range(len(candidates[index][0]))]
        right_keys = [f"primary_{index}_{part}" for part in range(len(candidates[index][1]))]
        matched = left.join(right, left_on=left_keys, right_on=right_keys,
                            how="inner", validate="m:1", coalesce=False)
        for other in range(len(candidates)):
            for part in range(len(candidates[other][0])):
                if not matched[f"foreign_{other}_{part}"].eq_missing(matched[f"primary_{other}_{part}"]).all():
                    return True
    return False


def _reachable(graph: dict, root: int) -> set[int]:
    found, pending = {root}, [root]
    while pending:
        for parent in graph[pending.pop()]:
            if parent not in found:
                found.add(parent)
                pending.append(parent)
    return found


def _inherit_field_origin(
    origin: dict, column: str, source_origins: list[dict], renames: dict[str, str], combined: pl.DataFrame,
) -> dict:
    inherited = [origins[column] for origins in source_origins if isinstance(origins.get(column), dict)]
    if not inherited:
        return origin
    sources = []
    for previous in inherited:
        for source in previous.get("source_origins") or [previous]:
            mapped = {**source, "entity_key_columns": [renames.get(key, key)
                      for key in source.get("entity_key_columns", [])]}
            if mapped not in sources:
                sources.append(mapped)
    result = {**origin, **sources[0]} if len(sources) == 1 else {
        **origin, "source_table": "Multiple source tables", "source_origins": sources,
        "entity_key_columns": [], "key_basis": "multiple_sources",
    }
    if all(source.get("kind") == "fact" for source in sources):
        result["entity_key_columns"] = origin["entity_key_columns"]
        if origin.get("key_basis"):
            result["key_basis"] = origin["key_basis"]
    result["kind"] = "lookup" if origin["kind"] == "lookup" or any(
        item.get("kind") == "lookup" for item in inherited) else "fact"
    result["repeated"] = origin["repeated"] or any(item.get("repeated") is True for item in inherited)
    keys = result.get("entity_key_columns") or []
    if keys and any(item.get("kind") == "lookup" for item in inherited) and all(key in combined.columns for key in keys):
        represented = _keys(combined, tuple(keys)).drop_nulls()
        result["matched_entries"] = represented.height
        result["repeated"] = result["repeated"] or represented.height > represented.n_unique()
    return result


def _parent_rows(combined: pl.DataFrame, foreign: tuple[str, ...], lookup: pl.DataFrame,
                 primary: tuple[str, ...]) -> list[int | None]:
    parents = {key: index for index, key in enumerate(_keys(lookup, primary).iter_rows())}
    return [parents.get(key) if all(value is not None for value in key) else None
            for key in _keys(combined, foreign).iter_rows()]


def _attach_role_lookup(combined, lookup, foreign_columns, primary_columns, table_number, role_label):
    foreign, primary = _keys(combined, foreign_columns), _keys(lookup, primary_columns)
    matched = foreign.join(primary, on=primary.columns, how="semi").height
    unused = primary.join(foreign.drop_nulls().unique(), on=primary.columns, how="anti").height
    payload = lookup.drop("Source file") if "Source file" in lookup.columns else lookup
    used = set(combined.columns) | set(payload.columns)
    renames = {}
    for column in payload.columns:
        replacement = f"{role_label} {column}" if role_label else column
        if replacement in combined.columns:
            replacement = f"{replacement} related {table_number}"
        while replacement in used and replacement != column:
            replacement += "_"
        if replacement != column:
            renames[column] = replacement
            used.add(replacement)
    key_names = []
    for part in range(len(primary_columns)):
        key = f"__relationship_key_{part}"
        while key in used:
            key += "_"
        used.add(key)
        key_names.append(key)
    payload = payload.rename(renames).with_columns([primary[name].alias(key)
        for name, key in zip(primary.columns, key_names, strict=True)])
    result = combined.with_columns([foreign[name].alias(key)
        for name, key in zip(foreign.columns, key_names, strict=True)]).join(
            payload, on=key_names, how="left", validate="m:1", maintain_order="left",
        ).drop(key_names)
    if result.height != combined.height:
        raise ValueError("A lookup relationship changed the main table's record count.")
    return result, renames, matched, unused


def _enrich_role_paths(tables, names, origins, frames, graph, constraints, role_links, declared, root):
    combined = tables[root]
    field_origins = {column: _inherit_field_origin({"source_table": names[root], "source_column": column,
        "kind": "fact", "repeated": False, "entity_key_columns": []}, column, origins[root], {}, combined)
        for column in combined.columns if column != "Source file"}
    instances = [{"table": root, "role": (), "labels": (), "path": [], "ancestors": (root,),
                  "fields": {column: column for column in combined.columns}, "rows": list(range(combined.height))}]
    resolution = {"status": "enriched", "grain": "One entry per record in the main source table",
        "fact_files": combined["Source file"].unique(maintain_order=True).to_list() if "Source file" in combined.columns else [],
        "input_rows": sum(frame.height for frame in frames), "row_count": combined.height, "joins": []}

    def target_role(instance, parent, link):
        child = instance["table"]
        label = _role_label(link) if (child, parent) in role_links else ""
        if label:
            slug = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
            return (*instance["role"], slug), (*instance["labels"], label)
        if instance["role"]:
            return instance["role"], instance["labels"]
        incoming = [index for index in graph if parent in graph[index]]
        if len(incoming) > 1 and parent not in graph[root] and child != root:
            label = Path(names[child]).stem
            slug = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
            return (slug,), (label,)
        return (), ()

    def matching_ancestor(instance, parent, rows):
        return any(node["table"] == parent and node["rows"] == rows
                   and node["path"] == instance["path"][:len(node["path"])] for node in instances)

    cursor = 0
    while cursor < len(instances):
        instance = instances[cursor]
        cursor += 1
        child = instance["table"]
        for parent, selected in graph[child].items():
            for link in role_links.get((child, parent), [selected]):
                role, labels = target_role(instance, parent, link)
                foreign = tuple(instance["fields"][column] for column in link[0])
                represented_rows = _parent_rows(combined, foreign, tables[parent], link[1])
                if parent in instance["ancestors"] and matching_ancestor(instance, parent, represented_rows):
                    continue
                existing = [node for node in instances if node["table"] == parent and node["role"] == role]
                if existing:
                    if any(node["rows"] != represented_rows for node in existing):
                        return None, {"status": "unresolved", "reason_code": "conflicting_identifiers",
                            "reason": "The identifier links disagree about which rows belong together. Choose the intended relationship before combining these files."}
                    continue
                if parent in instance["ancestors"]:
                    return None, {"status": "unresolved", "reason_code": "ambiguous_relationship_graph",
                        "reason": "These lookup paths form a cycle. Choose a main table and separate lookup roles."}
                path = [*instance["path"], {"from_table": names[child], "from_columns": list(link[0]),
                    "to_table": names[parent], "to_columns": list(link[1])}]
                role_label = " / ".join(labels)
                combined, renames, matched, unused = _attach_role_lookup(
                    combined, tables[parent], foreign, link[1], parent + 1, role_label)
                fields = {column: renames.get(column, column) for column in tables[parent].columns if column != "Source file"}
                entity_keys = [fields[column] for column in link[1]]
                represented = _keys(combined, tuple(entity_keys)).drop_nulls()
                repeated = represented.height > represented.n_unique()
                source_role = "/".join(role) or None
                for column, output in fields.items():
                    origin = _inherit_field_origin({"source_table": names[parent], "source_column": column,
                        "kind": "lookup", "entity_key_columns": entity_keys, "key_basis": "parent_primary",
                        "repeated": repeated, "matched_entries": matched, "source_rows": tables[parent].height},
                        column, origins[parent], renames, combined)
                    inherited_role = origin.get("source_role")
                    inherited_label = origin.get("source_role_label")
                    field_origins[output] = {**origin,
                        "source_role": "/".join(part for part in [source_role, inherited_role] if part) or None,
                        "source_role_label": " / ".join(part for part in [role_label, inherited_label] if part) or None,
                        "relationship_path": [*path, *(origin.get("relationship_path") or [])]}
                instances.append({"table": parent, "role": role, "labels": labels, "path": path,
                    "ancestors": (*instance["ancestors"], parent), "fields": fields, "rows": represented_rows})
                files = tables[parent]["Source file"].unique(maintain_order=True).to_list() if "Source file" in tables[parent].columns else [names[parent]]
                resolution["joins"].append({"foreign_key": foreign[0] if len(foreign) == 1 else list(foreign),
                    "lookup_key": link[1][0] if len(link[1]) == 1 else list(link[1]),
                    "foreign_keys": list(foreign), "lookup_keys": list(link[1]), "lookup_files": files,
                    "lookup_rows": tables[parent].height, "matched_entries": matched,
                    "unmatched_entries": combined.height - matched, "lookup_only_entries": unused,
                    "renamed_fields": renames, "declared": (child, parent) in declared,
                    "source_role": source_role, "source_role_label": role_label or None, "relationship_path": path})
    for instance in instances:
        child = instance["table"]
        for (source, parent), links in constraints.items():
            if source != child or (child, parent) in role_links:
                continue
            for link in links:
                role, _labels = target_role(instance, parent, link)
                targets = [node for node in instances if node["table"] == parent and node["role"] == role]
                foreign = tuple(instance["fields"][column] for column in link[0])
                rows = _parent_rows(combined, foreign, tables[parent], link[1])
                if matching_ancestor(instance, parent, rows):
                    continue
                if not targets or any(node["rows"] != rows for node in targets):
                    return None, {"status": "unresolved", "reason_code": "conflicting_identifiers",
                        "reason": "The identifier links disagree about which rows belong together. Choose the intended relationship before combining these files."}
    if {node["table"] for node in instances} != set(range(len(tables))):
        return None, {"status": "unresolved", "reason_code": "ambiguous_relationship_graph",
            "reason": "Some tables have no verified lookup path from the main table."}
    resolution["field_origins"] = field_origins
    return combined, resolution


def enrich_related_files(
    frames: list[pl.DataFrame], *, table_names: list[str] | None = None,
    table_ids: list[str] | None = None, declared_relationships: list[dict] | None = None,
    fact_table: str | None = None, table_origins: list[dict] | None = None,
) -> tuple[pl.DataFrame | None, dict[str, Any]]:
    """Join only a single unambiguous fact table to unique-key lookup tables.

    Same-schema files are partitions of the same record type. Unrelated or
    ambiguous tables retain the caller's portfolio behaviour with a limitation.
    No fact aggregation, inner joins or many-to-many expansion is permitted.
    """
    partitions: dict[tuple[str, ...], list[pl.DataFrame]] = {}
    partition_names: dict[tuple[str, ...], list[str]] = {}
    partition_origins: dict[tuple[str, ...], list[dict]] = {}
    original_tables = {}
    for original, frame in enumerate(frames):
        signature = tuple(sorted(c for c in frame.columns if c != "Source file"))
        original_tables[original] = list(partitions).index(signature) if signature in partitions else len(partitions)
        partitions.setdefault(signature, []).append(frame)
        inferred = frame["Source file"][0] if "Source file" in frame.columns and frame.height else f"Table {original + 1}"
        partition_names.setdefault(signature, []).append(table_names[original] if table_names else str(inferred))
        supplied_origins = table_origins[original] if table_origins else {}
        partition_origins.setdefault(signature, []).append({column: {
            "source_table": partition_names[signature][-1], "source_column": column,
            "kind": "fact", "repeated": False, "entity_key_columns": [], **supplied_origins.get(column, {}),
        } for column in frame.columns if column != "Source file"})
    tables = [pl.concat(group, how="diagonal_relaxed") for group in partitions.values()]
    names = [values[0] for values in partition_names.values()]
    origins = list(partition_origins.values())
    if len(tables) < 2:
        if declared_relationships:
            return None, {"status": "unresolved", "reason_code": "invalid_declared_relationship",
                "reason": "Choose relationships between different record types. Files with the same fields are parts of one table."}
        field_origins = {column: _inherit_field_origin({"source_table": names[0], "source_column": column,
            "kind": "fact", "repeated": False, "entity_key_columns": []}, column, origins[0], {}, tables[0])
            for column in tables[0].columns if column != "Source file"} if tables else {}
        return None, {"status": "stacked", "reason": "Files have the same fields and were appended.",
                      "field_origins": field_origins}

    declared = {}
    declared_root = None
    if declared_relationships or fact_table:
        try:
            references = {}
            for original in range(len(frames)):
                reference = str(table_ids[original]) if table_ids else str(original)
                if reference in references:
                    raise ValueError("Source file references must be unique.")
                references[reference] = original_tables[original]
            if fact_table is not None:
                declared_root = references[str(fact_table)]
            if not isinstance(declared_relationships or [], list) or len(declared_relationships or []) > 16:
                raise ValueError("Choose at most sixteen relationships.")
            for item in declared_relationships or []:
                child, parent = references[str(item["from_file"])], references[str(item["to_file"])]
                foreign, primary = item["from_columns"], item["to_columns"]
                if (child == parent or not isinstance(foreign, list) or not isinstance(primary, list)
                        or not 1 <= len(foreign) == len(primary) <= 3
                        or len(set(foreign)) != len(foreign) or len(set(primary)) != len(primary)
                        or any(not isinstance(column, str) or column not in tables[child].columns for column in foreign)
                        or any(not isinstance(column, str) or column not in tables[parent].columns for column in primary)):
                    raise ValueError("Choose existing columns from two different tables.")
                link = (tuple(foreign), tuple(primary))
                if not _valid_link(tables[child], tables[parent], link, True):
                    raise ValueError("The parent keys must be unique, filled in and match source records.")
                links = declared.setdefault((child, parent), [])
                if any(existing[0] == link[0] and existing != link for existing in links):
                    raise ValueError("Different lookup roles need different source key columns.")
                if link not in links:
                    links.append(link)
            declared_graph = {index: {} for index in range(len(tables))}
            for child, parent in declared:
                declared_graph[child][parent] = True
            if any(child in _reachable(declared_graph, parent) for child, parent in declared):
                raise ValueError("Relationships cannot form a cycle. Choose a main table and its lookup tables.")
        except (KeyError, TypeError, ValueError) as error:
            return None, {"status": "unresolved", "reason_code": "invalid_declared_relationship", "reason": str(error)}

    graph = {}
    constraints = {}
    role_links = {}
    for index, fact in enumerate(tables):
        graph[index] = {}
        for other, lookup in enumerate(tables):
            if other != index:
                if (index, other) in declared:
                    candidates = declared[index, other]
                elif (other, index) in declared:
                    continue
                else:
                    candidates = _candidate_relationships(fact, lookup, allow_unique=True, lookup_name=names[other])
                separate_roles = _separate_roles(candidates, names[other], (index, other) in declared)
                if len(candidates) > 1 and not separate_roles and _conflicting_identifier_associations(fact, lookup, candidates):
                    return None, {
                        "status": "unresolved", "reason_code": "conflicting_identifiers",
                        "reason": "The identifier links disagree about which rows belong together. Choose the intended relationship before combining these files.",
                    }
                if candidates:
                    constraints[index, other] = candidates
                if separate_roles or (len(candidates) == 1 and _role_prefix(candidates[0], names[other])):
                    role_links[index, other] = candidates
                if len(candidates) == 1 or separate_roles:
                    graph[index][other] = candidates[0]
    # A repeated foreign key establishes the transaction side. One-to-one
    # lookup links can then extend that known grain without choosing a new one.
    roots = [index for index, fact in enumerate(tables)
             if _reachable(graph, index) == set(range(len(tables)))
             and (index == declared_root or any(_valid_link(fact, tables[parent], candidate, False)
                 for parent, link in graph[index].items() for candidate in role_links.get((index, parent), [link])))]
    if declared_root is not None:
        roots = [root for root in roots if root == declared_root]
    if len(roots) != 1:
        return None, {
            "status": "unresolved",
            "reason": "Different record types were appended. No unambiguous many-to-one identifier relationship connects all files. Cross-table comparisons require a verified relationship.",
        }

    index = roots[0]
    multiple_paths = any(parent not in graph[index] and sum(parent in edges for edges in graph.values()) > 1
                         for parent in range(len(tables)) if parent != index)
    if role_links or multiple_paths:
        return _enrich_role_paths(tables, names, origins, frames, graph, constraints, role_links, declared, index)
    combined = tables[index]
    attached = {index}
    field_names = {(index, column): column for column in combined.columns}
    field_origins = {column: _inherit_field_origin({"source_table": names[index], "source_column": column,
                             "kind": "fact", "repeated": False, "entity_key_columns": []},
                             column, origins[index], {}, combined)
                     for column in combined.columns if column != "Source file"}
    resolution: dict[str, Any] = {
        "status": "enriched", "grain": "One entry per record in the main source table",
        "fact_files": combined["Source file"].unique(maintain_order=True).to_list() if "Source file" in combined.columns else [],
        "input_rows": sum(len(frame) for frame in frames), "row_count": len(combined), "joins": [],
    }
    while len(attached) < len(tables):
        available = [(other, [(child, graph[child][other]) for child in sorted(attached) if other in graph[child]])
                     for other in range(len(tables)) if other not in attached]
        available = [(other, paths) for other, paths in available if paths]
        other, paths = available[0]
        child, (source_columns, primary_columns) = paths[0]
        foreign_columns = tuple(field_names[(child, column)] for column in source_columns)
        lookup = tables[other]
        foreign, primary = _keys(combined, foreign_columns), _keys(lookup, primary_columns)
        matched = foreign.join(primary, on=primary.columns, how="semi").height
        unused = primary.join(foreign.drop_nulls().unique(), on=primary.columns, how="anti").height
        key_names = []
        for part in range(len(primary_columns)):
            key_name = f"__relationship_key_{part}"
            while key_name in combined.columns or key_name in lookup.columns:
                key_name += "_"
            key_names.append(key_name)
        source_files = lookup["Source file"].unique(maintain_order=True).to_list() if "Source file" in lookup.columns else []
        payload = lookup.drop("Source file") if "Source file" in lookup.columns else lookup
        used = set(combined.columns) | set(payload.columns)
        renames = {}
        for column in payload.columns:
            if column in combined.columns:
                replacement = f"{column} related {other + 1}"
                while replacement in used:
                    replacement += "_"
                renames[column] = replacement
                used.add(replacement)
        payload = payload.rename(renames).with_columns([primary[name].alias(key_name)
            for name, key_name in zip(primary.columns, key_names, strict=True)])
        combined = combined.with_columns([foreign[name].alias(key_name)
            for name, key_name in zip(foreign.columns, key_names, strict=True)]).join(
            payload, on=key_names, how="left", validate="m:1", maintain_order="left",
        ).drop(key_names)
        field_names.update({(other, column): renames.get(column, column) for column in lookup.columns
                            if column != "Source file"})
        entity_columns = tuple(field_names[(other, column)] for column in primary_columns)
        represented = _keys(combined, entity_columns).drop_nulls()
        repeated = represented.height > represented.n_unique()
        field_origins.update({renames.get(column, column): _inherit_field_origin({
            "source_table": names[other], "source_column": column, "kind": "lookup",
            "entity_key_columns": list(entity_columns), "key_basis": "parent_primary",
            "repeated": repeated, "matched_entries": matched, "source_rows": lookup.height,
        }, column, origins[other], renames, combined) for column in lookup.columns if column != "Source file"})
        attached.add(other)
        resolution["joins"].append({
            "foreign_key": foreign_columns[0] if len(foreign_columns) == 1 else list(foreign_columns),
            "lookup_key": primary_columns[0] if len(primary_columns) == 1 else list(primary_columns),
            "foreign_keys": list(foreign_columns), "lookup_keys": list(primary_columns),
            "lookup_files": source_files, "lookup_rows": len(lookup),
            "matched_entries": matched, "unmatched_entries": len(combined) - matched,
            "lookup_only_entries": unused, "renamed_fields": renames,
            "declared": (child, other) in declared,
        })
    # Check paths that became available after a table was attached as well.
    # Input order must never decide which conflicting identifier to believe.
    # An ambiguous pair cannot choose an attachment path, but every plausible
    # identifier still constrains the finished rows if another path joined it.
    for (child, parent), links in constraints.items():
        for foreign_columns, primary_columns in links:
            for foreign_column, primary_column in zip(foreign_columns, primary_columns, strict=True):
                left = _key(combined, field_names[(child, foreign_column)])
                right = _key(combined, field_names[(parent, primary_column)])
                known = left.is_not_null() & right.is_not_null()
                if not left.filter(known).eq_missing(right.filter(known)).all():
                    return None, {"status": "unresolved", "reason_code": "conflicting_identifiers", "reason": "The identifier links disagree about which rows belong together. Choose the intended relationship before combining these files."}
    resolution["field_origins"] = field_origins
    return combined, resolution
