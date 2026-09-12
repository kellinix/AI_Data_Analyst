# AI Analytics — What's Deterministic, What's the Model, and How Hallucination Is Constrained

The single most important architectural fact in this codebase is that **the
LLM is the last thing that runs, on data that's already correct** — never
the thing computing the numbers. This document draws the exact line between
"calculated" and "generated," lists every AI touchpoint, and enumerates the
concrete hallucination-prevention mechanisms actually implemented in code
(not just described in a system prompt).

---

## 1. Taxonomy — every calculation, classified

| Category | Definition | Modules |
|---|---|---|
| **Deterministic calculation** | A fixed formula over the data — same input always produces the same output, no model involved | `analytics/statistics.py`, `analytics/kpi_detector.py`, `analytics/forecasting.py` (OLS trend extrapolation), `analytics/anomaly_detection.py` (z-score), `analytics/data_quality.py`, `analytics/data_quality_checks.py` |
| **Rule-based logic** | If/then heuristics and keyword matching — deterministic, but editorial rather than statistical | `analytics/chart_selector.py` (chart-type heuristics), `analytics/semantic_detector.py` (column semantic typing), `analytics/recommendations.py` (rule-based recommendation generator), the KPI priority ranking (`kpi_detector.py:88-97`) |
| **Machine-computed, non-LLM** | Statistical/numerical methods beyond simple aggregation | Correlation (`CORR()`), percentile ranking (`CUME_DIST()`), linear regression (`np.polyfit`) — all deterministic once run, but "machine calculation" in the sense of a formula, not a lookup |
| **LLM-generated** | Natural-language content authored by GPT-4o at inference time — the only genuinely non-deterministic layer | `services/ai_service.py` (`generate_analysis`, `chat`), `services/semantic_wrangler.py` (display-label generation, category-value embedding clustering) |

**Everything a chart's *numbers* come from is deterministic.** The LLM never computes a KPI, a trend line, a correlation, or an anomaly score. It writes sentences about numbers that were already computed before it was called.

---

## 2. Every AI touchpoint, and what it's allowed to see

| Touchpoint | Trigger | Model call | Input | What it produces |
|---|---|---|---|---|
| **Analysis narrative** | Every completed analysis | `AIService.generate_analysis()` (`ai_service.py:35-330`) | The Profile JSON only — pre-computed stats, never raw rows | Executive summary, `layout_grid` (chart selection hints), recommendations |
| **Chat** | Every user message | `AIService.chat()` (`ai_service.py:332-393`) | Stored Profile JSON + stored `Insight` rows + last 10 messages of history | A conversational answer, optionally a chart spec |
| **Category-value merging** | Upload cleaning, if `semantic_categorical_merging` enabled (default on) | `SemanticWrangler.canonicalize_cleaned_file()` (`semantic_wrangler.py:77-169`) | Raw category text values (e.g. `"USA"`, `"U.S.A."`) via OpenAI `text-embedding-3-small` | A canonical mapping merging near-duplicate category labels |
| **Display-label generation** | Every analysis, Celery stage | `SemanticWrangler.build_display_metadata()` (`semantic_wrangler.py:257-324`) | Column names + semantic types (not row data) via a chat completion | Human-readable column/chart labels |

Two of these four touchpoints (narrative, chat) are what most people mean by "the AI" in this product. The other two are smaller, easy-to-miss enrichment calls — worth naming explicitly because "does the model ever see my data" has a different, more nuanced answer for category values (yes, individual category *text values* are embedded) than for the main analysis (no, only aggregates).

---

## 3. Why deterministic-first — the actual architectural reason, not a slogan

The `README.md`'s framing — *"The LLM receives only pre-computed statistics — it never touches raw data"* — is implemented as a real data-flow boundary, not a policy. Concretely:

1. **Speed**: `_build_stats_summary()` (`ai_service.py:395-403`) short-circuits to serializing an already-built Profile JSON dict. There's no query the model needs to wait on — every number it will reference was computed by DuckDB, in-process, before the model call starts.
2. **Accuracy**: an LLM asked to "calculate the month-over-month change" from a table of numbers in its context window can arithmetic-error. A model asked to *narrate* a number that DuckDB already computed with `SUM()`/`AVG()`/`CORR()` cannot get the arithmetic wrong, because it isn't doing arithmetic — it's paraphrasing a value.
3. **Security**: raw uploaded data never becomes part of any OpenAI API payload for the main analysis or chat calls. What leaves the server is aggregates: means, percentiles, correlation coefficients, top-10 category values (capped), KPI totals. This is a meaningfully smaller and more defensible data-exposure surface than "send the file to the model," and it's enforced structurally — the Profile JSON builder (`data_profile.py`) has no code path that serializes individual rows.

The ordering in the pipeline (`docs/analytics/01_Data_Architecture.md §3`, Stage C) makes this non-negotiable: forecasting, anomaly detection, and recommendations all run **before** the AI call, specifically so the model has something correct to describe rather than something to compute.

---

## 4. Hallucination-prevention techniques actually implemented

Six distinct mechanisms, in the order they'd catch a problem:

### 4.1 Structural grounding (the strongest control)
The model physically cannot invent a number "from the data" because it never receives the data — only the Profile JSON. Prompted instructions (§4.2) are a second line of defense; this is the first, and it doesn't depend on the model following instructions correctly.

### 4.2 Explicit anti-hallucination system prompt
Quoted directly from `ai_service.py:41-274`, not paraphrased:

> *"You must not invent facts, numbers, trends, labels, categories, columns, relationships, business causes, or financial estimates."* (line 50)
> *"Never invent columns, values, categories, date ranges, totals, averages, percentages, trends, causes, or relationships."* (rule 2, line 115)
> *"Do not overstate causation. Use cautious language unless the Profile JSON directly supports the cause."* (rule 12, line 125)
> *"If the Profile JSON does not contain enough information for a chart or recommendation, omit that chart or recommendation."* (rule 15, line 128)
> *"If dataset.sample_truncated is true in the Profile JSON, the executive_summary must note that the analysis covers a sample..."* (rule 20, line 132) — the model is required to disclose sampling, not silently generalize from a partial read.

This is a **prompted** constraint — it shapes what the model is likely to output, but nothing enforces it mechanically. That's what §4.3–4.5 are for.

### 4.3 Structured output schema
`_analysis_schema()` (`ai_service.py:515-570`) is passed to the OpenAI Responses API as a JSON Schema (`strict: False` — a hint, not hard mode). Every chart requires `chart_type` from an enum of 4 values; every recommendation requires `priority` from `{High, Medium, Low}`. A response that doesn't roughly conform is malformed JSON and fails to parse, dropping to the next fallback tier rather than reaching the user as-is.

### 4.4 Server-side sanitization — code-enforced, not prompted
This is the layer that actually matters most, because it runs regardless of whether the model followed instructions:

- **`_contains_unsafe_chart_value()`** (`ai_service.py:715-728`) recursively scans every chart option value for JS syntax (`=>`, `function(`, `new Date(`) and non-JSON literals (`regexp`, `undefined`, `NaN`, `Infinity`) as whole tokens — a chart containing any of these is **dropped entirely**, not sanitized-and-kept. *(Until 2026-09-11 this was a raw substring match, so `nan` inside ordinary labels like "Finance" or "Maintenance" silently dropped legitimate charts; found while writing `tests/test_ai_service.py`, now covered by a regression test.)*
- **`_normalize_recommendation()`** (`ai_service.py:627-662`) force-coerces `priority`/`difficulty` into their allowed enum values via case-insensitive matching, falling back to `"Medium"` rather than accepting an off-schema value.
- **`_parse_financial_opportunity()`** (`ai_service.py:673-704`) is a regex-based numeric extractor that returns `None` — not a fabricated number — for `"NA"` or any unparseable string, and honours K/M/B and thousand/million/billion suffixes (before 2026-09-11, `"$1.5M"` parsed as `1.5`). The model is explicitly instructed to write `"NA"` when it can't support a financial estimate (line 245); this parser is what makes that instruction actually load-bearing rather than aspirational.
- **Confidence is never model-reported**: `_normalize_recommendation()` tags each AI recommendation with a source by its priority tier (`ai:high` / `ai:medium` / `ai:low`) and `app/analytics/calibration.py` assigns the confidence — the benchmark-measured hit rate for that tier when one exists, otherwise the original hand-set lookup `{"High": 0.85, "Medium": 0.7, "Low": 0.55}`. The model never supplies the number, which closes off one specific hallucination path (a model claiming "97% confidence" with no basis). Whether the number now means anything is §6.

### 4.5 Prompted self-check (weakest layer — worth being honest about)
The system prompt ends with a `FINAL VALIDATION BEFORE RESPONDING` checklist (`ai_service.py:259-274`), including *"Validate that every number in the response exists in or is directly calculated from the Profile JSON"* and *"Validate that every chart uses real Profile JSON data."* This is the model being asked to check its own work — it's a real, reasonable prompting technique, and it's the **only** one of the six mechanisms here that has no code-level enforcement behind it. Listed last deliberately: a hallucination-prevention document that put this first would overstate how much of the guardrail is actually mechanical versus requested.

### 4.6 Graceful degradation instead of a forced answer
Three-tier fallback (`ai_service.py:282-330`): Responses API (75s) → Chat Completions API (45s) → a **fully deterministic** template summary with zero model involvement if both fail. The alternative design — retry until something, anything, comes back — is exactly how a system ends up displaying a low-quality or hallucinated response under time pressure. This system instead degrades to *less* narrative rather than *worse* narrative: `_fallback_summary()` (`ai_service.py:828-849`) is built entirely from row/column counts and the already-computed KPI list, and `recommendations` in that branch come from the deterministic rule-based engine, not an empty or invented list.

---

## 5. What's LLM-authored vs. deterministic, per dashboard element

| Dashboard element (`insights.type`) | Authored by | Notes |
|---|---|---|
| KPI summary tiles | Deterministic (`kpi_detector.py`) | Confidence hardcoded to `0.99` — not a model claim |
| Forecast cards | Deterministic (`forecasting.py`, OLS) | Confidence is a real formula (history + noise), see glossary §4 |
| Anomaly cards | Deterministic (`anomaly_detection.py`, z-score) | Confidence = `min(z_score/5, 0.95)` |
| AI insights | **LLM** (`ai_service.generate_analysis`) | The only insight type with no deterministic fallback content of its own — omitted entirely if the AI call fails all 3 tiers |
| Recommendations | **Both, merged** | Rule-based (`recommendations.py`) + AI-authored, deduplicated by evidence text (`analysis_engine.py:_merge_recommendations`) — a dashboard's Decision Feed is never purely one or the other |
| Executive summary | **LLM**, with a deterministic fallback | Template-based (`_fallback_summary`) if the AI call fails entirely |
| Chat responses | **LLM**, always | No deterministic fallback beyond a static error string — this is the one surface with no graceful-content degradation, only "the AI is unavailable" |

---

## 6. Confidence calibration — partly measured

Until 2026-09-11 every recommendation confidence was a hand-set constant or a formula, none measured against accuracy. That work is now done for the rule-based sources and built but not yet run cleanly for the AI tiers — full method, results and caveats in [`10_Confidence_Calibration.md`](10_Confidence_Calibration.md):

- **Measured and in production:** a planted-truth benchmark run through the production pipeline found every rule source overconfident — forecasts 0.83 → 0.72, anomalies 0.78 → 0.49, data quality 0.90 → 0.49 — and those measured values now replace the defaults via `app/analytics/calibration_table.json`.
- **Still unmeasured:** the AI tiers keep `{"High": 0.85, "Medium": 0.7, "Low": 0.55}`. The one paid run was rate-limited on 19 of 48 datasets and exposed a judge-prompt defect on data-quality claims, so it was archived rather than used; its indication (`ai:high` right 49% of the time) is consistent with the same overconfidence but not reliable enough to ship.
- **Production outcome signal:** owners can now mark each recommendation helpful or not; verdicts are stored with the confidence shown and aggregated per source by the `recommendation_calibration` view.

The model still never supplies its own confidence (§4.4).
