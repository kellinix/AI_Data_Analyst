from __future__ import annotations

"""
Hybrid semantic wrangling.

Deterministic cleaning handles structure. This service handles human-language
messiness: category aliases and display names for terse database headers.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

client = AsyncOpenAI(api_key=settings.openai_api_key)


CATEGORY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "u_s": "United States",
    "u_s_a": "United States",
    "unitedstates": "United States",
    "united_states": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u_k": "United Kingdom",
    "gb": "United Kingdom",
    "gbr": "United Kingdom",
    "greatbritain": "United Kingdom",
    "great_britain": "United Kingdom",
    "unitedkingdom": "United Kingdom",
    "united_kingdom": "United Kingdom",
    "uae": "United Arab Emirates",
    "u_a_e": "United Arab Emirates",
    "ny": "New York",
    "n_y": "New York",
    "nyc": "New York",
    "n_y_c": "New York",
    "newyork": "New York",
    "new_york": "New York",
    "newyorkcity": "New York",
    "new_york_city": "New York",
    "sf": "San Francisco",
    "s_f": "San Francisco",
    "sanfrancisco": "San Francisco",
    "san_francisco": "San Francisco",
    "la": "Los Angeles",
    "l_a": "Los Angeles",
    "losangeles": "Los Angeles",
    "los_angeles": "Los Angeles",
}


@dataclass(slots=True)
class SemanticWrangleResult:
    dataframe: pl.DataFrame
    report: dict[str, Any]


class SemanticWrangler:
    async def canonicalize_cleaned_file(
        self,
        *,
        parquet_path: str,
        csv_path: str,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Rewrite a cleaned dataset with semantic category canonicalization."""
        if not settings.semantic_wrangling_enabled:
            return profile

        try:
            df = pl.read_parquet(parquet_path)
            result = await self.canonicalize_categorical_values(df)
        except Exception as exc:
            logger.warning("Semantic categorical wrangling failed", exc=str(exc))
            return _attach_semantic_report(profile, {"enabled": True, "failed": str(exc)})

        if not result.report.get("changed_columns"):
            return _attach_semantic_report(profile, result.report)

        Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
        result.dataframe.write_parquet(parquet_path)
        result.dataframe.write_csv(csv_path)

        refreshed = {
            **_profile_dataframe(result.dataframe),
            "cleaned_parquet_path": parquet_path,
            "cleaned_csv_path": csv_path,
            "cleaning_report": profile.get("cleaning_report", {}),
        }
        return _attach_semantic_report(refreshed, result.report)

    async def canonicalize_categorical_values(self, df: pl.DataFrame) -> SemanticWrangleResult:
        """Merge likely equivalent category labels in low-cardinality columns."""
        report: dict[str, Any] = {
            "enabled": True,
            "method": "normalization+embeddings"
            if settings.semantic_wrangling_use_embeddings
            else "normalization",
            "changed_columns": [],
            "columns": [],
        }
        if df.is_empty():
            return SemanticWrangleResult(df, report)

        cleaned = df.clone()
        for column in _candidate_category_columns(cleaned):
            counts = _string_value_counts(cleaned[column])
            if not (2 <= len(counts) <= settings.semantic_wrangling_max_unique_values):
                continue

            mapping, clusters = await self._canonical_mapping(counts)
            if not mapping:
                continue

            cleaned = cleaned.with_columns(
                pl.col(column)
                .map_elements(
                    lambda value: mapping.get(str(value), value) if value is not None else None,
                    return_dtype=pl.String,
                )
                .alias(column)
            )
            report["changed_columns"].append(column)
            report["columns"].append(
                {
                    "column": column,
                    "merged_value_count": len(mapping),
                    "clusters": clusters[:12],
                }
            )
            if len(report["changed_columns"]) >= settings.semantic_wrangling_max_columns:
                break

        return SemanticWrangleResult(cleaned, report)

    async def _canonical_mapping(
        self,
        counts: Counter[str],
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        values = [
            value
            for value in counts
            if _safe_category_value(value)
        ]
        if len(values) < 2:
            return {}, []

        parent = {value: value for value in values}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        normalized_keys = {}
        for value in values:
            key = _semantic_key(value)
            if key in normalized_keys:
                union(value, normalized_keys[key])
            else:
                normalized_keys[key] = value

        if settings.semantic_wrangling_use_embeddings:
            vectors = await self._embed_values(values)
            if vectors:
                threshold = settings.semantic_wrangling_similarity_threshold
                for i, left in enumerate(values):
                    for right in values[i + 1:]:
                        similarity = _cosine_similarity(vectors[left], vectors[right])
                        if similarity >= threshold:
                            union(left, right)

        groups: dict[str, list[str]] = {}
        for value in values:
            groups.setdefault(find(value), []).append(value)

        mapping: dict[str, str] = {}
        clusters: list[dict[str, Any]] = []
        for group_values in groups.values():
            if len(group_values) < 2:
                continue
            canonical = _choose_canonical_value(group_values, counts)
            variants = sorted(group_values, key=lambda item: (-counts[item], item.lower()))
            for value in variants:
                if value != canonical:
                    mapping[value] = canonical
            if any(value != canonical for value in variants):
                clusters.append(
                    {
                        "canonical": canonical,
                        "values": variants,
                        "row_count": sum(counts[value] for value in variants),
                    }
                )

        return mapping, clusters

    async def _embed_values(self, values: list[str]) -> dict[str, list[float]]:
        try:
            response = await client.embeddings.create(
                model=settings.openai_embedding_model,
                input=[f"Category value: {value}" for value in values],
            )
            return {
                value: list(item.embedding)
                for value, item in zip(values, response.data, strict=False)
            }
        except Exception as exc:
            logger.warning("Embedding category values failed; using normalization only", exc=str(exc))
            return {}

    async def build_display_metadata(
        self,
        *,
        file_name: str,
        statistics: dict[str, Any],
        charts: list[dict[str, Any]],
        upload_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Use one LLM pass to decipher terse schema names into display labels."""
        fallback = _fallback_display_metadata(statistics, charts)
        if not settings.semantic_wrangling_enabled:
            return fallback

        payload = {
            "file_name": file_name,
            "data_description": (upload_context or {}).get("data_description")
            if isinstance(upload_context, dict)
            else None,
            "columns": [
                {
                    "name": column.get("name"),
                    "dtype": str(column.get("dtype")),
                    "semantic_type": column.get("semantic_type"),
                    "analysis_role": column.get("analysis_role"),
                    "sample_values": _sample_values_for_column(column.get("name"), statistics),
                }
                for column in statistics.get("schema", [])[:60]
            ],
            "charts": [
                {
                    "id": chart.get("id"),
                    "type": chart.get("type"),
                    "title": chart.get("title"),
                    "xAxis": chart.get("xAxis"),
                    "yAxis": chart.get("yAxis"),
                    "series": chart.get("series", []),
                }
                for chart in charts[:12]
            ],
        }

        prompt = (
            "Decode dataset schema labels for a business dashboard. Return JSON only. "
            "Do not invent metrics or change column keys. For each column, provide a "
            "short human label and optional description. For each chart, provide a "
            "clear title and description using the decoded labels."
        )

        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.1,
                max_tokens=min(settings.openai_max_tokens, 2048),
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            metadata = json.loads(content)
            return _merge_display_metadata(fallback, metadata)
        except Exception as exc:
            logger.warning("Semantic display metadata generation failed", exc=str(exc))
            return fallback


def apply_display_metadata_to_statistics(
    statistics: dict[str, Any],
    display_metadata: dict[str, Any],
) -> dict[str, Any]:
    labels = _column_labels(display_metadata)
    schema = []
    for column in statistics.get("schema", []):
        name = column.get("name")
        label = labels.get(name)
        schema.append(
            {
                **column,
                "display_label": label or _humanize_identifier(str(name)),
                "display_description": _column_descriptions(display_metadata).get(name),
            }
        )
    return {**statistics, "schema": schema, "semantic_display": display_metadata}


def apply_display_metadata_to_charts(
    charts: list[dict[str, Any]],
    display_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    labels = _column_labels(display_metadata)
    chart_overrides = {
        str(item.get("id")): item
        for item in display_metadata.get("charts", [])
        if isinstance(item, dict) and item.get("id")
    }
    updated = []
    for chart in charts:
        override = chart_overrides.get(str(chart.get("id")), {})
        chart_copy = {
            **chart,
            "title": override.get("title") or _friendly_chart_title(chart, labels),
            "description": override.get("description") or chart.get("description"),
        }
        opt = dict(chart_copy.get("echarts_option") or {})
        if isinstance(opt.get("xAxis"), dict) and chart.get("xAxis"):
            opt["xAxis"] = {**opt["xAxis"], "name": labels.get(chart["xAxis"], chart["xAxis"])}
        if isinstance(opt.get("yAxis"), dict) and chart.get("yAxis"):
            opt["yAxis"] = {**opt["yAxis"], "name": labels.get(chart["yAxis"], chart["yAxis"])}
        if isinstance(opt.get("series"), list):
            opt["series"] = [
                {
                    **series,
                    "name": labels.get(str(series.get("name")), series.get("name")),
                }
                if isinstance(series, dict)
                else series
                for series in opt["series"]
            ]
        chart_copy["echarts_option"] = opt
        updated.append(chart_copy)
    return updated


def _candidate_category_columns(df: pl.DataFrame) -> list[str]:
    candidates = []
    for column in df.columns:
        if df[column].dtype != pl.String:
            continue
        normalized = _semantic_key(column)
        if (
            normalized == "id"
            or normalized.endswith("id")
            or "description" in normalized
            or "summary" in normalized
            or "email" in normalized
            or "phone" in normalized
        ):
            continue
        try:
            unique_count = df[column].n_unique()
        except Exception:
            continue
        if 2 <= unique_count <= settings.semantic_wrangling_max_unique_values:
            candidates.append(column)
    return candidates[: settings.semantic_wrangling_max_columns * 2]


def _string_value_counts(series: pl.Series) -> Counter[str]:
    values = [
        str(value).strip()
        for value in series.drop_nulls().to_list()
        if str(value).strip()
    ]
    return Counter(values)


def _safe_category_value(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < 2 or len(stripped) > 80:
        return False
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", stripped):
        return False
    if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", stripped):
        return False
    return True


def _semantic_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    compact = normalized.replace("_", "")
    return CATEGORY_ALIASES.get(normalized) or CATEGORY_ALIASES.get(compact) or compact


def _choose_canonical_value(values: list[str], counts: Counter[str]) -> str:
    for value in values:
        key = _semantic_key(value)
        if key in set(CATEGORY_ALIASES.values()):
            return key
        alias = CATEGORY_ALIASES.get(key)
        if alias:
            return alias
    return max(values, key=lambda value: (counts[value], " " in value, len(value)))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _attach_semantic_report(profile: dict[str, Any], semantic_report: dict[str, Any]) -> dict[str, Any]:
    report = dict(profile.get("cleaning_report") or {})
    report["semantic_wrangling"] = semantic_report
    if semantic_report.get("changed_columns"):
        steps = list(report.get("steps") or [])
        if "semantic_categorical_merging" not in steps:
            steps.append("semantic_categorical_merging")
        report["steps"] = steps
    return {**profile, "cleaning_report": report}


def _profile_dataframe(df: pl.DataFrame) -> dict[str, Any]:
    columns = []
    for column in df.columns:
        series = df[column]
        columns.append(
            {
                "name": column,
                "dtype": str(series.dtype),
                "non_null_count": len(series) - series.null_count(),
                "null_count": series.null_count(),
                "unique_count": series.n_unique(),
                "sample_values": [str(value) for value in series.drop_nulls().head(5).to_list()],
            }
        )
    return {"row_count": df.height, "column_count": len(df.columns), "columns": columns}


def _fallback_display_metadata(
    statistics: dict[str, Any],
    charts: list[dict[str, Any]],
) -> dict[str, Any]:
    columns = [
        {
            "name": column.get("name"),
            "label": _humanize_identifier(str(column.get("name"))),
            "description": None,
        }
        for column in statistics.get("schema", [])
    ]
    labels = {item["name"]: item["label"] for item in columns}
    return {
        "columns": columns,
        "charts": [
            {
                "id": chart.get("id"),
                "title": _friendly_chart_title(chart, labels),
                "description": chart.get("description"),
            }
            for chart in charts
        ],
    }


def _merge_display_metadata(
    fallback: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    columns_by_name = {
        str(item.get("name")): item
        for item in fallback.get("columns", [])
        if isinstance(item, dict) and item.get("name")
    }
    for item in metadata.get("columns", []):
        if isinstance(item, dict) and item.get("name"):
            name = str(item["name"])
            columns_by_name[name] = {
                **columns_by_name.get(name, {"name": name}),
                "label": str(item.get("label") or columns_by_name.get(name, {}).get("label") or name),
                "description": item.get("description"),
            }

    charts_by_id = {
        str(item.get("id")): item
        for item in fallback.get("charts", [])
        if isinstance(item, dict) and item.get("id")
    }
    for item in metadata.get("charts", []):
        if isinstance(item, dict) and item.get("id"):
            chart_id = str(item["id"])
            charts_by_id[chart_id] = {
                **charts_by_id.get(chart_id, {"id": chart_id}),
                "title": item.get("title") or charts_by_id.get(chart_id, {}).get("title"),
                "description": item.get("description") or charts_by_id.get(chart_id, {}).get("description"),
            }

    return {"columns": list(columns_by_name.values()), "charts": list(charts_by_id.values())}


def _column_labels(display_metadata: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("name")): str(item.get("label"))
        for item in display_metadata.get("columns", [])
        if isinstance(item, dict) and item.get("name") and item.get("label")
    }


def _column_descriptions(display_metadata: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("name")): str(item.get("description"))
        for item in display_metadata.get("columns", [])
        if isinstance(item, dict) and item.get("name") and item.get("description")
    }


def _sample_values_for_column(name: Any, statistics: dict[str, Any]) -> list[str]:
    if not name:
        return []
    cat = statistics.get("categorical_stats", {}).get(str(name), {})
    return [str(item.get("value")) for item in cat.get("top_values", [])[:5]]


def _friendly_chart_title(chart: dict[str, Any], labels: dict[str, str]) -> str:
    chart_type = chart.get("type")
    x_axis = chart.get("xAxis")
    y_axis = chart.get("yAxis")
    x_label = labels.get(x_axis, _humanize_identifier(str(x_axis))) if x_axis else None
    y_label = labels.get(y_axis, _humanize_identifier(str(y_axis))) if y_axis else None

    if chart_type == "bar" and x_label and y_label:
        return f"{x_label} by {y_label}"
    if chart_type == "line" and x_label and y_label:
        if len(chart.get("series", [])) > 1:
            return "Key Metrics Over Time"
        return f"{y_label} Over Time" if "time" in x_label.lower() or "date" in x_label.lower() else f"{y_label} by {x_label}"
    if chart_type == "donut" and chart.get("series"):
        return f"{labels.get(chart['series'][0], _humanize_identifier(str(chart['series'][0])))} Distribution"
    if chart_type == "scatter" and x_label and y_label:
        return f"{x_label} vs {y_label}"
    if chart_type == "histogram" and x_label:
        return f"{x_label} Distribution"
    return str(chart.get("title") or "Chart")


def _humanize_identifier(value: str) -> str:
    text = re.sub(r"[_\s]+", " ", value).strip()
    if not text or text.lower() == "none":
        return ""
    replacements = {
        "pct": "%",
        "usd": "USD",
        "gbp": "GBP",
        "eur": "EUR",
        "id": "ID",
        "q1": "Q1",
        "q2": "Q2",
        "q3": "Q3",
        "q4": "Q4",
        "rd": "R&D",
    }
    words = [replacements.get(word.lower(), word.capitalize()) for word in text.split()]
    return " ".join(words)
