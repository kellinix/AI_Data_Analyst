# Verification Log

What was actually run to confirm this review didn't change application
behavior, what environment problems that hit along the way, and what the
final, complete test run showed.

---

## 1. Result

```
112 passed in 5.84s
```

Full suite (15 pre-existing test files + the new `test_data_quality_checks.py`), run clean, zero failures, after resolving the environment issue in §2. This is the real number — not an estimate, and not a partial run.

## 2. The environment problem this review found (not caused)

Neither `backend/requirements.txt` nor `requirements-dev.txt` were installed in any available Python environment at the start of this review. Getting to a working test environment took multiple attempts and surfaced a genuine, specific compatibility problem worth documenting on its own merits:

**Root cause: the ambient system Python was 3.14; this project pins dependency versions that predate Python 3.14 wheel support, and several of them (`pydantic-core`, `duckdb`, `pyarrow`, `asyncpg`, `Pillow`, and transitively `scipy`) have no prebuilt wheel for `cp314` at their pinned versions.** `scipy==1.15.3` additionally fails to *build* from source on this machine because compiling it requires a Fortran compiler (`gfortran`/`ifort`/etc.), none of which are installed — and it turned out to be moot, since `scipy` isn't imported anywhere in the actual application code (confirmed by `grep -r "^import scipy\|from scipy" backend/app` returning nothing). `pydantic-core==2.33.2` fails to build for a more fundamental reason: its Rust extension (`pyo3`) explicitly refuses to compile against Python 3.14, since PyO3 0.24.1's maximum supported version is 3.13.

Because `pip install -r requirements.txt` resolves and builds every package in one transaction, **a single unbuildable package aborts the entire install** — including packages that would have installed fine individually. This is why early attempts appeared to install successfully (`exit code 0` on a truncated log) while `fastapi`, `pandas`, etc. remained unimportable: the batch failed on `pydantic-core`/`scipy`/etc. partway through and installed nothing new in that run.

**Resolution used for this review**: installed each blocked package individually at its latest (unpinned) version instead of the pinned one — every one of them has a `cp314` wheel at latest. This is a verification workaround, not a code change: nothing in `requirements.txt` was edited.

**A second, separate issue** surfaced once imports succeeded: `app/core/config.py` instantiates `Settings()` at **module import time** (`config.py:214-217`), which requires `SECRET_KEY`, `POSTGRES_PASSWORD`, and `OPENAI_API_KEY` to already be set as environment variables. `backend/tests/conftest.py` sets safe test values for exactly these fields, but via `monkeypatch.setenv` inside an `autouse` **fixture** — which only runs at test-execution time, after collection/import has already happened. And `backend/.env` doesn't exist (only a repo-root `.env`, in a different working directory than where `pytest` is documented to run from). The net effect: **`pytest` cannot even *collect* the test modules that import `app.core.config` without environment variables being set some other way first** — `conftest.py`'s protection doesn't reach far enough back. Worked around here by exporting the same non-secret values `conftest.py` already defines, directly in the shell, before invoking `pytest` — no real credentials were needed or used anywhere in this verification.

### Recommended fixes (not made in this pass — all three since applied, see §5)

1. Either relax the `requirements.txt` pins to ranges that resolve to `cp314`-compatible versions, or pin the project to Python 3.12/3.13 explicitly in a `.python-version` file / CI matrix and document that as the *only* supported version — right now nothing in the repo states a hard upper bound, so a contributor on a newer Python has no signal they're off the supported path until pip fails deep into a build log.
2. Drop `scipy` from `requirements.txt` — it's unused.
3. Ship a `backend/.env.example`-derived `backend/.env` for local test runs, or move the safe test defaults from `conftest.py`'s fixture into a `pytest_configure` hook / a `.env.test` loaded before collection, so `pytest` works out of the box from a clean clone without a contributor needing to reverse-engineer this chain first.

## 3. What was verified, and how

| Change | Verified by |
|---|---|
| Full pre-existing suite + new tests | `pytest backend/tests/` → **112 passed, 0 failed** (see §1) |
| `data_quality_checks.py` (new module) | Included in the 112; standalone run also confirmed 20/20 passed in isolation |
| `data_quality_report.py` CLI (new script) | Run directly against `backend/scripts/demo_data/northwind_outfitters_sales.csv`; output inspected manually and committed as `backend/scripts/demo_data/sample_data_quality_report.md`/`.json` |
| `sql_utils.py` consolidation (5 duplicate `_quote_identifier` definitions → 1 shared import) | `test_data_quality.py`, `test_statistics.py`, `test_anomaly_detection.py`, `test_chart_selector.py` (via `chart_selector` → `kpi_detector` path), and `test_live_filter.py` — the five modules whose local `_quote_identifier` definitions were removed — all pass in the full run. `grep -rn "def _quote_identifier\|def quote_identifier" backend/app` returns exactly one definition, in `sql_utils.py` |
| `semantic_wrangler.py` silent-except fix | `test_semantic_wrangler.py` passes; control flow (`continue` on exception) is unchanged, only a `logger.debug(...)` call was added before it |
| `insights.py` / `sandboxed_code_executor.py` docstring additions | No code logic touched; `test_sandboxed_code_executor.py` passes |
| README.md, all `docs/analytics/*.md`, `ANALYTICS_PORTFOLIO_REPORT.md` | Documentation only, no runtime code |

## 4. Reproducing this

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Python 3.12, per backend/.python-version
pip install -r requirements.txt -r requirements-dev.txt
pytest -q   # no env vars needed — tests/conftest.py seeds safe test values before collection
```

## 5. Follow-up: install/test fixes and `ai_service.py` coverage (2026-09-11)

All three §2 recommendations were applied, and the AI guardrail layer got the test coverage it was missing:

| Change | Detail |
|---|---|
| `scipy` removed from `requirements.txt` | Unused — no imports anywhere in `backend/app`. |
| `backend/.python-version` → `3.12` | Matches `docker/backend.Dockerfile` (`python:3.12-slim`) and CI (`python-version: "3.12"`). This makes the supported version explicit; it does not make the pinned dependencies build on 3.14. |
| `tests/conftest.py` seeds test env at import time | The same safe values the `isolate_env` fixture already used are written with `os.environ.setdefault` when `conftest.py` loads, which is before test modules are collected — so `Settings()` can be built at import. `setdefault` means CI- or shell-provided values still win. **Before:** with `SECRET_KEY`/`POSTGRES_PASSWORD`/`OPENAI_API_KEY` unset, `pytest` aborted with 8 collection errors. **After:** it collects and runs. |
| `tests/test_ai_service.py` (new, 67 tests) | Response parsing, chart allow-listing and executable-value filtering, recommendation normalization (including pinning the fixed confidence lookup, §6 of `08_AI_Analytics_and_Guardrails.md`), the Responses API → Chat Completions → deterministic fallback chain, and chat grounding — all against a fake OpenAI client, no network. |
| Two bugs found by those tests, fixed in `ai_service.py` | (1) `_contains_unsafe_chart_value()` substring-matched its blocklist, so `nan` inside labels like "Finance" or "Maintenance" silently dropped legitimate charts — it now matches JS syntax and literals as whole tokens. (2) `_parse_financial_opportunity("$1.5M")` returned `1.5` — it now honours K/M/B and thousand/million/billion suffixes. Both have regression tests. |

**Verification — fresh venv, Python 3.12.7, pinned `requirements.txt` only (none of the §2 per-package workarounds):**

```
pip install -r requirements.txt -r requirements-dev.txt   → exit 0
pip check                                                 → No broken requirements found
pytest -q          (no env vars exported)                 → 179 passed
ruff check .                                              → All checks passed!
mypy app --ignore-missing-imports                         → Success: no issues found in 58 source files
```

The same suite also passes (179 passed) in the Python 3.14 environment from §2. **Not verified here:** the Docker image build and a CI run on these changes.

## 6. Follow-up: confidence calibration and recommendation feedback (2026-09-11)

What changed is documented in `10_Confidence_Calibration.md`; this section records how it was checked.

| Change | Verified by |
|---|---|
| `compute_analysis` extracted from `AnalysisEngine._run_pipeline` | Full suite, including `test_live_filter.py`'s regression test on the engine's chart-population path (kept as a thin wrapper); the benchmark and `test_calibration_eval.py` call the extracted function end to end on real generated files |
| `app/analytics/calibration.py` + `calibration_table.json` | `tests/test_calibration.py` — defaults without a table, measured values with one, every malformed-entry fallback, source tagging on AI and rule recommendations, and a check that the committed table is valid. An autouse fixture in `conftest.py` points all other tests at an empty table so they stay deterministic whatever the committed table holds |
| Migration `003_recommendation_feedback` | Against a throwaway Postgres 16 (`postgres:16-alpine` on port 5433): `alembic upgrade head` → `downgrade 002_add_share_token` → `upgrade head`, all clean; `\d recommendation_feedback` shows the CHECK, the unique constraint, and the SET NULL / CASCADE foreign keys |
| Feedback endpoints, `user_feedback` on `GET /analyses/{id}`, the `recommendation_calibration` view | `tests/test_recommendation_feedback.py` — 9 tests against that real database through the ASGI app (no mocked session): upsert and change, withdrawal, ownership (404), type check (422), invalid verdict, auth required (401), snapshot surviving insight deletion, and the view's arithmetic |
| Benchmark harness (`backend/evals/calibration/`) | `tests/test_calibration_eval.py` — 27 tests: metrics against hand-computed values, generator determinism and that planted truth really holds (the planted anomaly is the max-\|z\| record; both gap types exceed cleaning's 70% null threshold; the holdout month is absent from the file), every label rule, judge-output parsing, and one dataset end to end through cleaning + `compute_analysis` offline |
| Frontend feedback control | `npm run type-check`, `npm run lint` (one pre-existing `<img>` warning, unrelated), and `npm run build` — all routes compile |

```
pytest -q  (Python 3.12 venv, POSTGRES_PORT=5433, nothing else exported)  → 229 passed
ruff check .                                                             → All checks passed!
mypy app --ignore-missing-imports                                        → no issues in 61 source files
```

A bug found while wiring the endpoint: with `from __future__ import annotations`, slowapi's `@limiter.limit` wrapper makes FastAPI resolve annotations against slowapi's module, which broke route registration at import ("204 must not have a response body"). The new endpoint module omits that import, as `analyses.py` already does, and says why in its docstring.

CI on the pull request: backend (229 passed, the 9 feedback tests running against the CI Postgres service, none skipped) and frontend build both green.

## 7. End-to-end test of the running app (2026-09-11)

The full local stack (Docker backend, Celery worker, Postgres, Redis; `next dev` frontend) was driven the way a user would drive it, with the demo CSV and the upload screen's default cleaning.

**API, as a programmatic user** — upload → analyse → rate → withdraw → re-run, checking each step in the API and directly in Postgres: **21/22 checks passed.** Recommendations carried their `confidence_source`; a rule-based forecast recommendation arrived at the measured 0.72; `PUT` upserted without duplicates; invalid verdicts and non-recommendation insights got 422; `DELETE` withdrew; after the re-run both verdicts survived with `insight_id` nulled and the snapshot intact, the regenerated recommendations started unrated, and `recommendation_calibration` aggregated the rows. The one failure was a test artifact (the test user's `@example.test` email — see below).

**Browser, as a logged-in user** (headless Chromium, a temporary Supabase test user) — log in → upload → wait for the dashboard → 👍 one card, 👎 another → reload → withdraw → re-analyse from the header menu: **11/11 checks passed**, no console errors. Both verdicts showed as pressed with "Thanks for the feedback", persisted across the reload, and the re-analysed cards started unrated; Postgres confirmed the verdicts outlived the re-analyse. The test users, their analyses and uploaded files were deleted afterwards.

**Bugs found and fixed** (both present on `main`; regression tests added, suite now 231):

| Bug | Effect | Fix |
|---|---|---|
| `anomaly_detection.py` put DuckDB `DATE` cells (`datetime.date`) into anomaly `context`, which is stored in JSONB | **Every cleaned upload with a date column and an outlier failed to save** — the default path, including the repo's own demo CSV | Context values converted with `isoformat()` (`_json_safe`); `test_context_values_are_json_serializable` |
| `AnalysisEngine.run` called `_mark_failed` on a session left unusable by the failed flush | The failure handler itself raised `PendingRollbackError`, so the analysis **stayed "processing 90%" forever** with no error shown | Roll back before marking failed; `test_analysis_engine.py` |

**Environment problems:** on **Node 25** the server has a `localStorage` object whose methods are undefined, and every `next dev` page returned 500 (`localStorage.getItem is not a function`). A preload script that logged a stack on each server-side `localStorage` read traced it to **Next's own dev overlay** (`react-dev-overlay/…/preferences.js`, `getInitialScale`) — dev-only, not app code. And `next dev` run from `frontend/` reads only `frontend/.env*`, not the repo-root `.env`, so without a `frontend/.env.local` the Supabase middleware had no URL and every page returned 500 (documented in the README).

**Found during testing, then fixed** (regression tests in `test_api_contracts.py` and `test_ai_service.py`):

| Problem | Fix |
|---|---|
| **Login and register forms could put credentials in the URL.** `<form onSubmit>` with no `method` meant a submit before React hydrated fell back to a native GET — `/login?email=…&password=…`, into browser history and server logs. Seen for real during testing. | `method="post"` on both forms (`login-form.tsx`, `register-form.tsx`) |
| **Shared links and `/api/openapi.json` were broken** (500; `/api/docs` didn't load). `public.py` combined `from __future__ import annotations` with `@limiter.limit`, so its `db: DB` dependency became an unresolvable query parameter. Present on `main`. | Drop the future import there, as `analyses.py` does |
| **`/users/me` returned 500 for reserved-domain emails** (e.g. `@example.test`), which Supabase accepts at sign-up but `EmailStr` rejects. | Response models echo the stored email as `str`; sign-up input is still validated |
| **AI failures were invisible to users** — the dashboard silently showed the deterministic summary. | `generate_analysis` reports `generation.status` (`ai` / `fallback`), persisted as `metadata.ai_generation`; the dashboard shows a notice on fallback |
| **Node 25 broke `next dev`** — Next's dev overlay reads Node 25's non-functional server `localStorage`. | `npm run dev` now runs `frontend/scripts/dev.mjs`, which adds `--no-experimental-webstorage` only on Node 25+ (the flag doesn't exist on Node 20, which CI uses). The auth store's `persist` was also made browser-only, defensively |

## 8. Real-data test: UK government major projects portfolio (2026-09-12)

Six IPA *Government Major Projects Portfolio* spreadsheets (MOD, DFT, HO, DFE, DHSC, DCMS; March 2024) were uploaded and combined through the product's own UI with default cleaning — 118 rows, 20 columns. The dashboard it produced was confidently wrong, and every cause sat in the deterministic layer *before* any AI call. This section records the diagnosis; each fix has a regression test built from these files.

**What the dashboard showed:** KPI tiles reading "Departmental Narrative On Schedule ... $8,323" and "Departmental Narrative On Budgeted Whole Life Costs $23,078,507,463.50"; "Key Metrics Over Time" plotted against "Amber"; forecasts of "-29.14, likely between -770.66 and 712.38" citing "73 monthly observations"; £m figures shown in dollars.

| # | Root cause | Evidence | Fix |
|---|---|---|---|
| 1 | `_parse_numeric_text_value` **searched** for a number anywhere in a cell, and a column converted to numeric once 85% of rows yielded one | "Compared to financial year 22/23-Q4, the project's end-date…" → `22.0` in 46 of 49 rows; `GMPP ID Number` "MOD_0001_1112-Q1" → a number too | The whole cell must be numeric once symbols, separators and magnitude suffixes are stripped (`re.fullmatch`) |
| 2 | Withheld values counted as evidence *against* a column being numeric | "Financial Year Baseline (£m)": 33 numeric, 15 "Exempt under Section 43 of the Freedom of Information Act 2000", 1 "Not Available" — after fix 1 the column fell below 85% and the real metric was lost | `_looks_like_withheld_value` treats those rows as missing numbers (null), with a floor so prose columns can't convert |
| 3 | Keyword vocabularies matched as **substrings** | `"arr"` inside "n**arr**ative" typed three narrative columns as annual recurring revenue — in `kpi_detector`, `semantic_detector` and `recommendations` | New `app/analytics/text_matching.py` matches whole, singularised tokens: `"arr"` no longer matches "narrative", `"cost"` still matches "costs" |
| 4 | A column counted as a date if its **name** contained "time" | "…assessment of the project at a fixed point in **time**…" made a Red/Amber/Green rating `temporal_dimension`, so it became the x-axis of "Over Time" charts | Date-ish names now need date-ish values (text columns); numeric date names (20260710) keep the old rule |
| 5 | Currency was hardcoded to USD in the API, the AI summaries and the frontend | UK £m columns displayed as `$23,078,507,463.50` | Detected from the original headers before standardisation rewrites "(£m)" → "currency_m", carried on the cleaning report → statistics → KPI insights → UI; unknown currency now shows no symbol rather than a dollar sign |

**Before → after on the same file** (`MOD_…_March_2024.xlsx`, run offline through `compute_analysis`, no OpenAI spend):

| | Before | After |
|---|---|---|
| Columns converted to numeric | 10, including 3 narrative columns, the commentary column and the ID column | 4, all genuinely numeric (33/49, 33/49, 34/49, 25/49 — withheld rows null) |
| KPI tiles | 4 narrative columns as money, typed `arr` | the real money metrics, typed `cost`, plus the variance percentage |
| Red/Amber/Green columns | `temporal_dimension` (the charts' time axis) | `dimension` |
| Chart time axis | the RAG rating | `project_start_date` |
| Currency | assumed USD | `GBP`, from the header `Financial Year Baseline (£m)` |

**Fixed in a follow-up the same day:**

| Problem | Fix |
|---|---|
| Forecasting treated project start dates spanning 1997–2024 as 41 monthly observations and projected "next month" from them | A monthly series must now cover at least 60% of the months between its first and last observation (`forecasting._monthly_density`). The demo dataset's 18 consecutive months still forecast; a scatter of dates across years no longer does. Tests: `test_forecasting.py` |
| A KPI tile and its own chart could disagree on SUM vs AVERAGE (roadmap item 4) | `chart_selector._aggregation()` delegates to the new `kpi_detector.uses_average_aggregation()`. Already-averaged names (`avg`, `mean`, `median`, `aov`) average on both sides — the demo dashboard's "Avg Order Value $46,919.50" was a sum of averages |

### 8.1 Second pass: compared against a hand-built Power BI report

The same six files were then modelled by hand in Power BI, giving an independent ground truth: **118 projects, £244,568m total whole-life cost, 66.1% cost-data coverage**, with a per-department breakdown (MOD 117,457; DFT 67,446; HO 30,834; DFE 19,673; DHSC 7,994; DCMS 1,164). The app disagreed — 114 rows and £367,548m — which is 244,568 ÷ 0.661, the tell-tale shape of counting withheld values as if they were reported.

| Problem | Fix | Verification |
|---|---|---|
| **Withheld values were imputed.** After cleaning marked "Exempt under Section 43…" rows as missing, the smart missing-data strategy filled them with a median — inventing public spending — and rows whose every metric was withheld were dropped entirely | Columns containing withheld values are recorded during parsing, then excluded from imputation *and* from the "row has no numeric metric" drop rule | Cleaning the six files now yields exactly 118 rows, £244,568m and 66.1% coverage, matching Power BI to the pound. `test_withheld_costs_are_never_imputed_and_keep_their_rows` |
| **Axis labels showed raw column names.** The frontend renders the visual spec, whose encodings fell back to the column name, ignoring the decoded label already on the ECharts option | Spec encodings carry the decoded titles, with a matching fallback in `charts-grid.tsx` | `test_spec_axes_carry_the_decoded_labels` |
| **Charts were "by Source File."** `source_file` scored +20 in the dimension ranking against +10 for a business name | A real dimension outranks it (department, region, segment, channel, team, …); `source_file` keeps a small bonus | Charts for this data are now by Department and Annual Report Category. `test_real_dimensions_outrank_the_source_file_column` |
| **Money was formatted as bare numbers** once the hardcoded `$` was removed | Charts whose measure is a currency column are tagged with the detected code, and the UI formats axes and labels in it | GBP flows from header → statistics → KPI and chart tags. `test_only_money_charts_are_tagged_with_the_currency` |
| **A time axis over scattered dates.** Project end dates running 2023–2045 produced a "costs over time" line across 23 years | A date column needs enough rows per month of span to be used as a time axis — the same density rule as forecasting | `test_dates_scattered_across_decades_are_not_charted_over_time` |

Worth recording about the process: the app's own analysis had been run by a Celery worker started before those fixes were deployed. Uvicorn reloads on file changes and the worker does not, so cleaning ran new code while the analysis pipeline ran old code — which is why the output looked half-fixed. `docker compose restart celery_worker` after changing analytics code.

### 8.2 Third pass: the smaller gaps this investigation had left open

| Problem | Fix | Verification |
|---|---|---|
| **Monthly anomaly detection had no density guard.** It z-scored whatever months existed, so dates scattered across decades made every populated month extreme next to the empty ones — the same flaw fixed in forecasting | Both now ask `analytics/time_series.py`, so the rule can't drift between them | `test_monthly_anomalies_need_a_real_series`, and a contiguous series still reports its spike |
| **A text column could carry `analysis_role=metric`** from its name alone, describing prose to the AI as a measure | `_role_for` only calls a column a metric when it is actually numeric | `test_text_columns_are_never_metrics_however_they_are_named` |
| **Read-time coercion destroyed withheld values.** A mostly-numeric column was cast on read, turning "Exempt under Section 43 …" into anonymous nulls before cleaning could record them — so the same six files lost 12 of 118 projects when supplied as CSV rather than Excel | Read-time casting skips columns containing withheld values, leaving them to the cleaning stage that knows what they are | `test_read_time_casting_leaves_withheld_columns_to_the_cleaning_stage`, `test_withheld_values_survive_a_csv_round_trip`, and the full pipeline over the six files via CSV now returns 118 rows and £244,568m — identical to the Excel path |

Existing analyses keep their old numbers until re-analysed.

### 8.3 Fourth pass: the chart the portfolio review actually needs

The Power BI comparison also asked for better chart *choices*, not just correct numbers. A portfolio review asks "how much of our spend is rated Red?", and the app could only answer it by reading a cost-by-department chart next to a department-count-by-rating chart.

| Problem | Fix | Verification |
|---|---|---|
| **No chart split a measure by status.** Cost by department and delivery confidence had to be inferred from two charts side by side | A stacked status-by-dimension bar: a new builder in `chart_selector`, a two-dimension aggregation in `live_filter` (so it re-queries under slicers rather than rescaling a cached total), a `color` encoding in the visual spec, and a stacking branch in `charts-grid.tsx` | `test_a_status_dimension_gets_a_stacked_chart`, `test_populate_stacked_bar_builds_one_series_per_status`, `test_stacked_bar_re_aggregates_under_a_filter`, `test_stacked_bar_spec_carries_a_colour_encoding` |
| **The gate hid the chart on the data it was built for.** Status columns were picked by raw distinct count (2–8). The GMPP delivery-confidence column has 11: five real RAG states plus six separate "Exempt under Section N of the Freedom of Information Act 2000" sentences | A status column is judged on the values that carry information, not the raw count. Requiring retained `top_values` also excludes the free-text column named `…on_the_ipa_rag_rating`, which matches the keywords but holds 117 distinct paragraphs | `test_the_real_gmpp_rag_column_is_stacked_despite_its_long_tail`, `test_free_text_commentary_about_a_rating_is_not_a_status_column` |
| **Stacking every distinct value** would have drawn six near-invisible segments, each legended with a paragraph | Values that say nothing (the FOI sentences, `Unknown`, `Not Applicable`) fold into one `Not reported` series, sharing one vocabulary with the cleaning stage via `analytics/text_matching.py` rather than a second copy of the rule. The populator selects `SUM` and `COUNT` and re-derives an average over the folded group — folding after an `AVG` would average four averages | `test_stacked_bar_folds_values_that_say_nothing_into_one_series`, `test_stacked_bar_averages_over_the_folded_group_not_over_averages`. On the six files the chart draws 6 departments × Amber / Green / Red / Not reported |
| **The title ran to ~250 characters.** It names three columns, and this column is named with its whole definition; with semantic wrangling unavailable the fallback humanises the raw name | Each part of a stacked title is trimmed to ~24 characters on a word boundary and marked with an ellipsis. Plain bars keep their full labels — only this three-column title overflowed | `test_a_paragraph_long_column_name_is_trimmed_in_the_title`. The real title is now 68 characters: "Financial Year Baseline… by Department and Ipa Delivery Confidence…" |
| **A misleading skip reason.** The DB-backed tests surface the raw driver error, "password authentication failed for user test_user", which reads like broken credentials when the cause is the default port pointing at the application's Postgres instead of the test container | The skip says no test database is reachable and names `POSTGRES_PORT`. CI pins no port, so the default is left alone | `POSTGRES_PORT=5433 pytest` runs all 9; without it they skip with an actionable message |

Measured against the same ground truth: the stacked chart's segments sum to the financial-year baseline KPI (£22,797m), not the whole-life-cost total — it plots the portfolio's leading metric, and the whole-life-cost total remains £244,568m as in §8.1.

### 8.4 Fifth pass: what a non-technical reader is actually told

The arithmetic was right by this point; the narration was not. Reviewing the running dashboard as its intended audience — someone who cannot check the figures — turned up one falsehood and four presentation faults. The first was a defect and was fixed immediately; the rest change analysis behaviour and were done only once approved.

| Problem | Fix | Verification |
|---|---|---|
| **The summary stated a record's figure as its department's.** "The DFT department shows a standout financial year variance of 733%" — DFT averages 23.94% across 19 projects, and 733% is one project, the Midland Main Line Programme. The recommendation title repeated it. The deterministic cards were correct throughout ("One record reached 733.00…"), so this was the AI narrative collapsing a record into its group | A core analysis rule, governing recommendation titles as well as the summary: an extreme value belongs to the record that holds it, and a figure may be stated as a group's only when the profile carries that group's own average or total | `test_prompt_forbids_attributing_a_record_extreme_to_its_group` |
| **An unweighted mean of percentages.** "Avg Financial Year Variance −4.41%" gave a £5bn scheme exactly the same say as a £75m one | The statistics layer computes `SUM(pct × weight) / SUM(weight)` against the largest money column, and the KPI reads "Weighted Avg …, weighted by …" so the reader is told what changed. The plain mean is still carried | On the six files the headline moves from −4.41% to −5.63%, weighted by total baseline whole-life costs. `test_percentage_average_is_weighted_by_the_money_it_applies_to`, `test_a_percentage_kpi_uses_the_cost_weighted_average_when_one_exists` |
| **Five near-identical "Standout" cards**, each saying one record was higher than almost every other, quoting reference numbers like `DFT_0027_1617-Q1` at the reader | One consolidated card naming the strongest and listing the rest. Identifier columns are excluded from an insight's context, and a column label is trimmed to 40 characters — the delivery-confidence column's name is 200 | `test_several_anomalies_become_one_card`, `test_identifier_columns_are_left_out_of_the_context`, `test_a_paragraph_long_context_label_is_shortened` |
| **Large projects reported as quality defects.** "8 values fall far outside the typical range (−300 to 578)" at medium severity, on a portfolio containing HS2 — and no cost column can reach −300 | Right-skew is the subject matter: high-side spread is reported as `wide_spread` at low severity in neutral wording, and the quoted bound is clamped to a value the column can reach. Values *below* a reachable floor are still flagged as outliers at medium | Four issues drop to low with bounds starting at 0; Financial Year Variance % correctly stays medium, since it genuinely has values below the fence. `test_a_right_skewed_metric_is_not_reported_as_a_defect`, `test_values_below_a_reachable_floor_are_still_flagged` |
| **The histogram put 84 of 118 projects in one bar**, because equal-width bands cannot describe a distribution whose largest value is fifty times its median | When the maximum dwarfs the median, bands step 1-2-5 instead, and the open top band reads "5K+" rather than "5K-5K" | The largest bar falls from 84 to 23 and the records spread across nine populated bands. `test_histogram_bands_widen_for_a_skewed_distribution`, `test_histogram_bands_stay_even_when_the_data_is_not_skewed` |

### 8.5 Sixth pass: driving the running app in a browser

The previous passes were verified through the pipeline and the API. This one drove the actual dashboard: a throwaway account, the six workbooks uploaded through `/uploads`, a combined analysis, then Playwright logging in and screenshotting the page a reader sees. Three defects were visible there that no payload inspection had caught.

| Problem | Fix | Verification |
|---|---|---|
| **A second copy of the long-label bug.** `_anomaly_recommendations` builds its own context string, so while the anomaly's description was shortened, the recommendation card still carried 200 characters of column name — visible on screen with the shortened evidence line directly beneath it | The same shared shortener | `test_anomaly_recommendation_shortens_a_paragraph_long_context_label` |
| **"5 issues detected before AI reasoning."** Four of those were the low-severity spread notes from §8.4, so the count still told a non-technical reader their data was faulty | Defects and notes are counted separately: "1 issue detected before AI reasoning, plus 4 notes on spread". Both stay listed with their badges — the framing changed, not the disclosure | Rendered in the browser; `defects`/`notes` split in `data-quality-panel.tsx` |
| **Display labels can be a column's whole definition.** These come from an AI call, and a *successful* response was observed returning the 200-character delivery-confidence definition as the label, which then became a chart title, an axis name and a check heading | Labels are capped at 64 characters at both the fallback and the merge — the single point where the final label is chosen | `test_display_labels_are_capped_so_a_column_definition_cannot_become_a_title` |

**Known and unfixed.** Display-metadata quality is non-deterministic: one run produced "Baseline Financial Year Cost (M)", the next produced "Financial Year Baseline Currency M Including Non Government Costs" for the same column, from a successful call each time. At exactly 64 characters the latter passes the cap untouched, so the dashboard still reads poorly whenever that happens — chart titles run to 79 characters and the scatter's to 134. A deterministic label derivation, rather than a length cap on whatever the model returns, is the real fix.

**The scatter was left alone, deliberately.** A log scale was built for it and is covered by tests, but it does not engage on this data and should not: the baseline and forecast columns each contain genuine zero values (six and four), and a log axis silently drops them. A chart that looks better by hiding six real projects is worse than a crowded one, so the guard requires strictly positive values and this dataset keeps a linear, complete scatter.
