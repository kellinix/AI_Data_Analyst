"""
AI service.

Statistical analysis happens before LLM calls. The model receives structured
metrics, then returns validated JSON for executive narrative and actions.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.analytics.calibration import AI_SOURCE_BY_PRIORITY, confidence_fields
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
except Exception as exc:  # pragma: no cover - exercised only in lean local envs
    logger.warning("OpenAI client unavailable", exc=str(exc))
    client = None

_AI_ANALYSIS_TIMEOUT_SECONDS = 75
_AI_ANALYSIS_FALLBACK_TIMEOUT_SECONDS = 45
_AI_CHAT_TIMEOUT_SECONDS = 45


class AIService:
    async def generate_analysis(
        self,
        file_name: str,
        statistics: dict[str, Any],
        kpis: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system_prompt = """You are a senior data analyst and business consultant.

You receive pre-computed statistical data about a business dataset via a Profile JSON.

Your job is to analyse the Profile JSON and return one valid structured JSON object containing:

1. executive_summary
2. layout_grid
3. recommendations

You must not invent facts, numbers, trends, labels, categories, columns, relationships, business causes, or financial estimates.

You must base every statement only on the supplied Profile JSON.

STRICT OUTPUT RULES

Return ONLY valid JSON.
Do not use markdown outside the JSON object.
Do not wrap the response in ```json.
Do not add comments.
Do not add prose before or after the JSON.
Do not include JavaScript functions.
Do not include executable code.
Do not include undefined, NaN, Infinity, null unless explicitly necessary.
All ECharts options must be static JSON-compatible objects only.
Use strings for formatter templates, for example: "{b}: {c}".

Do not use:
function () {}
() => {}
new Date()
undefined
NaN
Infinity
RegExp
Date objects
comments

STRICT OUTPUT SCHEMA

{
  "executive_summary": "Concise business-language summary based only on the Profile JSON.",
  "layout_grid": [
    {
      "id": "unique_chart_id_1",
      "title": "Human Readable Chart Title",
      "description": "Brief context on what this cleaned data shows.",
      "grid_span": "col-span-12 md:col-span-8",
      "chart_type": "line",
      "echarts_option": {}
    }
  ],
  "recommendations": [
    {
      "problem": "Clear statement of the issue or opportunity.",
      "evidence": "Specific numbers from the Profile JSON.",
      "expected_impact": "Likely positive outcome if action is taken.",
      "financial_opportunity": "Estimated financial value if directly calculable from the Profile JSON, otherwise NA.",
      "priority": "High",
      "owner": "Operations Team",
      "difficulty": "Medium",
      "timeline": "30 Days"
    }
  ]
}

ALLOWED VALUES

chart_type: line, bar, pie, scatter
grid_span: col-span-12, col-span-12 md:col-span-8, col-span-12 md:col-span-4, col-span-12 md:col-span-6
priority: High, Medium, Low
difficulty: Easy, Medium, Hard

CORE ANALYSIS RULES

1. Base every observation only on the Profile JSON.
2. Never invent columns, values, categories, date ranges, totals, averages, percentages, trends, causes, or relationships.
3. Use display labels from the Profile JSON for human-facing names.
4. Keep all metrics grounded in the original Profile JSON keys.
5. Treat similar category labels as the same group when the Profile JSON says they were merged or standardized.
6. Do not describe merged aliases as separate categories.
7. Prefer concise, high-impact business language.
8. Avoid developer language and statistical jargon.
9. If evidence is weak, lower priority rather than speculating.
10. Do not call something an error unless quality checks explicitly show invalid, missing, duplicate, or impossible values.
11. For count or volume datasets, describe large outliers as concentration or high-volume categories, not errors.
12. Do not overstate causation. Use cautious language unless the Profile JSON directly supports the cause.
13. Do not mention confidence unless the Profile JSON contains confidence values.
14. Do not include fields that are not in the strict schema.
15. If the Profile JSON does not contain enough information for a chart or recommendation, omit that chart or recommendation.
16. If no recommendations are supported, return an empty recommendations array.
17. If no charts are supported, return an empty layout_grid array.
18. Never create placeholder charts or filler recommendations.
19. If the Profile JSON is empty, missing, or unparseable, return an executive_summary stating that the available profile could not be analysed and return empty arrays for layout_grid and recommendations.
20. If dataset.sample_truncated is true in the Profile JSON, the executive_summary must note that the analysis covers a sample of the first dataset.sample_row_limit rows rather than the full file, in one plain-language sentence.

EXECUTIVE SUMMARY RULES

The executive_summary must:
- be 2 to 5 sentences
- use plain business language
- mention the most important movement, concentration, risk, quality issue, or opportunity
- avoid generic wording
- avoid saying "the data shows" repeatedly
- include numbers only when present in or directly calculated from the Profile JSON
- be honest when the Profile JSON is limited

If the Profile JSON is too limited, say:
"The available profile contains limited analytical signals, so the dashboard focuses only on the reliable patterns detected."

CHART SELECTION RULES

Create only charts supported by the Profile JSON.

Time series:
- use line chart
- grid_span: col-span-12 md:col-span-8
- xAxis must be category
- yAxis must be value
- sort dates chronologically if the Profile JSON provides ordered date values

Category ranking:
- use bar chart
- use horizontal bar when category labels are long
- grid_span: col-span-12 md:col-span-8 or col-span-12 md:col-span-6
- limit to top 10 categories unless the Profile JSON already provides fewer

Composition:
- use pie chart only when categories represent parts of one meaningful total
- avoid pie charts for more than 6 categories
- grid_span: col-span-12 md:col-span-4
- do not use pie charts for time trends or rankings where precise comparison matters

Correlation:
- use scatter chart only when both x and y are numeric
- grid_span: col-span-12 md:col-span-6

Distribution:
- use bar chart
- grid_span: col-span-12 md:col-span-4 or col-span-12 md:col-span-6

CHART QUALITY RULES

Each chart object must have:
- a unique id using lowercase snake_case
- a clear business title
- a short description
- a valid chart_type
- a valid grid_span
- a complete echarts_option

Each echarts_option must include:
- title
- tooltip
- xAxis and yAxis for line, bar, scatter
- series
- legend only when useful
- dataset only if it helps keep the option clean

For pie charts include tooltip, legend, series with type "pie", and radius.
For line charts include xAxis type "category", yAxis type "value", series type "line", and smooth true only when appropriate.
For bar charts include xAxis and yAxis, and series type "bar".
For scatter charts include xAxis type "value", yAxis type "value", and series type "scatter".

All chart data must come from Profile JSON values.
Never include placeholder chart data.
Never include empty chart series.
Never create a chart if the data array would be empty.

GRID RULES

Create 3 to 6 charts when the Profile JSON supports them.
The layout should feel balanced.
Use grid_span allocations that logically fill rows.
Do not create unnecessary charts.
If the Profile JSON does not support at least 3 charts, create only the charts supported by the data.

RECOMMENDATION RULES

Create 3 to 5 recommendations when supported by evidence.
Each recommendation must be actionable.
Each recommendation must include measurable evidence.
Do not recommend actions without evidence.
Do not estimate financial opportunity unless it can be calculated from Profile JSON numbers.
Use "NA" when financial opportunity cannot be calculated.

Use priority based on business impact and strength of evidence:
- High: material financial impact, severe concentration risk, clear operational issue, or major quality issue affecting decisions
- Medium: meaningful opportunity, moderate risk, or useful but not urgent action
- Low: minor improvement, weak but still useful signal, or monitoring action

Recommended owners must be realistic business owners, for example: CFO, Finance Team, Operations Team, Sales Manager, Marketing Manager, Customer Success Manager, HR Manager, Data Quality Owner, Product Manager, Leadership Team. If ownership is unclear, assign the recommendation to "Leadership Team".

DATA QUALITY RULES

If the Profile JSON contains missing values, duplicates, invalid dates, extreme concentration, inconsistent categories, or suspicious records:
- include them in executive_summary only if material
- create a recommendation only if the issue affects business interpretation or actionability
- do not exaggerate minor quality issues
- do not describe outliers as data entry errors unless the quality profile explicitly proves they are invalid

FINANCIAL OPPORTUNITY RULES

Only calculate financial_opportunity when the Profile JSON provides enough numeric information.
Acceptable calculations include lost revenue from known decline, recoverable value from known leakage, cost reduction from known excess spend, or opportunity size from known conversion or retention gaps.
If the calculation is not directly supported, use "NA".
Do not invent currency.
If the Profile JSON contains currency, use that currency.
If no currency is provided, describe financial opportunity without a symbol or use "NA".

ECHARTS STYLE RULES

Use clean, modern chart options.
Prefer simple titles, readable labels, no excessive legends, no 3D charts, no decorative effects, no unnecessary animation settings, and no hardcoded theme assumptions.
Use grid with containLabel true where appropriate.
Use tooltip trigger "axis" for line and bar.
Use tooltip trigger "item" for pie.

FINAL VALIDATION BEFORE RESPONDING

Before returning the JSON:
1. Validate that the response is parseable JSON.
2. Validate that every required top-level key exists.
3. Validate that every layout_grid item contains all required fields.
4. Validate that every recommendation item contains all required fields.
5. Validate that all allowed-value fields use exact allowed values.
6. Validate that every chart id is unique.
7. Validate that ECharts options contain no JavaScript functions.
8. Validate that every number in the response exists in or is directly calculated from the Profile JSON.
9. Validate that every chart uses real Profile JSON data.
10. Validate that there is no markdown.
11. Validate that there are no comments.
12. Validate that there are no unsupported schema fields.
"""

        user_prompt = f"""Dataset: {file_name}

{self._build_stats_summary(statistics, kpis)}

        Return only JSON matching the requested schema."""

        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model=settings.openai_model,
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=settings.openai_temperature,
                    max_output_tokens=settings.openai_max_tokens,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "dashboard_analysis",
                            "schema": _analysis_schema(),
                            "strict": False,
                        }
                    },
                ),
                timeout=_AI_ANALYSIS_TIMEOUT_SECONDS,
            )
            return _coerce_analysis_json(response.output_text)
        except Exception as exc:
            logger.warning("Responses API generation failed, using chat fallback", exc=str(exc))

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=settings.openai_temperature,
                    max_tokens=settings.openai_max_tokens,
                    response_format={"type": "json_object"},
                ),
                timeout=_AI_ANALYSIS_FALLBACK_TIMEOUT_SECONDS,
            )
            content = response.choices[0].message.content or "{}"
            return _coerce_analysis_json(content)
        except Exception as exc:
            logger.error("AI analysis generation failed", exc=str(exc))
            return {
                "executive_summary": _fallback_summary(statistics, kpis),
                "layout_grid": [],
                "insights": [],
                "recommendations": statistics.get("deterministic_recommendations", []),
            }

    async def chat(
        self,
        analysis: Any,
        history: list[dict[str, str]],
        user_message: str,
    ) -> dict[str, Any]:
        analysis_context = _build_chat_analysis_context(analysis)
        system_prompt = f"""You are a data analyst AI assistant with access to a business dataset.
Dataset: {analysis.name}
Rows: {analysis.row_count:,}
Columns: {analysis.column_count}

Grounded analysis context:
{analysis_context}

When answering:
- Use Computed answer context first when it is present.
- Explain the answer in natural, non-technical language for a business user.
- Lead with the takeaway, then give the few numbers that matter.
- Reference specific numbers and trends from the analysis, but avoid jargon.
- Be concise, warm, and conversational.
- Use markdown formatting for readability.
- If relevant, mention the chart in natural language.
- Never make up numbers you do not have evidence for.
- If the available data is too limited to answer, say what field or detail is missing in plain language.
- Do not say you lack the capability to analyse the dataset when computed aggregates or stored context are provided.
- Do not offer code instructions unless the user asks how to reproduce the analysis.
- Never provide hypothetical placeholder values such as Team A, Team X, example totals, or illustrative rankings.
- Avoid technical phrases in the final answer such as computed aggregate, stored context, schema, JSON, query, or column. Use everyday words like field, chart, total, group, or ranking instead.
- Do not generate React, Vue, HTML, JavaScript, or client-side chart code.
- If suggesting a visualization, describe it as a strict JSON visual specification only.
"""
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": user_message})

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1024,
                ),
                timeout=_AI_CHAT_TIMEOUT_SECONDS,
            )
            content = response.choices[0].message.content or "I couldn't generate a response."
            return {
                "content": content,
                "chart_config": None,
                "metadata": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            }
        except Exception as exc:
            logger.error("AI chat failed", exc=str(exc))
            return {
                "content": "I encountered an error. Please try again.",
                "chart_config": None,
                "metadata": {},
            }

    def _build_stats_summary(
        self, statistics: dict[str, Any], kpis: list[dict[str, Any]]
    ) -> str:
        profile_json = statistics.get("profile_json")
        if isinstance(profile_json, dict):
            return (
                "PROFILE JSON - canonical analysis source of truth:\n"
                f"{json.dumps(profile_json, ensure_ascii=False, indent=2)}"
            )

        lines = [
            f"Rows: {statistics.get('row_count', 'unknown'):,}",
            f"Columns: {statistics.get('column_count', 'unknown')}",
        ]

        if kpis:
            lines.append("\nKEY MEASURES:")
            for kpi in kpis[:8]:
                value = kpi.get("value")
                is_currency = kpi.get("is_currency", False)
                formatted = f"${value:,.2f}" if is_currency and value is not None else f"{value:,.0f}" if value is not None else "N/A"
                lines.append(f"  {_humanize_column_label(kpi['column'])}: {formatted}")

        numeric_stats = statistics.get("numeric_stats", {})
        if numeric_stats:
            lines.append("\nNUMERIC COLUMN STATISTICS:")
            for col, stats in list(numeric_stats.items())[:10]:
                lines.append(
                    f"  {col}: mean={stats.get('mean', 0):.2f}, "
                    f"min={stats.get('min', 0):.2f}, max={stats.get('max', 0):.2f}, "
                    f"total={stats.get('total', 0):.2f}"
                )

        cat_stats = statistics.get("categorical_stats", {})
        if cat_stats:
            lines.append("\nCATEGORICAL COLUMNS:")
            for col, stats in list(cat_stats.items())[:5]:
                top = stats.get("top_values", [])[:5]
                top_str = ", ".join(f"{v['value']}({v['count']})" for v in top)
                lines.append(f"  {col}: {stats.get('unique_count', 0)} unique values. Top: {top_str}")

        corr = statistics.get("correlations", {})
        if corr:
            lines.append("\nNOTABLE CORRELATIONS:")
            for pair, r in list(corr.items())[:5]:
                lines.append(f"  {pair}: r={r:.3f}")

        quality = statistics.get("data_quality", {})
        if quality:
            lines.append(f"\nDATA QUALITY SCORE: {quality.get('score', 100)}/100")
            for issue in quality.get("issues", [])[:5]:
                lines.append(f"  Issue: {issue.get('description', '')}")

        parser = statistics.get("parser", {})
        if parser:
            lines.append("\nPARSER PROFILE:")
            parser_bits = ", ".join(
                f"{key}={value}"
                for key, value in parser.items()
                if value is not None
            )
            lines.append(f"  {parser_bits}")

        upload_context = statistics.get("upload_context")
        if upload_context:
            lines.append("\nUPLOAD RELATIONSHIP CONTEXT:")
            data_description = upload_context.get("data_description") if isinstance(upload_context, dict) else None
            instructions = upload_context.get("instructions") if isinstance(upload_context, dict) else None
            if data_description:
                lines.append(f"  Data description: {data_description}")
            if instructions:
                lines.append(f"  User instructions: {instructions}")
            cleaning = upload_context.get("cleaning") if isinstance(upload_context, dict) else None
            if isinstance(cleaning, dict) and cleaning.get("enabled"):
                report = cleaning.get("report", {})
                if isinstance(report, dict):
                    lines.append(
                        "  Cleaning applied: "
                        f"rows {report.get('input_rows')} -> {report.get('output_rows')}, "
                        f"columns {report.get('input_columns')} -> {report.get('output_columns')}, "
                        f"duplicates removed={report.get('removed_duplicate_rows', 0)}, "
                        f"fuzzy duplicates removed={report.get('removed_fuzzy_duplicate_rows', 0)}, "
                        f"rows missing critical metrics dropped={report.get('dropped_rows_missing_critical_metrics', 0)}, "
                        f"outlier values capped={report.get('capped_outlier_values', 0)}, "
                        f"outliers excluded={report.get('excluded_outlier_rows', 0)}"
                    )
            suggestions = upload_context.get("suggestions", []) if isinstance(upload_context, dict) else []
            for suggestion in suggestions[:5]:
                if not isinstance(suggestion, dict):
                    continue
                title = suggestion.get("title", "Relationship suggestion")
                detail = suggestion.get("description", "")
                confidence = suggestion.get("confidence")
                lines.append(f"  {title}: {detail} confidence={confidence}")

        forecasts = statistics.get("forecasts", [])
        if forecasts:
            lines.append("\nFORECASTS:")
            for forecast in forecasts[:3]:
                next_month = forecast.get("predictions", {}).get("next_month", {})
                lines.append(
                    f"  {forecast.get('metric')}: next_month={next_month.get('value')} "
                    f"range={next_month.get('lower')}..{next_month.get('upper')}"
                )

        anomalies = statistics.get("anomalies", [])
        if anomalies:
            lines.append("\nANOMALIES:")
            for anomaly in anomalies[:5]:
                lines.append(f"  {anomaly.get('description')} score={anomaly.get('score')}")

        deterministic_recommendations = statistics.get("deterministic_recommendations", [])
        if deterministic_recommendations:
            lines.append("\nEVIDENCE-BACKED RECOMMENDATION CANDIDATES:")
            for rec in deterministic_recommendations[:5]:
                lines.append(f"  {rec.get('title')}: {rec.get('evidence')}")

        return "\n".join(lines)


def _analysis_schema() -> dict[str, Any]:
    chart_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "grid_span": {
                "type": "string",
                "enum": [
                    "col-span-12",
                    "col-span-12 md:col-span-8",
                    "col-span-12 md:col-span-4",
                    "col-span-12 md:col-span-6",
                ],
            },
            "chart_type": {"type": "string", "enum": ["line", "bar", "pie", "scatter"]},
            "echarts_option": {"type": "object", "additionalProperties": True},
        },
        "required": ["id", "title", "description", "grid_span", "chart_type", "echarts_option"],
    }
    recommendation_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "problem": {"type": "string"},
            "evidence": {"type": "string"},
            "expected_impact": {"type": "string"},
            "financial_opportunity": {"type": ["string", "number"]},
            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
            "owner": {"type": "string"},
            "difficulty": {"type": "string", "enum": ["Easy", "Medium", "Hard"]},
            "timeline": {"type": "string"},
        },
        "required": [
            "problem",
            "evidence",
            "expected_impact",
            "financial_opportunity",
            "priority",
            "owner",
            "difficulty",
            "timeline",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "executive_summary": {"type": "string"},
            "layout_grid": {"type": "array", "items": chart_schema, "maxItems": 6},
            "recommendations": {"type": "array", "items": recommendation_schema, "maxItems": 5},
        },
        "required": ["executive_summary", "layout_grid", "recommendations"],
    }


def _coerce_analysis_json(content: str) -> dict[str, Any]:
    result = json.loads(content or "{}")
    return {
        "executive_summary": str(result.get("executive_summary", "")),
        "layout_grid": _sanitize_layout_grid(result.get("layout_grid") or []),
        "insights": list(result.get("insights") or []),
        "recommendations": [
            _normalize_recommendation(rec)
            for rec in list(result.get("recommendations") or [])
            if isinstance(rec, dict)
        ],
    }


def _sanitize_layout_grid(items: Any) -> list[dict[str, Any]]:
    allowed_spans = {
        "col-span-12",
        "col-span-12 md:col-span-8",
        "col-span-12 md:col-span-4",
        "col-span-12 md:col-span-6",
    }
    allowed_types = {"line", "bar", "pie", "scatter"}
    sanitized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        chart_id = _safe_chart_id(item.get("id") or item.get("title") or f"chart_{index + 1}")
        if chart_id in seen_ids:
            chart_id = f"{chart_id}_{index + 1}"
        seen_ids.add(chart_id)

        chart_type = str(item.get("chart_type") or "").lower()
        grid_span = str(item.get("grid_span") or "")
        option = item.get("echarts_option")
        if chart_type not in allowed_types or grid_span not in allowed_spans or not isinstance(option, dict):
            continue
        if _contains_unsafe_chart_value(option):
            continue

        sanitized.append(
            {
                "id": chart_id,
                "title": str(item.get("title") or "Chart"),
                "description": str(item.get("description") or ""),
                "grid_span": grid_span,
                "chart_type": chart_type,
                "echarts_option": option,
            }
        )
    return sanitized[:6]


def _normalize_recommendation(rec: dict[str, Any]) -> dict[str, Any]:
    if "title" in rec and "importance" in rec and "data" in rec:
        return rec

    priority = _allowed_title_case(rec.get("priority"), {"High", "Medium", "Low"}, "Medium")
    difficulty = _allowed_title_case(rec.get("difficulty"), {"Easy", "Medium", "Hard"}, "Medium")
    financial_raw = rec.get("financial_opportunity", "NA")
    financial_value = _parse_financial_opportunity(financial_raw)
    show_financial = financial_value is not None
    problem = str(rec.get("problem") or "Review analysis finding").strip()
    expected_impact = str(rec.get("expected_impact") or "").strip()
    evidence = str(rec.get("evidence") or "").strip()
    owner = str(rec.get("owner") or "Leadership Team").strip()
    timeline = str(rec.get("timeline") or "30 Days").strip()

    return {
        "title": problem,
        "description": expected_impact or evidence,
        "problem": problem,
        "evidence": evidence,
        "expected_impact": expected_impact,
        "financial_opportunity": financial_value if show_financial else 0,
        "show_financial_opportunity": show_financial,
        "importance": priority.lower(),
        **confidence_fields(AI_SOURCE_BY_PRIORITY[priority]),
        "data": {
            "difficulty": difficulty.lower(),
            "owner": owner,
            "estimated_completion": timeline,
            "financial_opportunity": financial_value if show_financial else None,
            "financial_opportunity_raw": financial_raw,
            "expected_impact": expected_impact,
            "evidence": evidence,
            "priority": priority,
        },
    }


def _allowed_title_case(value: Any, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    for option in allowed:
        if option.lower() == normalized:
            return option
    return fallback


_FINANCIAL_AMOUNT = re.compile(
    r"(-?\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*(thousand|million|billion|bn|mn|mm|k|m|b)\b)?",
    re.IGNORECASE,
)
_FINANCIAL_MULTIPLIERS = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mm": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
}


def _parse_financial_opportunity(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "").strip()
    if not text or text.upper() == "NA":
        return None
    match = _FINANCIAL_AMOUNT.search(text)
    if not match:
        return None
    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (match.group(2) or "").lower()
    return amount * _FINANCIAL_MULTIPLIERS.get(suffix, 1)


def _safe_chart_id(value: Any) -> str:
    chart_id = re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower())
    chart_id = re.sub(r"_+", "_", chart_id).strip("_")
    return chart_id or "chart"


# Matches JS syntax and non-JSON literals as whole tokens, so ordinary labels
# such as "Finance", "Maintenance", or "Renew date" are not mistaken for them.
_UNSAFE_CHART_VALUE = re.compile(
    r"=>|\bfunction\s*\(|\bnew\s+date\s*\(|\bregexp\b|\bundefined\b|\bnan\b|\binfinity\b",
    re.IGNORECASE,
)


def _contains_unsafe_chart_value(value: Any) -> bool:
    if isinstance(value, str):
        return _UNSAFE_CHART_VALUE.search(value) is not None
    if isinstance(value, dict):
        return any(_contains_unsafe_chart_value(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_chart_value(child) for child in value)
    return False


def _build_chat_analysis_context(analysis: Any) -> str:
    metadata = analysis.metadata_ or {}
    lines: list[str] = []

    data_profile = metadata.get("data_profile")
    if isinstance(data_profile, dict):
        dataset = data_profile.get("dataset", {})
        if isinstance(dataset, dict):
            lines.append(
                "Profile JSON: "
                f"{dataset.get('row_count', analysis.row_count)} rows, "
                f"{dataset.get('column_count', analysis.column_count)} columns"
            )
        metrics = data_profile.get("metrics", {})
        if isinstance(metrics, dict):
            kpis = metrics.get("kpis", [])
            if kpis:
                lines.append("Profile KPIs:")
                for kpi in kpis[:8]:
                    if isinstance(kpi, dict):
                        lines.append(
                            f"  - {kpi.get('column')}: {kpi.get('value')} ({kpi.get('type')})"
                        )

    if analysis.summary:
        lines.append(f"Executive summary: {analysis.summary}")

    schema = metadata.get("schema", [])
    if schema:
        lines.append("Columns:")
        for column in schema[:20]:
            name = column.get("name")
            dtype = column.get("dtype")
            role = column.get("analysis_role") or column.get("semantic_type")
            lines.append(f"  - {name} ({dtype}; {role})")

    quality = metadata.get("data_quality", {})
    if quality:
        lines.append(f"Data quality score: {quality.get('score', 'unknown')}/100")
        for issue in quality.get("issues", [])[:5]:
            lines.append(f"  - Quality issue: {issue.get('description')}")

    parser = metadata.get("parser", {})
    if parser:
        parser_bits = ", ".join(
            f"{key}={value}"
            for key, value in parser.items()
            if value is not None
        )
        lines.append(f"Parser profile: {parser_bits}")

    upload_context = metadata.get("upload_context")
    if upload_context:
        lines.append("Upload relationship context:")
        data_description = upload_context.get("data_description") if isinstance(upload_context, dict) else None
        instructions = upload_context.get("instructions") if isinstance(upload_context, dict) else None
        if data_description:
            lines.append(f"  - Data description: {data_description}")
        if instructions:
            lines.append(f"  - User instructions: {instructions}")
        cleaning = upload_context.get("cleaning") if isinstance(upload_context, dict) else None
        if isinstance(cleaning, dict) and cleaning.get("enabled"):
            report = cleaning.get("report", {})
            if isinstance(report, dict):
                lines.append(
                    "  - Cleaning applied: "
                    f"rows {report.get('input_rows')} -> {report.get('output_rows')}; "
                    f"duplicates removed={report.get('removed_duplicate_rows', 0)}; "
                    f"fuzzy duplicates removed={report.get('removed_fuzzy_duplicate_rows', 0)}; "
                    f"rows missing critical metrics dropped={report.get('dropped_rows_missing_critical_metrics', 0)}; "
                    f"outlier values capped={report.get('capped_outlier_values', 0)}; "
                    f"outliers excluded={report.get('excluded_outlier_rows', 0)}"
                )
        suggestions = upload_context.get("suggestions", []) if isinstance(upload_context, dict) else []
        for suggestion in suggestions[:5]:
            if isinstance(suggestion, dict):
                lines.append(f"  - {suggestion.get('title')}: {suggestion.get('description')}")

    insights = sorted(getattr(analysis, "insights", []) or [], key=lambda item: item.sort_order)
    if insights:
        lines.append("Stored insights:")
        for insight in insights[:16]:
            lines.append(
                f"  - {insight.type}: {insight.title} — {insight.description}"
            )

    charts = analysis.charts or []
    if charts:
        lines.append("Available charts:")
        for chart in charts[:8]:
            lines.append(f"  - {chart.get('title', chart.get('type', 'Chart'))}")

    if not lines:
        return "No computed analysis metadata is available yet."
    return "\n".join(lines)


def _fallback_summary(statistics: dict[str, Any], kpis: list[dict[str, Any]]) -> str:
    lines = [
        f"The file contains {statistics.get('row_count', 0):,} rows across {statistics.get('column_count', 0)} columns.",
    ]
    if statistics.get("sample_truncated"):
        limit = statistics.get("sample_row_limit")
        lines.append(
            f"This analysis covers a sample of the first {limit:,} rows rather than the full file."
            if limit
            else "This analysis covers a sample of the file rather than the full file."
        )
    if kpis:
        lines.append(f"Key measures include {_metric_list_sentence(kpis[:4])}.")
    quality = statistics.get("data_quality", {})
    if quality:
        score = quality.get("score", 0)
        numeric_score = _safe_int(score)
        if numeric_score >= 95:
            lines.append(f"Automated checks did not find major data quality issues; quality score is {score}/100.")
        else:
            lines.append(f"Automated checks found data quality items to review; quality score is {score}/100.")
    return "\n".join(lines)


def _metric_list_sentence(kpis: list[dict[str, Any]]) -> str:
    parts = []
    for kpi in kpis:
        label = _humanize_column_label(str(kpi.get("column", "measure")))
        value = _format_metric_value(kpi)
        if kpi.get("is_percent"):
            parts.append(f"a {label.lower()} rate of {value}%")
        elif kpi.get("is_total", True):
            parts.append(f"{label} at {value}")
        else:
            parts.append(f"average {label.lower()} at {value}")
    if len(parts) <= 1:
        return parts[0] if parts else "the available measures"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _format_metric_value(kpi: dict[str, Any]) -> str:
    value = kpi.get("value")
    if value is None:
        return "not available"
    if kpi.get("is_currency"):
        return f"${float(value):,.2f}"
    numeric = float(value)
    if abs(numeric) >= 1000:
        return f"{numeric:,.0f}" if numeric.is_integer() else f"{numeric:,.2f}"
    return f"{numeric:,.2f}".rstrip("0").rstrip(".")


def _humanize_column_label(value: str) -> str:
    replacements = {
        "pct": "%",
        "km": "km",
        "kmh": "km/h",
        "eur": "EUR",
        "usd": "USD",
    }
    return " ".join(
        replacements.get(word.lower(), word.capitalize())
        for word in re.sub(r"[_\s]+", " ", value).strip().split()
    )


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
