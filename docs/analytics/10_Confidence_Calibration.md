# 10 — Confidence Calibration

How the confidence attached to every recommendation is measured, where the
measurement comes from, and what it can and can't tell you. Built 2026-09-11
to close the gap documented in [`08_AI_Analytics_and_Guardrails.md` §6](08_AI_Analytics_and_Guardrails.md#6-known-limitation-confidence-is-not-calibrated).

---

## 1. The problem

Every recommendation carries a confidence between 0 and 1. Until this change,
every one of those numbers was hand-set: `0.85 / 0.7 / 0.55` for AI
recommendations by priority tier, `0.9` for the data-quality rule, `0.78` for
the anomaly rule, and a history-and-noise formula for forecasts. None had been
checked against how often the recommendation turned out to be right.

A confidence is *calibrated* when recommendations shown at 0.8 are right about
80% of the time. Two signals now measure that:

1. **An offline benchmark** (§3) — synthetic datasets with planted ground
   truth, run through the production pipeline, every recommendation scored.
   Reproducible, runs before release, but synthetic.
2. **A production feedback loop** (§6) — owners mark recommendations helpful
   or not, each verdict stored with the confidence that was shown. Real, but
   a weaker label ("helpful" is not "correct") and needs volume.

## 2. How confidence is assigned now

Every recommendation is tagged with a `confidence_source`, and
`app/analytics/calibration.py` resolves its confidence:

| Source | Produced by | Hand-set default |
|---|---|---|
| `ai:high` / `ai:medium` / `ai:low` | `ai_service._normalize_recommendation`, by the model's priority tier | 0.85 / 0.70 / 0.55 |
| `rule:data_quality` | `recommendations._quality_recommendations` — first high/critical quality issue | 0.90 |
| `rule:anomaly` | `recommendations._anomaly_recommendations` — top-scoring anomaly | 0.78 |
| `rule:forecast` | `recommendations._forecast_recommendations` — forecast move of 5%+ | the forecast's own formula confidence |
| `rule:tracking` | "Track X regularly" fallback | 0.72 — never scored or calibrated: it makes no falsifiable claim |

If `app/analytics/calibration_table.json` holds a measured entry for the
source with at least `MIN_SAMPLES` (10) scored recommendations, that value is
used and the recommendation's `confidence_method` is `"measured"`; otherwise the
default is used and it is `"default"`. Both fields are stored on each
recommendation insight's `data`, so any number in the product can be traced to
where it came from. The table is committed and regenerated only by the
benchmark (§7); nothing is learned at runtime.

**Where this shows up:** recommendation confidence is stored and returned by
the API (`InsightResponse.confidence`), but the dashboard's recommendation
cards don't display it — the "Strong / Good signal" labels in
`insights-panel.tsx` apply to forecast and anomaly *insights*, whose
confidences are unchanged by this work. So the calibration changes what the
system records and exposes, not what a user currently reads on screen.

## 3. The offline benchmark

Code: `backend/evals/calibration/` (`benchmark.py`, `labels.py`,
`metrics.py`, `run_eval.py`). Tests: `backend/tests/test_calibration_eval.py`.

### 3.1 It runs the production path

Each dataset is written as a CSV and then processed exactly as an upload with
the upload screen's defaults would be:

1. `FileProcessor.clean_file` with `_cleaning_options({"mode": "clean"})` — the
   same helper `POST /analyses` uses, and the frontend's default (`cleaningMode
   = "clean"`, outliers kept, semantic cleanup on, fuzzy dedupe off).
2. `SemanticWrangler.canonicalize_cleaned_file`.
3. `compute_analysis` — pipeline steps 1–6, extracted from
   `AnalysisEngine._run_pipeline` in this change so the engine and the
   benchmark call one function. The engine keeps only the database work around
   it (progress updates and persistence).

Running the default *cleaning* path matters: without it, CSV date columns stay
`VARCHAR`, `generate_forecasts` finds no date column, and no forecast
recommendation is ever produced (§8).

### 3.2 Datasets with planted truth

`draw_scenarios` produces a seeded, balanced mix across four domains (outdoor
retail, online marketplace, B2B software, hotel group) and two grains
(weekly, monthly), 12–24 observed months each. Each dataset's generating
process is known, including:

| Truth | How it's planted | What a correct recommendation looks like |
|---|---|---|
| Genuine anomaly (50% of datasets) | One record's revenue/volume/customers scaled until it is verifiably the most extreme revenue record (\|z\| ≥ 3.5) | Flags that record (or its month) |
| Ordinary variation | High-noise datasets (lognormal σ = 0.3) produce z ≥ 3 records naturally | Not flagged as an event |
| Tracking outage (1/3) | The customers metric goes blank from a quarter of the way in — >70% null, so it survives cleaning's imputation threshold | Flagged as a data problem |
| Optional-by-design column (50%) | e.g. `promo_discount`, filled only when a promotion ran — also >70% null | *Not* flagged as a data problem |
| Next month | One month beyond the file is generated from the same process and held back | A forecast move of 5%+ that actually happens in that month |

Trend (−8% to +8% a month), seasonality (none, or a Nov–Dec peak) and noise
are drawn per dataset. Every dataset's ground truth is saved next to its
results in `results/raw/<dataset>.json`.

### 3.3 Labels

**Rule-based recommendations** are labeled deterministically
(`labels.label_rule_recommendation`):

| Source | Correct when | Not scored when |
|---|---|---|
| `rule:anomaly` | The flagged record matches the planted one on date and dimensions (or a flagged month contains it) and the flagged column was affected | — (with no planted anomaly, any flag is wrong) |
| `rule:data_quality` | The flagged column is a planted defect (an optional-by-design column is wrong) | — |
| `rule:forecast` | The held-back month moved in the predicted direction by at least 5% (the rule's own firing threshold), measured from the forecast's `latest_value` | The metric has a planted tracking outage (no trustworthy actual) |
| `rule:tracking` | — | Always |

**AI recommendations** are free text, so an LLM judge
(`labels.judge_recommendation`, temperature 0, JSON output) grades each
against the dataset's full ground truth — including the held-back month the
analysis never saw — as `SUPPORTED`, `NOT_SUPPORTED`, or `UNVERIFIABLE`
(generic advice with nothing checkable; excluded from scoring). The judge is
told explicitly that ordinary variation and blank-by-design values are not
problems.

**Checking the judge:** the judge also grades every rule-based recommendation,
where deterministic labels exist. Its agreement rate with those labels is
reported with the results — a direct measure of how far to trust it on the AI
recommendations, where no deterministic label exists.

### 3.4 Metrics

`metrics.py` is plain arithmetic, unit-tested:

- **Hit rate** per source, with a 95% Wilson interval (sound at small n).
- **Brier score** — mean squared gap between confidence and outcome, lower is
  better; **ECE** — sample-weighted gap between confidence and hit rate across
  confidence bins; a **reliability table**.
- **Recalibrated confidence** = the smoothed hit rate `(hits + 1) / (n + 2)`.
- **Recalibrated Brier, leave-one-dataset-out** — each recommendation is scored
  against the rate measured on every *other* dataset, so the improvement from
  recalibrating is never judged on the data it was fitted to.
- **Recall** on planted findings, for the rules and for the AI separately.

## 4. Results

The numbers in production come from the offline, rules-only run of 2026-09-11 (48 datasets,
178 scored recommendations; full report in
`backend/evals/calibration/results/REPORT.md`):

| Source | n (datasets) | Confidence before | Hit rate (95% CI) | Brier before → after (LOO) | Confidence now |
|---|---|---|---|---|---|
| `rule:forecast` | 98 (39) | 0.83 (formula, avg) | **0.72** (0.63–0.80) | 0.212 → 0.209 | 0.72 |
| `rule:anomaly` | 47 (47) | 0.78 | **0.49** (0.35–0.63) | 0.334 → 0.260 | 0.49 |
| `rule:data_quality` | 33 (33) | 0.90 | **0.48** (0.33–0.65) | 0.422 → 0.265 | 0.49 |
| `ai:high` / `ai:medium` / `ai:low` | — | 0.85 / 0.70 / 0.55 | **not measured** (see below) | — | unchanged defaults |

Across all scored recommendations the expected calibration error of the confidence *as
shown* was 0.21. Every rule source was overconfident, and the most confident one — the
data-quality rule at 0.90 — was the least accurate.

**What each number is actually saying:**

- **Forecasts (0.83 → 0.72).** About 11 points overconfident against the held-back month.
  Replacing the per-forecast formula with one measured constant barely changes the Brier
  score (0.212 → 0.209), which says the formula's variation (0.45–0.90 by history length
  and noise) wasn't carrying much information about which forecasts come true. Weekly data
  did better (0.78) than monthly (0.65).
- **Anomalies (0.78 → 0.49).** The rule is right 95% of the time when a genuine anomaly
  exists and found 23 of 24 — but it fired on 47 of 48 datasets, because some record is
  always 3+ standard deviations out. It can't say "nothing unusual here", so its hit rate is
  simply the share of datasets that really contain an anomaly — 50%, by construction of
  this benchmark (§5). Weekly datasets fared worse (0.30 vs 0.67 monthly): more rows means
  more natural extremes, often in other columns, outranking the planted record.
- **Data quality (0.90 → 0.49).** Perfect (1.00) on datasets without an optional column,
  0.29 on datasets with one. Recall was 16/16 — the rule catches every real outage — but
  a column that is blank by design looks identical to it, and cleaning's imputation leaves
  exactly those >70%-empty numeric columns behind. Telling them apart needs context the
  rule doesn't have (a schema annotation, or a user saying "this field is optional").

**Why the AI tiers are unmeasured.** The one paid run (gpt-4o analysis + gpt-4o judge)
was discarded — its summary is archived with the reasons in
`results/archive/2026-09-11_ai_run_rate_limited/`. In short: the key's rate limit produced
527 HTTP 429s, so 19 of 48 datasets fell back to the no-AI path, skewed toward the larger
weekly datasets; and the judge agreed with the deterministic labels on 39/39 anomaly and
70/70 forecast recommendations but only 13/26 data-quality ones, which traced to two
defects both since fixed (the recommendation didn't name its column; the judge prompt let
"known defect" read as "not a problem"). Its AI numbers — `ai:high` right 49% of the time
at 0.85, `ai:medium` 54% at 0.70 — suggest the same overconfidence, but are not reliable
enough to ship. The harness now backs off and retries on rate limits (`--retry-failed`,
and `--rejudge` to re-grade saved results), so the next run needs only a key with more
headroom or a lower `--concurrency`.

## 5. What the numbers can and can't tell you

- **Two of the three rates depend on the benchmark's mix.** The anomaly rate is the share
  of datasets with a genuine anomaly (50% here); the data-quality rate depends on how often
  optional-by-design columns appear (50%) relative to real outages (1/3). Real uploads have
  their own, unknown mix — if genuine anomalies are rarer, the anomaly rule is right even
  less often than 49%. The report splits every source by scenario so the rates can be
  reweighted. The forecast rate depends on the generating process (trend, seasonality and
  noise ranges) rather than on a mix, and is the most transferable of the three.
- **The data is synthetic** — four domains, tidy structure, known processes. Real files are
  messier in ways this doesn't test (mixed date formats, merged headers, free-text
  categories).
- **The scale is now mixed.** Measured rule confidences (0.49–0.72) sit next to unmeasured
  AI defaults (0.85 / 0.70 / 0.55). An AI "High" at 0.85 is not more trustworthy than a
  forecast at 0.72 — it is simply not measured yet. Each recommendation's
  `confidence_method` says which kind of number it carries.
- **"Correct" is a definition** (§3.3) — e.g. a forecast counts as right if the real move
  was in its direction and at least 5%, regardless of size.
- **Nobody reads these on screen today.** Recommendation cards don't display confidence, so
  this changes what's stored and returned by the API, not what users see (§2).
- **The production feedback loop is the fix for most of this.** Real verdicts come with
  real uploads' mix, messiness, and — eventually — enough volume per source (§6).

## 6. Production feedback loop

Built in the same change (migration `003_recommendation_feedback`):

- **UI:** each recommendation card on the owner's dashboard asks "Was this
  useful?" with 👍 / 👎 (click again to withdraw). Not shown on shared links.
  Optimistic update, rolled back with a toast on failure
  (`recommendations-panel.tsx`, `useRecommendationFeedback`).
- **API:** `PUT` / `DELETE /api/v1/analyses/{analysis_id}/insights/{insight_id}/feedback`
  — owner-only (404 for anyone else), recommendations only (422 otherwise),
  rate-limited, upserted atomically (`INSERT … ON CONFLICT DO UPDATE`).
  `GET /analyses/{id}` returns the owner's verdict per insight as
  `user_feedback`.
- **Table `recommendation_feedback`:** one row per (recommendation, user), with
  a `CHECK` on the verdict. Each row **snapshots** the recommendation's title,
  priority, confidence, `confidence_source` and `confidence_method` at the
  moment of the verdict. That matters because a re-run deletes and regenerates
  every insight: the feedback row's `insight_id` is then nulled (`ON DELETE
  SET NULL`) but the verdict stays joinable to the confidence the user was
  actually shown. Deleting the analysis or the user deletes their feedback
  (`CASCADE`) — the snapshot contains text derived from their data.
- **View `recommendation_calibration`:** per source — n, mean confidence
  shown, helpful rate, Brier score, first/last feedback time:

  ```sql
  SELECT * FROM recommendation_calibration ORDER BY n DESC;
  ```

"Helpful" is a proxy, not ground truth: a correct recommendation about a
problem the user already knew may be rated unhelpful, and an appealing wrong one
helpful. The benchmark measures correctness on synthetic data; the feedback
measures usefulness on real data. When the two disagree for a source, that
disagreement is itself the finding. Once a source has enough real verdicts,
its helpful rate is the better number to put in the calibration table — the
table's format doesn't care which signal produced it.

Tests: `backend/tests/test_recommendation_feedback.py` runs against real
Postgres (the CI service container; skipped when none is reachable) — upgrade
to head, upsert and update, withdrawal, ownership and type checks, the
snapshot surviving insight regeneration, and the view's arithmetic.

## 7. Re-running

From `backend/`, with the pinned environment (Python 3.12):

```bash
python -m evals.calibration.run_eval --no-ai          # offline, free: rule-based sources only
python -m evals.calibration.run_eval                  # + gpt-4o analysis and LLM judge (reads OPENAI_API_KEY)
python -m evals.calibration.run_eval --rescore        # recompute metrics from saved results, no API calls
python -m evals.calibration.run_eval --write-table    # also write app/analytics/calibration_table.json
```

Outputs: `evals/calibration/results/REPORT.md`, `summary.json`, and one
`raw/<dataset>.json` per dataset (ground truth, pipeline outputs, every
recommendation with its label and the judge's reason). The full run makes
roughly 50 analysis calls and 400 judge calls; on a low-tier OpenAI key keep
`--concurrency` at 1–2 and follow up with `--retry-failed` for any dataset that
still hit rate limits.

## 8. Other findings along the way

- **The data-quality recommendation didn't name its column** — "78.2% of values are
  missing", on a card with no field name. Fixed: it now reads "New Customers: 78.2% of
  values are missing" (`recommendations._quality_recommendations`, regression test in
  `test_recommendations.py`).
- **Rate limits degrade silently in production too.** When both OpenAI calls fail,
  `AIService` returns the deterministic summary and recommendations with no indication to
  the user — which is correct as a fallback, but under sustained 429s (19 of 48 datasets
  in the paid run) users would get a plainer dashboard with no explanation.
- **Without cleaning, forecasts never run.** On the raw-upload path CSV dates stay
  `VARCHAR`, so `generate_forecasts` finds no date column. The upload screen defaults to
  cleaning, so most users get forecasts — anyone who picks "raw" never does.
- **The semantic detector classified `marketing_spend` as a "country" dimension** on the
  demo dataset, removing it from the metrics.
- **LLM judges need the opposite cases spelled out.** "Known defect" and "blank by design"
  are opposites for grading, and the first judge prompt let one read as the other. The
  judge-vs-deterministic agreement check is what exposed it — worth keeping in any
  LLM-graded eval.
