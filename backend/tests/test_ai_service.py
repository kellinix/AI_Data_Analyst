"""Tests for the guardrails in app.services.ai_service.

These cover the post-processing layer that docs/analytics/08_AI_Analytics_and_Guardrails.md
relies on: every LLM response is parsed, allow-listed, and sanitized before it
reaches the dashboard, and every failure path degrades to deterministic output
instead of raising. No test calls the real OpenAI API — the module-level client
is replaced with a fake.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import ai_service
from app.services.ai_service import (
    AIService,
    _build_chat_analysis_context,
    _coerce_analysis_json,
    _fallback_summary,
    _normalize_recommendation,
    _parse_financial_opportunity,
    _safe_chart_id,
    _sanitize_layout_grid,
)

# ── Fixtures / helpers ─────────────────────────────────────────────────────


def _chart(**overrides: Any) -> dict[str, Any]:
    chart = {
        "id": "revenue_by_month",
        "title": "Revenue by Month",
        "description": "Monthly revenue.",
        "grid_span": "col-span-12 md:col-span-8",
        "chart_type": "line",
        "echarts_option": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": ["Jan", "Feb"]},
            "yAxis": {"type": "value"},
            "series": [{"type": "line", "data": [100, 120]}],
        },
    }
    chart.update(overrides)
    return chart


def _recommendation(**overrides: Any) -> dict[str, Any]:
    rec = {
        "problem": "Returns are concentrated in one region",
        "evidence": "North accounts for 41% of returns.",
        "expected_impact": "Lower return costs.",
        "financial_opportunity": "NA",
        "priority": "High",
        "owner": "Operations Team",
        "difficulty": "Medium",
        "timeline": "30 Days",
    }
    rec.update(overrides)
    return rec


class _FakeOpenAI:
    """Stands in for AsyncOpenAI. Each outcome is a return value or an exception."""

    def __init__(self, responses_outcome: Any = None, chat_outcome: Any = None):
        self._responses_outcome = responses_outcome
        self._chat_outcome = chat_outcome
        self.responses_calls: list[dict[str, Any]] = []
        self.chat_calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._responses_create)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat_create))

    async def _responses_create(self, **kwargs: Any) -> Any:
        self.responses_calls.append(kwargs)
        if isinstance(self._responses_outcome, BaseException):
            raise self._responses_outcome
        return self._responses_outcome

    async def _chat_create(self, **kwargs: Any) -> Any:
        self.chat_calls.append(kwargs)
        if isinstance(self._chat_outcome, BaseException):
            raise self._chat_outcome
        return self._chat_outcome


def _chat_completion(content: str | None, usage: Any = None) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


def _analysis(**overrides: Any) -> Any:
    fields = {
        "name": "sales.csv",
        "row_count": 936,
        "column_count": 12,
        "metadata_": {},
        "summary": None,
        "insights": [],
        "charts": [],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


# ── Response parsing ───────────────────────────────────────────────────────


def test_coerce_analysis_json_normalizes_a_valid_response():
    content = json.dumps(
        {
            "executive_summary": "Revenue grew 20% month over month.",
            "layout_grid": [_chart()],
            "recommendations": [_recommendation(), "not a dict", 42],
        }
    )

    result = _coerce_analysis_json(content)

    assert result["executive_summary"] == "Revenue grew 20% month over month."
    assert [chart["id"] for chart in result["layout_grid"]] == ["revenue_by_month"]
    # Non-dict recommendation entries are dropped, not passed through.
    assert len(result["recommendations"]) == 1
    assert result["insights"] == []


def test_coerce_analysis_json_tolerates_missing_keys():
    result = _coerce_analysis_json("{}")

    assert result == {
        "executive_summary": "",
        "layout_grid": [],
        "insights": [],
        "recommendations": [],
    }


def test_coerce_analysis_json_raises_on_invalid_json():
    """Invalid JSON must raise so generate_analysis falls through to the next path."""
    with pytest.raises(json.JSONDecodeError):
        _coerce_analysis_json("```json\n{not json}\n```")


# ── Chart sanitization ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"chart_type": "radar"},
        {"chart_type": "3d_bar"},
        {"grid_span": "col-span-3"},
        {"echarts_option": "not an object"},
        {"echarts_option": None},
    ],
)
def test_sanitize_layout_grid_drops_charts_outside_the_allow_list(overrides):
    assert _sanitize_layout_grid([_chart(**overrides)]) == []


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "function (params) { return params.value; }",
        "(v) => v * 100",
        "v=>v*2",
        "new Date()",
        "new RegExp('x')",
        "undefined",
        "NaN",
        "-Infinity",
    ],
)
def test_sanitize_layout_grid_drops_charts_with_executable_or_non_json_values(unsafe_value):
    option = {"tooltip": {"formatter": unsafe_value}, "series": [{"type": "bar", "data": [1]}]}

    assert _sanitize_layout_grid([_chart(echarts_option=option)]) == []


def test_sanitize_layout_grid_checks_nested_lists_for_unsafe_values():
    option = {"series": [{"type": "bar", "data": [1, 2, "() => 3"]}]}

    assert _sanitize_layout_grid([_chart(echarts_option=option)]) == []


def test_sanitize_layout_grid_keeps_template_string_formatters():
    option = {"tooltip": {"formatter": "{b}: {c}"}, "series": [{"type": "pie", "data": [1]}]}

    result = _sanitize_layout_grid([_chart(chart_type="pie", echarts_option=option)])

    assert len(result) == 1


def test_sanitize_layout_grid_deduplicates_ids_and_caps_at_six():
    charts = [_chart(id="Revenue Trend") for _ in range(8)]

    result = _sanitize_layout_grid(charts)

    assert len(result) == 6
    ids = [chart["id"] for chart in result]
    assert len(set(ids)) == 6
    assert ids[0] == "revenue_trend"


def test_sanitize_layout_grid_ignores_non_list_and_non_dict_input():
    assert _sanitize_layout_grid("not a list") == []
    assert _sanitize_layout_grid([None, "chart", 3]) == []


def test_sanitize_layout_grid_strips_unknown_fields():
    result = _sanitize_layout_grid([_chart(onclick="alert(1)")])

    assert "onclick" not in result[0]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Revenue by Month!", "revenue_by_month"),
        ("  --  ", "chart"),
        ("A__B  C", "a_b_c"),
    ],
)
def test_safe_chart_id(raw, expected):
    assert _safe_chart_id(raw) == expected


@pytest.mark.parametrize(
    "labels",
    [
        ["Finance", "Maintenance", "Sales"],
        ["Nancy", "Renew date", "Functional area", "Undefinedness"],
    ],
)
def test_sanitize_layout_grid_keeps_ordinary_labels_containing_unsafe_substrings(labels):
    """Regression: the filter used to substring-match, so 'nan' inside 'Finance'
    silently dropped the whole chart."""
    option = {
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": list(range(len(labels)))}],
    }

    assert len(_sanitize_layout_grid([_chart(chart_type="bar", echarts_option=option)])) == 1


# ── Recommendation normalization ───────────────────────────────────────────


def test_normalize_recommendation_maps_llm_schema_to_card_shape():
    result = _normalize_recommendation(_recommendation())

    assert result["title"] == "Returns are concentrated in one region"
    assert result["importance"] == "high"
    assert result["data"]["owner"] == "Operations Team"
    assert result["data"]["difficulty"] == "medium"
    assert result["data"]["estimated_completion"] == "30 Days"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("high", "High"), ("  LOW ", "Low"), ("Critical", "Medium"), (None, "Medium")],
)
def test_normalize_recommendation_coerces_priority_to_allowed_values(raw, expected):
    assert _normalize_recommendation(_recommendation(priority=raw))["data"]["priority"] == expected


def test_normalize_recommendation_falls_back_to_default_confidence_by_priority():
    """With no measured calibration entry, confidence is the hand-set per-tier
    default. Measured overrides are covered in test_calibration.py."""
    results = {
        priority: _normalize_recommendation(_recommendation(priority=priority))
        for priority in ("High", "Medium", "Low")
    }

    assert {p: r["confidence"] for p, r in results.items()} == {
        "High": 0.85,
        "Medium": 0.7,
        "Low": 0.55,
    }
    assert {p: r["confidence_source"] for p, r in results.items()} == {
        "High": "ai:high",
        "Medium": "ai:medium",
        "Low": "ai:low",
    }
    assert all(r["confidence_method"] == "default" for r in results.values())


def test_normalize_recommendation_defaults_missing_fields():
    result = _normalize_recommendation({})

    assert result["title"] == "Review analysis finding"
    assert result["data"]["owner"] == "Leadership Team"
    assert result["data"]["estimated_completion"] == "30 Days"


def test_normalize_recommendation_hides_financial_opportunity_when_not_calculable():
    result = _normalize_recommendation(_recommendation(financial_opportunity="NA"))

    assert result["show_financial_opportunity"] is False
    assert result["financial_opportunity"] == 0
    assert result["data"]["financial_opportunity"] is None
    assert result["data"]["financial_opportunity_raw"] == "NA"


def test_normalize_recommendation_passes_deterministic_cards_through_unchanged():
    deterministic = {"title": "Review Chol", "importance": "medium", "data": {"x": 1}}

    assert _normalize_recommendation(deterministic) is deterministic


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (12500, 12500.0),
        (99.5, 99.5),
        ("12,500", 12500.0),
        ("$12,500 per quarter", 12500.0),
        ("-3,200.50", -3200.5),
        ("$1.5M", 1_500_000.0),
        ("£750k recoverable", 750_000.0),
        ("2.4 billion", 2_400_000_000.0),
        ("$3bn in annual revenue", 3_000_000_000.0),
        ("USD 12 million", 12_000_000.0),
        ("1.2 mm", 1_200_000.0),
        ("5 months of lost sales", 5.0),
        ("NA", None),
        ("na", None),
        ("", None),
        (None, None),
        ("Not directly calculable", None),
    ],
)
def test_parse_financial_opportunity(raw, expected):
    assert _parse_financial_opportunity(raw) == expected


# ── generate_analysis: primary path and fallbacks ──────────────────────────


_PROFILE_STATS = {
    "row_count": 936,
    "column_count": 12,
    "profile_json": {"dataset": {"row_count": 936}, "metrics": {"kpis": []}},
    "deterministic_recommendations": [{"title": "Deterministic card", "evidence": "z=4.6"}],
}


async def test_generate_analysis_uses_responses_api_with_strict_schema(monkeypatch):
    payload = {"executive_summary": "OK.", "layout_grid": [_chart()], "recommendations": []}
    fake = _FakeOpenAI(responses_outcome=SimpleNamespace(output_text=json.dumps(payload)))
    monkeypatch.setattr(ai_service, "client", fake)

    result = await AIService().generate_analysis("sales.csv", _PROFILE_STATS, [])

    assert result["executive_summary"] == "OK."
    assert len(result["layout_grid"]) == 1
    assert result["generation"] == {"status": "ai"}
    assert fake.chat_calls == []
    request = fake.responses_calls[0]
    assert request["text"]["format"]["type"] == "json_schema"
    # The Profile JSON is sent as the canonical source of truth.
    user_prompt = request["input"][1]["content"]
    assert "PROFILE JSON - canonical analysis source of truth" in user_prompt


async def test_generate_analysis_falls_back_to_chat_completions(monkeypatch):
    payload = {"executive_summary": "From fallback.", "layout_grid": [], "recommendations": []}
    fake = _FakeOpenAI(
        responses_outcome=RuntimeError("responses API unavailable"),
        chat_outcome=_chat_completion(json.dumps(payload)),
    )
    monkeypatch.setattr(ai_service, "client", fake)

    result = await AIService().generate_analysis("sales.csv", _PROFILE_STATS, [])

    assert result["executive_summary"] == "From fallback."
    assert result["generation"] == {"status": "ai"}
    assert fake.chat_calls[0]["response_format"] == {"type": "json_object"}


async def test_generate_analysis_falls_back_when_primary_returns_invalid_json(monkeypatch):
    payload = {"executive_summary": "Recovered.", "layout_grid": [], "recommendations": []}
    fake = _FakeOpenAI(
        responses_outcome=SimpleNamespace(output_text="Sure! Here's your dashboard:"),
        chat_outcome=_chat_completion(json.dumps(payload)),
    )
    monkeypatch.setattr(ai_service, "client", fake)

    result = await AIService().generate_analysis("sales.csv", _PROFILE_STATS, [])

    assert result["executive_summary"] == "Recovered."


async def test_generate_analysis_degrades_to_deterministic_output_when_llm_fails(monkeypatch):
    fake = _FakeOpenAI(
        responses_outcome=RuntimeError("down"),
        chat_outcome=TimeoutError("down"),
    )
    monkeypatch.setattr(ai_service, "client", fake)

    result = await AIService().generate_analysis("sales.csv", _PROFILE_STATS, [])

    assert result["layout_grid"] == []
    assert result["recommendations"] == _PROFILE_STATS["deterministic_recommendations"]
    assert "936 rows across 12 columns" in result["executive_summary"]
    # The dashboard reads this to tell the user the narrative is automatic.
    assert result["generation"] == {"status": "fallback", "error_type": "TimeoutError"}


async def test_generate_analysis_does_not_raise_when_client_is_unavailable(monkeypatch):
    monkeypatch.setattr(ai_service, "client", None)

    result = await AIService().generate_analysis("sales.csv", _PROFILE_STATS, [])

    assert result["layout_grid"] == []
    assert result["recommendations"] == _PROFILE_STATS["deterministic_recommendations"]


# ── Stats summary sent to the model ────────────────────────────────────────


def test_build_stats_summary_without_profile_json_formats_kpis_and_stats():
    statistics = {
        "row_count": 1000,
        "column_count": 3,
        "numeric_stats": {"revenue": {"mean": 10, "min": 1, "max": 50, "total": 10000}},
        "data_quality": {"score": 88, "issues": [{"description": "5% missing region"}]},
    }
    kpis = [{"column": "total_revenue", "value": 10000, "is_currency": True}]

    summary = AIService()._build_stats_summary(statistics, kpis)

    assert "Rows: 1,000" in summary
    assert "Total Revenue: $10,000.00" in summary
    assert "revenue: mean=10.00" in summary
    assert "DATA QUALITY SCORE: 88/100" in summary
    assert "5% missing region" in summary


# ── Chat ───────────────────────────────────────────────────────────────────


async def test_chat_grounds_prompt_in_analysis_and_truncates_history(monkeypatch):
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30)
    fake = _FakeOpenAI(chat_outcome=_chat_completion("North leads returns.", usage))
    monkeypatch.setattr(ai_service, "client", fake)
    history = [{"role": "user", "content": f"message {i}"} for i in range(15)]

    result = await AIService().chat(
        _analysis(summary="Returns concentrated in North."), history, "Which region?"
    )

    assert result["content"] == "North leads returns."
    assert result["metadata"] == {"prompt_tokens": 120, "completion_tokens": 30}
    messages = fake.chat_calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "Returns concentrated in North." in messages[0]["content"]
    assert "Never make up numbers" in messages[0]["content"]
    # system + last 10 history messages + the new user message
    assert len(messages) == 12
    assert messages[1]["content"] == "message 5"
    assert messages[-1] == {"role": "user", "content": "Which region?"}


async def test_chat_returns_friendly_error_instead_of_raising(monkeypatch):
    monkeypatch.setattr(ai_service, "client", _FakeOpenAI(chat_outcome=RuntimeError("down")))

    result = await AIService().chat(_analysis(), [], "Hello?")

    assert result == {
        "content": "I encountered an error. Please try again.",
        "chart_config": None,
        "metadata": {},
    }


async def test_chat_handles_empty_model_content(monkeypatch):
    monkeypatch.setattr(ai_service, "client", _FakeOpenAI(chat_outcome=_chat_completion(None)))

    result = await AIService().chat(_analysis(), [], "Hello?")

    assert result["content"] == "I couldn't generate a response."
    assert result["metadata"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_chat_context_reports_when_no_metadata_exists():
    assert _build_chat_analysis_context(_analysis()) == (
        "No computed analysis metadata is available yet."
    )


def test_chat_context_includes_profile_quality_and_ordered_insights():
    insights = [
        SimpleNamespace(sort_order=2, type="trend", title="Second", description="b"),
        SimpleNamespace(sort_order=1, type="anomaly", title="First", description="a"),
    ]
    analysis = _analysis(
        metadata_={
            "data_profile": {
                "dataset": {"row_count": 936, "column_count": 12},
                "metrics": {"kpis": [{"column": "revenue", "value": 5000, "type": "sum"}]},
            },
            "data_quality": {"score": 91, "issues": [{"description": "3 duplicate rows"}]},
        },
        insights=insights,
    )

    context = _build_chat_analysis_context(analysis)

    assert "Profile JSON: 936 rows, 12 columns" in context
    assert "revenue: 5000 (sum)" in context
    assert "Data quality score: 91/100" in context
    assert context.index("First") < context.index("Second")


# ── Deterministic fallback summary ─────────────────────────────────────────


def test_fallback_summary_discloses_sampling():
    summary = _fallback_summary(
        {"row_count": 250_000, "column_count": 8, "sample_truncated": True, "sample_row_limit": 100_000},
        [],
    )

    assert "sample of the first 100,000 rows" in summary


@pytest.mark.parametrize(
    ("score", "phrase"),
    [(97, "did not find major data quality issues"), (80, "found data quality items to review")],
)
def test_fallback_summary_reflects_quality_score(score, phrase):
    summary = _fallback_summary({"row_count": 10, "column_count": 2, "data_quality": {"score": score}}, [])

    assert phrase in summary


def test_fallback_summary_lists_key_measures():
    kpis = [
        {"column": "total_revenue", "value": 12500.0, "is_currency": True},
        {"column": "return_pct", "value": 4.5, "is_percent": True},
    ]

    summary = _fallback_summary({"row_count": 10, "column_count": 2}, kpis)

    assert "Total Revenue at $12,500.00" in summary
    assert "a return % rate of 4.5%" in summary
