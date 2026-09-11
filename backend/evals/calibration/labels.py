"""
Correctness labels for recommendations.

Rule-based recommendations are labeled deterministically against the planted
truth. AI recommendations are free text, so an LLM judge grades them against
the same truth; the judge also grades the rule-based ones, and its agreement
with the deterministic labels is reported as a check on the judge itself.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any

from app.analytics.calibration import (
    RULE_ANOMALY,
    RULE_DATA_QUALITY,
    RULE_FORECAST,
    RULE_TRACKING,
)
from app.analytics.recommendations import _humanize

# A forecast recommendation fires when the predicted move is at least this
# large; the same threshold decides whether the real move was material.
MATERIAL_CHANGE_PERCENT = 5.0


@dataclass(frozen=True)
class Label:
    correct: bool | None  # None: not scored
    reason: str
    method: str  # "rule" | "judge" | "none"
    planted_finding: str | None = None  # judge only: "anomaly" | "data_defect" | "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Rule-based recommendations ─────────────────────────────────────────────


def label_rule_recommendation(
    rec: dict[str, Any], *, truth: dict[str, Any], computed: dict[str, Any]
) -> Label:
    source = rec.get("confidence_source")
    if source == RULE_TRACKING:
        return Label(None, "Makes no falsifiable claim.", "rule")
    if source == RULE_ANOMALY:
        return _label_anomaly(rec, truth, computed.get("anomalies", []))
    if source == RULE_FORECAST:
        return _label_forecast(rec, truth, computed.get("forecasts", []))
    if source == RULE_DATA_QUALITY:
        issues = computed.get("statistics", {}).get("data_quality", {}).get("issues", [])
        return _label_data_quality(rec, truth, issues)
    return Label(None, f"No rule labeler for source {source!r}.", "rule")


def _label_anomaly(rec: dict[str, Any], truth: dict[str, Any], anomalies: list[dict]) -> Label:
    anomaly = next((a for a in anomalies if a.get("description") == rec.get("evidence")), None)
    if anomaly is None:
        return Label(None, "Could not match the recommendation to a detected anomaly.", "rule")

    planted = truth.get("planted_anomaly")
    if not planted:
        return Label(False, "No anomaly was planted; the flagged record is ordinary variation.", "rule")
    if anomaly.get("column") not in planted["columns"]:
        return Label(
            False,
            f"Flagged {anomaly.get('column')}, which the planted event did not affect.",
            "rule",
        )

    if anomaly.get("type") == "time_series_spike":
        if str(anomaly.get("period", ""))[:7] == planted["month"]:
            return Label(True, "Flagged the month containing the planted event.", "rule")
        return Label(False, f"Flagged {anomaly.get('period')}, not the planted month.", "rule")

    context = {key: str(value) for key, value in (anomaly.get("context") or {}).items()}
    expected = {truth["date_column"]: planted["date"], **planted["dimensions"]}
    mismatched = [key for key, value in context.items() if key in expected and expected[key] != value]
    if context and not mismatched:
        return Label(True, "Flagged the planted record.", "rule")
    return Label(False, f"Flagged a different record ({context}) than the planted one.", "rule")


def _label_forecast(rec: dict[str, Any], truth: dict[str, Any], forecasts: list[dict]) -> Label:
    forecast = next((f for f in forecasts if _forecast_title(f) == rec.get("title")), None)
    if forecast is None:
        return Label(None, "Could not match the recommendation to a forecast.", "rule")

    metric = forecast["metric"]
    if metric in truth.get("defect_columns", []):
        return Label(None, f"{metric} has a broken tracking feed; no trustworthy actual.", "rule")
    actual = truth["holdout"]["totals"].get(metric)
    latest = forecast.get("latest_value")
    if actual is None or not latest:
        return Label(None, f"No next-month actual for {metric}.", "rule")

    predicted = float(forecast["change_percent_next_month"])
    realized = (actual - latest) / latest * 100
    same_direction = (predicted > 0) == (realized > 0)
    correct = same_direction and abs(realized) >= MATERIAL_CHANGE_PERCENT
    return Label(
        correct,
        f"Predicted {predicted:+.1f}% next month; the held-back month moved {realized:+.1f}%.",
        "rule",
    )


def _forecast_title(forecast: dict[str, Any]) -> str | None:
    change = forecast.get("change_percent_next_month", 0)
    if abs(change) < MATERIAL_CHANGE_PERCENT:
        return None
    direction = "increase" if change > 0 else "decline"
    return f"Prepare for {_humanize(forecast['metric'])} {direction}"


def _label_data_quality(rec: dict[str, Any], truth: dict[str, Any], issues: list[dict]) -> Label:
    column = (rec.get("data") or {}).get("column")
    if column is None:
        issue = next((i for i in issues if i.get("description") and i["description"] in (rec.get("problem") or "")), None)
        if issue is None:
            return Label(None, "Could not match the recommendation to a quality issue.", "rule")
        column = issue.get("column")
    if column in truth.get("defect_columns", []):
        return Label(True, f"Flagged {column}, which has a planted tracking outage.", "rule")
    if column in truth.get("by_design_sparse_columns", []):
        return Label(False, f"Flagged {column}, which is blank by design.", "rule")
    return Label(False, f"Flagged {column}, which has no planted defect.", "rule")


# ── LLM judge ───────────────────────────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """You grade recommendations produced by an automated data-analysis product.

The product analysed a synthetic business dataset. You are given the dataset's complete
ground truth: how it was generated, what was deliberately planted, which columns are blank
by design, the true totals, and the real next month (`holdout`) that the product never saw.

Grade the recommendation's central factual claim:

- SUPPORTED: the claim is true according to the ground truth. A forward-looking claim
  (a projected increase or decline) is SUPPORTED when the holdout month really moved in
  that direction by at least 5% versus the last observed month; the exact size need not
  match. This is the same standard applied to the product's rule-based forecasts.
- NOT_SUPPORTED: the claim is false or contradicted by the ground truth. This includes
  treating ordinary variation as a meaningful event when the ground truth says no anomaly
  was planted, treating blank-by-design values as a data-quality problem, and citing
  numbers, trends, or rankings the ground truth does not match.
- UNVERIFIABLE: generic advice with no specific factual claim that could be checked.

Data gaps — read carefully, these two cases are opposites:
- Columns in `defect_columns` have a REAL data defect (see `defect_story`). A recommendation
  that flags missing or broken values in one of them as a data-quality problem is SUPPORTED.
- Only columns in `by_design_sparse_columns` are blank by design. Flagging those as a
  data-quality problem is NOT_SUPPORTED.
- If a data-quality claim does not name a column, identify it from
  `missing_percent_by_column` (e.g. "78.2% of values are missing" means the column whose
  missing percentage is about 78.2).

Also say which planted finding, if any, the recommendation correctly identifies:
"anomaly" (the planted anomaly record or its month), "data_defect" (a column listed in
defect_columns), or "none".

Respond with JSON only:
{"verdict": "SUPPORTED" | "NOT_SUPPORTED" | "UNVERIFIABLE",
 "planted_finding": "anomaly" | "data_defect" | "none",
 "reason": "one or two sentences"}"""

_RECOMMENDATION_FIELDS = ("title", "problem", "evidence", "expected_impact", "description")


def truth_for_judge(truth: dict[str, Any]) -> str:
    visible = {key: value for key, value in truth.items() if key not in {"scenario"}}
    return json.dumps(visible, indent=1, ensure_ascii=False, default=str)


JUDGE_FAILED_PREFIX = "Judge failed"
# Waits between attempts: judge calls share the analysis calls' rate limit.
_JUDGE_BACKOFF_SECONDS = (10, 30, 60)


async def judge_recommendation(
    client: Any, model: str, rec: dict[str, Any], truth_text: str, attempts: int = 4
) -> Label:
    recommendation = {field: rec.get(field) for field in _RECOMMENDATION_FIELDS if rec.get(field)}
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"GROUND TRUTH:\n{truth_text}\n\n"
                f"RECOMMENDATION:\n{json.dumps(recommendation, ensure_ascii=False)}"
            ),
        },
    ]
    error = ""
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(_JUDGE_BACKOFF_SECONDS[min(attempt, len(_JUDGE_BACKOFF_SECONDS)) - 1])
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            return parse_judge_payload(payload)
        except Exception as exc:  # network, rate limit, or malformed output
            error = str(exc)
    return Label(None, f"{JUDGE_FAILED_PREFIX} after {attempts} attempts: {error[:200]}", "judge")


def parse_judge_payload(payload: dict[str, Any]) -> Label:
    verdict = str(payload.get("verdict", "")).upper()
    finding = str(payload.get("planted_finding", "none")).lower()
    finding = finding if finding in {"anomaly", "data_defect", "none"} else "none"
    reason = str(payload.get("reason", ""))[:500]
    if verdict == "SUPPORTED":
        return Label(True, reason, "judge", finding)
    if verdict == "NOT_SUPPORTED":
        return Label(False, reason, "judge", "none")
    if verdict == "UNVERIFIABLE":
        return Label(None, reason, "judge", "none")
    raise ValueError(f"Unexpected judge verdict: {verdict!r}")
