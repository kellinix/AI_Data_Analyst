"""
AI service.

Statistical analysis happens before LLM calls. The model receives structured
metrics, then returns validated JSON for executive narrative and actions.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
except Exception as exc:  # pragma: no cover - exercised only in lean local envs
    logger.warning("OpenAI client unavailable", exc=str(exc))
    client = None

_TEAM_COLUMN_PATTERNS = (
    "team",
    "team_name",
    "player_team",
    "club",
    "club_name",
    "squad",
    "squad_name",
    "country",
    "team_country",
    "nation",
    "national_team",
)
_GOALS_FOR_PATTERNS = (
    "goals_team",
    "team_goals",
    "goals_for",
    "goals_scored",
    "gf",
)
_GOALS_AGAINST_PATTERNS = (
    "goals_opponent",
    "opponent_goals",
    "goals_against",
    "goals_conceded",
    "ga",
)
_PLAYER_GOALS_PATTERNS = (
    "goals",
    "player_goals",
)
_RESULT_COLUMN_PATTERNS = (
    "match_result",
    "result",
    "outcome",
)
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
        computed_context = await _build_chat_computed_context(analysis, user_message)
        chart_config = await _build_chat_chart_config(analysis, user_message)
        if _asks_for_team_goals_chart(user_message):
            if chart_config:
                return {
                    "content": _chart_config_markdown_answer(chart_config),
                    "chart_config": chart_config,
                    "metadata": {"deterministic": True},
                }
            return {
                "content": _team_goals_unavailable_answer(analysis),
                "chart_config": None,
                "metadata": {"deterministic": True},
            }
        if computed_context:
            analysis_context = f"{analysis_context}\n\nComputed answer context:\n{computed_context}"
        if chart_config:
            analysis_context = (
                f"{analysis_context}\n\nA popup chart is attached to this answer: "
                f"{chart_config.get('title')}. Briefly mention it when useful."
            )
            chart_context = _chart_config_context(chart_config)
            if chart_context:
                analysis_context = f"{analysis_context}\n{chart_context}"
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
                "chart_config": chart_config,
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
        "confidence": {"High": 0.85, "Medium": 0.7, "Low": 0.55}[priority],
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


def _parse_financial_opportunity(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "").strip()
    if not text or text.upper() == "NA":
        return None
    match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _safe_chart_id(value: Any) -> str:
    chart_id = re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower())
    chart_id = re.sub(r"_+", "_", chart_id).strip("_")
    return chart_id or "chart"


def _contains_unsafe_chart_value(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(
            token in lowered
            for token in (
                "function",
                "() =>",
                "=>",
                "new date",
                "regexp",
                "undefined",
                "nan",
                "infinity",
            )
        )
    if isinstance(value, dict):
        return any(_contains_unsafe_chart_value(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_chart_value(child) for child in value)
    return False


async def _build_chat_computed_context(analysis: Any, user_message: str) -> str:
    parts = [_known_metric_notes(analysis)]
    if not _asks_for_team_goals_chart(user_message):
        team_context = await _compute_team_performance_context(analysis, user_message)
        if team_context:
            parts.append(team_context)
    return "\n\n".join(part for part in parts if part)


async def _build_chat_chart_config(analysis: Any, user_message: str) -> dict[str, Any] | None:
    if _asks_for_team_goals_chart(user_message):
        return await _compute_team_goals_chart_config(analysis)
    return None


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _known_metric_notes(analysis: Any) -> str:
    column_names = {
        str(column.get("name", "")).lower()
        for column in (analysis.metadata_ or {}).get("schema", [])
        if isinstance(column, dict)
    }
    notes = []
    if "goals_opponent" in column_names:
        notes.append(
            "- goals_opponent: goals scored by the opposing team against the row's team; lower values indicate stronger defensive results."
        )
    if "goals_team" in column_names:
        notes.append(
            "- goals_team: goals scored by the row's team; higher values indicate stronger attacking results."
        )
    if not notes:
        return ""
    return "Metric notes:\n" + "\n".join(notes)


async def _compute_team_performance_context(analysis: Any, user_message: str) -> str:
    if not _asks_for_team_performance(user_message):
        return ""

    uploaded_file = getattr(analysis, "file", None)
    storage_path = getattr(uploaded_file, "storage_path", None)
    if not storage_path:
        return _team_performance_missing_context(
            "the uploaded file path is not loaded for this chat session"
        )

    schema = [
        column
        for column in (analysis.metadata_ or {}).get("schema", [])
        if isinstance(column, dict) and column.get("name")
    ]
    if not schema:
        return _team_performance_missing_context("the column schema is missing")

    team_col = _select_column(schema, _TEAM_COLUMN_PATTERNS, require_non_numeric=True)
    goals_for_col = _select_column(schema, _GOALS_FOR_PATTERNS, require_numeric=True)
    goals_against_col = _select_column(schema, _GOALS_AGAINST_PATTERNS, require_numeric=True)
    player_goals_col = _select_column(
        schema,
        _PLAYER_GOALS_PATTERNS,
        allow_contains=False,
        require_numeric=True,
        exclude={goals_for_col, goals_against_col},
    )
    result_col = _select_column(schema, _RESULT_COLUMN_PATTERNS)
    if not team_col:
        return _team_performance_missing_context("a team, club, or squad column")
    if not any([goals_for_col, goals_against_col, player_goals_col, result_col]):
        return _team_performance_missing_context(
            "team-level performance metrics such as goals_team, goals_opponent, goals, or match_result"
        )

    try:
        import duckdb

        from app.services.file_processor import FileProcessor

        conn = duckdb.connect(":memory:")
    except Exception as exc:
        logger.warning("Team performance chat aggregate dependencies unavailable", exc=str(exc))
        return _team_performance_missing_context("the dataset query engine is unavailable")

    try:
        extension = Path(storage_path).suffix.lower()
        await FileProcessor().read_to_duckdb(conn, storage_path, extension)
        rows = _query_team_performance(
            conn=conn,
            team_col=team_col,
            goals_for_col=goals_for_col,
            goals_against_col=goals_against_col,
            player_goals_col=player_goals_col,
            result_col=result_col,
        )
    except Exception as exc:
        logger.warning("Team performance chat aggregate failed", exc=str(exc))
        return _team_performance_missing_context("the team performance aggregate could not be computed")
    finally:
        conn.close()

    if not rows:
        return _team_performance_missing_context("no non-empty team rows were found")

    ranking_basis = _team_ranking_basis(goals_for_col, goals_against_col, result_col)
    lines = [
        "Team performance aggregate computed from the uploaded dataset.",
        f"Detected columns: team={team_col}; goals_for={goals_for_col or 'missing'}; goals_against={goals_against_col or 'missing'}; player_goals={player_goals_col or 'missing'}; match_result={result_col or 'missing'}.",
        f"Ranking basis: {ranking_basis}.",
        "Top teams:",
    ]
    for row in rows[:10]:
        lines.append(_format_team_performance_row(row))
    return "\n".join(lines)


def _asks_for_team_performance(user_message: str) -> bool:
    normalized = user_message.lower()
    has_team = any(term in normalized for term in ("team", "club", "squad"))
    has_comparison = any(
        term in normalized
        for term in (
            "better",
            "best",
            "top",
            "rank",
            "ranking",
            "performed",
            "performance",
            "winner",
            "strongest",
        )
    )
    return has_team and has_comparison


def _asks_for_team_goals_chart(user_message: str) -> bool:
    normalized = user_message.lower()
    has_team = any(term in normalized for term in ("team", "teams", "club", "clubs", "squad"))
    has_goals = any(term in normalized for term in ("goal", "goals", "scored"))
    wants_ranked_view = any(
        term in normalized
        for term in ("top", "rank", "ranking", "highest", "show", "chart", "bar", "visual")
    )
    return has_team and has_goals and wants_ranked_view


async def _compute_team_goals_chart_config(analysis: Any) -> dict[str, Any] | None:
    uploaded_file = getattr(analysis, "file", None)
    storage_path = getattr(uploaded_file, "storage_path", None)
    if not storage_path:
        return None

    schema = [
        column
        for column in (analysis.metadata_ or {}).get("schema", [])
        if isinstance(column, dict) and column.get("name")
    ]
    team_col = _select_column(schema, _TEAM_COLUMN_PATTERNS, require_non_numeric=True)
    goals_for_col = _select_column(schema, _GOALS_FOR_PATTERNS, require_numeric=True)
    player_goals_col = _select_column(
        schema,
        _PLAYER_GOALS_PATTERNS,
        allow_contains=False,
        require_numeric=True,
        exclude={goals_for_col},
    )
    goals_col = goals_for_col or player_goals_col
    if not team_col or not goals_col:
        return None

    try:
        import duckdb

        from app.services.file_processor import FileProcessor

        conn = duckdb.connect(":memory:")
    except Exception as exc:
        logger.warning("Team goals chart dependencies unavailable", exc=str(exc))
        return None

    try:
        extension = Path(storage_path).suffix.lower()
        await FileProcessor().read_to_duckdb(conn, storage_path, extension)
        rows = _query_top_team_goals(conn, team_col, goals_col, limit=5)
    except Exception as exc:
        logger.warning("Team goals chart aggregate failed", exc=str(exc))
        return None
    finally:
        conn.close()

    if not rows:
        return None
    return _team_goals_chart_config(rows, team_col, goals_col)


def _query_top_team_goals(
    conn: Any,
    team_col: str,
    goals_col: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    team_identifier = _quote_identifier(team_col)
    goals_identifier = _quote_identifier(goals_col)
    sql = f"""
        SELECT
            CAST({team_identifier} AS VARCHAR) AS team,
            SUM({goals_identifier}) AS goals_scored
        FROM data
        WHERE {team_identifier} IS NOT NULL AND {goals_identifier} IS NOT NULL
        GROUP BY {team_identifier}
        ORDER BY goals_scored DESC NULLS LAST
        LIMIT {int(limit)}
    """
    return [
        {"team": str(team), "goals_scored": float(goals)}
        for team, goals in conn.execute(sql).fetchall()
        if team is not None and goals is not None
    ]


def _team_goals_chart_config(
    rows: list[dict[str, Any]],
    team_col: str,
    goals_col: str,
) -> dict[str, Any]:
    labels = [str(row["team"]) for row in rows]
    values = [round(float(row["goals_scored"]), 2) for row in rows]
    return {
        "id": "chat_top_teams_goals",
        "type": "bar",
        "title": "Top 5 Teams by Goals Scored",
        "description": f"Sum of {goals_col} grouped by {team_col}.",
        "xAxis": "Team",
        "yAxis": "Goals scored",
        "series": ["Goals scored"],
        "color_scheme": ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"],
        "visual_spec": None,
        "echarts_option": {
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 56, "right": 24, "top": 24, "bottom": 72, "containLabel": True},
            "xAxis": {
                "type": "category",
                "name": "Team",
                "nameLocation": "middle",
                "nameGap": 48,
                "data": labels,
                "axisLabel": {"interval": 0, "rotate": 25},
            },
            "yAxis": {"type": "value", "name": "Goals scored", "nameLocation": "middle", "nameGap": 52},
            "series": [
                {
                    "type": "bar",
                    "name": "Goals scored",
                    "data": values,
                    "label": {"show": True, "position": "top", "formatter": "{c}"},
                    "itemStyle": {"borderRadius": [6, 6, 0, 0]},
                }
            ],
        },
    }


def _chart_config_context(chart_config: dict[str, Any]) -> str:
    option = chart_config.get("echarts_option")
    if not isinstance(option, dict):
        return ""
    x_axis = option.get("xAxis")
    series = option.get("series")
    if not isinstance(x_axis, dict) or not isinstance(series, list) or not series:
        return ""
    labels = x_axis.get("data")
    first_series = series[0]
    if not isinstance(labels, list) or not isinstance(first_series, dict):
        return ""
    values = first_series.get("data")
    if not isinstance(values, list):
        return ""
    pairs = [
        f"{label}: {_format_context_number(value)}"
        for label, value in zip(labels, values, strict=False)
    ]
    if not pairs:
        return ""
    return "Attached chart data: " + "; ".join(pairs)


def _chart_config_markdown_answer(chart_config: dict[str, Any]) -> str:
    option = chart_config.get("echarts_option")
    if not isinstance(option, dict):
        return "I found the result and opened a chart for you."
    x_axis = option.get("xAxis")
    series = option.get("series")
    if not isinstance(x_axis, dict) or not isinstance(series, list) or not series:
        return "I found the result and opened a chart for you."
    labels = x_axis.get("data")
    first_series = series[0]
    if not isinstance(labels, list) or not isinstance(first_series, dict):
        return "I found the result and opened a chart for you."
    values = first_series.get("data")
    if not isinstance(values, list):
        return "I found the result and opened a chart for you."

    metric = str(first_series.get("name") or chart_config.get("yAxis") or "Value")
    lines = [
        f"The {str(chart_config.get('title') or 'top results').lower()} are:",
        "",
    ]
    for index, (label, value) in enumerate(zip(labels, values, strict=False), start=1):
        lines.append(f"{index}. **{label}**: {_format_context_number(value)} {metric.lower()}")
    lines.extend(
        [
            "",
            "I've opened a bar chart so you can compare them at a glance.",
        ]
    )
    return "\n".join(lines)


def _team_goals_unavailable_answer(analysis: Any) -> str:
    schema = [
        column
        for column in (analysis.metadata_ or {}).get("schema", [])
        if isinstance(column, dict) and column.get("name")
    ]
    team_col = _select_column(schema, _TEAM_COLUMN_PATTERNS, require_non_numeric=True)
    goals_col = _select_column(schema, _GOALS_FOR_PATTERNS, require_numeric=True) or _select_column(
        schema,
        _PLAYER_GOALS_PATTERNS,
        allow_contains=False,
        require_numeric=True,
    )
    missing = []
    if not team_col:
        missing.append("a field that identifies the team, country, nation, club, or squad")
    if not goals_col:
        missing.append("a goals field, such as goals_team or goals")
    if not missing:
        missing.append("the file could not be read for this question")
    missing_text = "; ".join(missing)
    return (
        "I can't give a real top 5 for goals scored yet because I can't see "
        f"{missing_text}. "
        "I don’t want to guess team names or goal totals, so I’ll only show this ranking when those fields are available."
    )


def _team_performance_missing_context(missing: str) -> str:
    return (
        "The user asked for a team ranking, but the answer cannot be worked out because "
        f"{missing} is unavailable. Explain this plainly and do not invent example teams or numbers."
    )


def _select_column(
    schema: list[dict[str, Any]],
    patterns: tuple[str, ...],
    *,
    allow_contains: bool = True,
    require_numeric: bool = False,
    require_non_numeric: bool = False,
    exclude: set[str | None] | None = None,
) -> str | None:
    excluded = {value for value in (exclude or set()) if value}
    by_name = {
        str(column["name"]): _normalize_column_name(str(column["name"]))
        for column in schema
        if str(column["name"]) not in excluded
        and (not require_numeric or bool(column.get("is_numeric")))
        and (not require_non_numeric or not bool(column.get("is_numeric")))
    }
    for wanted in patterns:
        for original, normalized in by_name.items():
            if normalized == wanted:
                return original
    if not allow_contains:
        return None
    for wanted in patterns:
        for original, normalized in by_name.items():
            if wanted in normalized:
                return original
    return None


def _query_team_performance(
    *,
    conn: Any,
    team_col: str,
    goals_for_col: str | None,
    goals_against_col: str | None,
    player_goals_col: str | None,
    result_col: str | None,
) -> list[dict[str, Any]]:
    team_identifier = _quote_identifier(team_col)
    select_parts = [
        f"CAST({team_identifier} AS VARCHAR) AS team",
        "COUNT(*) AS rows",
    ]
    order_parts = []

    if goals_for_col:
        goals_for_identifier = _quote_identifier(goals_for_col)
        select_parts.extend(
            [
                f"AVG({goals_for_identifier}) AS avg_goals_for",
                f"SUM({goals_for_identifier}) AS total_goals_for",
            ]
        )
    else:
        select_parts.extend(["NULL AS avg_goals_for", "NULL AS total_goals_for"])

    if goals_against_col:
        goals_against_identifier = _quote_identifier(goals_against_col)
        select_parts.extend(
            [
                f"AVG({goals_against_identifier}) AS avg_goals_against",
                f"SUM({goals_against_identifier}) AS total_goals_against",
            ]
        )
    else:
        select_parts.extend(["NULL AS avg_goals_against", "NULL AS total_goals_against"])

    if goals_for_col and goals_against_col:
        select_parts.append(
            f"AVG({_quote_identifier(goals_for_col)} - {_quote_identifier(goals_against_col)}) AS avg_goal_difference"
        )
        order_parts.append("avg_goal_difference DESC NULLS LAST")
    else:
        select_parts.append("NULL AS avg_goal_difference")

    if player_goals_col:
        player_goals_identifier = _quote_identifier(player_goals_col)
        select_parts.append(f"SUM({player_goals_identifier}) AS total_player_goals")
        if not order_parts:
            order_parts.append("total_player_goals DESC NULLS LAST")
    else:
        select_parts.append("NULL AS total_player_goals")

    if result_col:
        result_identifier = _quote_identifier(result_col)
        result_text = f"LOWER(CAST({result_identifier} AS VARCHAR))"
        win_expr = (
            f"CASE WHEN {result_text} IN ('w', 'win', 'won', '3', 'victory') "
            f"OR {result_text} LIKE '%win%' THEN 1 ELSE 0 END"
        )
        draw_expr = (
            f"CASE WHEN {result_text} IN ('d', 'draw', 'drawn', '1', 'tie') "
            f"OR {result_text} LIKE '%draw%' THEN 1 ELSE 0 END"
        )
        loss_expr = (
            f"CASE WHEN {result_text} IN ('l', 'loss', 'lost', '0', 'defeat') "
            f"OR {result_text} LIKE '%loss%' OR {result_text} LIKE '%lost%' THEN 1 ELSE 0 END"
        )
        select_parts.extend(
            [
                f"SUM({win_expr}) AS wins",
                f"SUM({draw_expr}) AS draws",
                f"SUM({loss_expr}) AS losses",
                f"AVG({win_expr}) AS win_rate",
            ]
        )
        order_parts.insert(0, "win_rate DESC NULLS LAST")
    else:
        select_parts.extend(
            [
                "NULL AS wins",
                "NULL AS draws",
                "NULL AS losses",
                "NULL AS win_rate",
            ]
        )

    if not order_parts:
        order_parts.append("rows DESC")

    sql = f"""
        SELECT {", ".join(select_parts)}
        FROM data
        WHERE {team_identifier} IS NOT NULL
        GROUP BY {team_identifier}
        ORDER BY {", ".join(order_parts)}, rows DESC
        LIMIT 10
    """
    columns = [description[0] for description in conn.execute(sql).description]
    return [
        dict(zip(columns, row, strict=False))
        for row in conn.fetchall()
        if row and row[0]
    ]


def _team_ranking_basis(
    goals_for_col: str | None,
    goals_against_col: str | None,
    result_col: str | None,
) -> str:
    if result_col and goals_for_col and goals_against_col:
        return "win rate first, then average goal difference"
    if result_col:
        return "win rate"
    if goals_for_col and goals_against_col:
        return "average goal difference"
    if goals_for_col:
        return f"average {goals_for_col}"
    return "available team-level metric"


def _format_team_performance_row(row: dict[str, Any]) -> str:
    parts = [
        f"- {row.get('team')}",
        f"rows={_format_context_number(row.get('rows'))}",
    ]
    if row.get("win_rate") is not None:
        parts.append(f"win_rate={float(row['win_rate']) * 100:.1f}%")
        parts.append(f"W-D-L={_format_context_number(row.get('wins'))}-{_format_context_number(row.get('draws'))}-{_format_context_number(row.get('losses'))}")
    if row.get("avg_goal_difference") is not None:
        parts.append(f"avg_goal_diff={float(row['avg_goal_difference']):.2f}")
    if row.get("avg_goals_for") is not None:
        parts.append(f"avg_goals_for={float(row['avg_goals_for']):.2f}")
    if row.get("avg_goals_against") is not None:
        parts.append(f"avg_goals_against={float(row['avg_goals_against']):.2f}")
    if row.get("total_player_goals") is not None:
        parts.append(f"total_player_goals={_format_context_number(row.get('total_player_goals'))}")
    return "; ".join(parts)


def _format_context_number(value: Any) -> str:
    if value is None:
        return "NA"
    numeric = float(value)
    if numeric.is_integer():
        return f"{numeric:,.0f}"
    return f"{numeric:,.2f}"


def _normalize_column_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


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
        if kpi.get("is_total", True):
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
        "xg": "xG",
        "xa": "xA",
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
