# Data Quality Framework

Two distinct data-quality components exist in this codebase, deliberately
kept separate. Conflating them would either risk breaking the live product
or produce documentation that overclaims what the shipped pipeline does.

| | Pipeline detector | Standalone framework |
|---|---|---|
| File | `backend/app/analytics/data_quality.py` | `backend/app/analytics/data_quality_checks.py` |
| Runs | Automatically, inside every analysis (`StatisticsEngine.describe_all`) | On demand — CLI, notebook, CI, or imported directly |
| Depends on | DuckDB (queries an open connection over table `"data"`) | Nothing — stdlib only |
| Output contract | Fixed: `{"score": int, "issues": [...], "fixes": [...]}` — load-bearing for the frontend panel and 3 pinned tests | `QualityReport` dataclass — free to extend |
| Checks | Missing values, IQR outliers + negative-financial-value scan (metric/attribute columns only), exact duplicates, 3 hardcoded "part exceeds whole" pairs | Missing values, duplicates (full-row or by key), invalid IDs, outliers (IQR or z-score), schema validation, referential integrity, unexpected nulls, date validity |

**Why two, not one.** The pipeline detector is intentionally narrow and stable — it's called from exactly one place (`statistics.py:52`), its output shape is depended on by `frontend/src/components/analysis/data-quality-panel.tsx`, `recommendations.py`, `analysis_engine.py`'s portfolio-mode adjustment, and three regression tests (one of them pinned to a specific historical scoring bug: a 70%-duplicate dataset must score ≤85). Changing its behavior was explicitly out of scope for this pass. The standalone framework is the general-purpose toolkit — the piece meant to demonstrate reusable validation-function design independent of any one product's internals, and the piece you can actually run against a dataset that never touches this app.

---

## 1. The pipeline detector (`data_quality.py`)

`analyze_data_quality(conn, schema, numeric_stats, table="data") -> dict`

Runs once per analysis, as the last step of `StatisticsEngine.describe_all()` (`statistics.py:52`), after schema introspection and semantic-role classification (its outlier/negative-value checks are gated on `analysis_role in {None, "metric", "attribute"}` — identifiers and dimension codes are excluded on purpose, since a rare category code isn't an "unusual value").

**Score formula** (`_quality_score`, `data_quality.py:148-160`):

```python
severity_weight = {"low": 1.5, "medium": 4.0, "high": 8.0, "critical": 14.0}
penalty = Σ over issues: weight(severity) × max(affected_ratio, 0.05)
        # weight doubled if affected_ratio > 0.5
score = clamp(100 - penalty, 0, 100)
```

Severity for missing values: `>50%→critical, >20%→high, else→low` (note: no explicit "medium" tier here). Severity for duplicates: `≥50%→critical, ≥20%→high, ≥5%→medium, else→low` — a second, slightly different rubric for the same underlying "what fraction of rows" concept, ~100 lines apart in the same file. Both are documented here rather than silently unified, since unifying them would change the score the frontend and tests already depend on.

**What the docs claim vs. what exists**: `docs/02_Product_Requirements.md` (`FR-PROC-11`) and `docs/08_Glossary.md` describe a *per-dimension* breakdown (missing %, duplicate %, type consistency, outlier presence, header quality) and a "score < 70 shows a warning banner" UX rule. Neither exists — `_quality_score` returns one flat integer, and the frontend panel (`data-quality-panel.tsx:94`) only recolors a progress bar below 75; there is no separate banner. This is flagged, not fixed, in `docs/analytics/01_Data_Architecture.md §8`.

---

## 2. The standalone framework (`data_quality_checks.py`)

Eight reusable, independently-testable checks, each returning one or more `CheckResult` objects (`check`, `column`, `passed`, `severity`, `message`, `affected_count`, `total_count`, `details`):

| Function | Validates |
|---|---|
| `check_missing_values(rows, columns)` | Null/blank rate per column (recognizes `""`, `"N/A"`, `"unknown"`, `"null"`, `"-"` as blank, not just `None`) |
| `check_duplicate_records(rows, key_columns=None)` | Exact full-row duplicates, or duplicate keys if a key is given |
| `check_invalid_ids(rows, id_column, pattern=None, require_unique=True)` | Blank, malformed (regex), and duplicate identifiers — reported both combined and broken down |
| `check_outliers(rows, column, method="iqr"\|"zscore")` | Statistical outliers; IQR (default, robust to skew) or z-score |
| `check_schema(rows, expected_columns)` | Missing/extra columns, and per-column type match rate against an expected `numeric/text/date/boolean` schema (≥90% tolerance — real files have a few dirty cells) |
| `check_referential_integrity(child_rows, child_key, parent_rows, parent_key)` | Foreign-key-style orphan check between two datasets — flat files have no `FOREIGN KEY` constraint, so nothing else in this codebase does this |
| `check_unexpected_nulls(rows, required_columns)` | Nulls in columns declared mandatory — always-actionable, unlike the informational missing-value rate |
| `check_date_validity(rows, column, min_date=None, max_date=None, allow_future=True)` | Unparseable dates, out-of-range dates, future dates (opt-in) |

`run_quality_suite(rows, QualitySuiteConfig(...))` runs whichever checks the config asks for and rolls them into a `QualityReport` (row/column counts, a 0–100 `score`, the full list of `CheckResult`s). `render_markdown_report(report)` renders it as a standalone Markdown document — no other dependency required.

### Design choices worth calling out

- **Stdlib only.** No pandas/duckdb/polars import. This is a conscious portability decision, not an oversight — the same module runs in a bare `python` invocation, a CI step, or gets imported into a project that uses a completely different data stack. Every check operates on `list[dict]`, the lowest common denominator every DataFrame library can already produce.
- **A deliberately separate scoring formula.** `score_report()` uses the same *shape* of severity-weighted penalty as the pipeline detector's `_quality_score`, but is its own implementation with no shared code and no claim of numerically matching it. Documented explicitly in the function's docstring so a reviewer doesn't mistake the similarity for either duplication or a bug.
- **Tested.** `backend/tests/test_data_quality_checks.py` — 20 tests, all passing (`python -m pytest backend/tests/test_data_quality_checks.py`), covering every check's pass and fail paths plus the report/scoring orchestration.

### Running it

```bash
python backend/scripts/data_quality_report.py path/to/file.csv \
    --id-column order_id \
    --date-column order_date \
    --outlier-column revenue \
    --required-column region \
    --output report.md --json-output report.json
```

### Example: run against this repo's own demo dataset

```bash
python backend/scripts/data_quality_report.py \
    backend/scripts/demo_data/northwind_outfitters_sales.csv \
    --date-column week_start_date \
    --outlier-column revenue --outlier-column marketing_spend --outlier-column units_sold \
    --required-column region --required-column category \
    --duplicate-key week_start_date --duplicate-key region --duplicate-key category
```

Full output committed at [`backend/scripts/demo_data/sample_data_quality_report.md`](../../backend/scripts/demo_data/sample_data_quality_report.md) (and `.json`). Result: **99/100**, 17 checks run, 3 flagged — all three are the `outliers` check correctly catching (a) the deliberately-injected checkout-outage anomaly at the low end of `revenue`, and (b) legitimate high-end holiday-season values. Every duplicate, null, and date-validity check passes clean, which is exactly what a synthetically generated, internally-consistent dataset should produce — a quality report that flags nothing at all on a file like this would be more suspicious than reassuring.

---

## 3. How they'd integrate, if extended

Not implemented in this pass, to keep the change-set behavior-neutral, but the concrete next step: `analyze_data_quality()`'s output dict could gain an additional `dimensions` key (additive, doesn't touch `score`/`issues`/`fixes`) populated by running the relevant `data_quality_checks` functions against the same DuckDB table and mapping their results into per-dimension sub-scores — closing the gap between what `docs/02_Product_Requirements.md` promises and what ships, without risking the existing contract.
