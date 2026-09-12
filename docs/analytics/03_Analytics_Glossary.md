# Analytics Glossary — KPIs, Metrics, Dimensions, Business Rules

> Every definition below cites the function that implements it. This is a
> living contract between the code and anyone reading a dashboard it
> produces — if a number on screen looks wrong, the calculation that
> produced it should be traceable from this document in under a minute.

---

## 1. Core concepts, as this system defines them

| Term | Definition here |
|---|---|
| **Fact** | A numeric, aggregatable observation in the uploaded table — a row's `revenue`, `units_sold`, etc. There is no separate fact *table*; every uploaded file is itself a single wide fact-and-dimension table (see `docs/analytics/05_Data_Modelling.md`). |
| **Dimension** | A categorical column used to group or filter facts (`region`, `category`, `channel`). Assigned the `analysis_role: "dimension"` semantic role. |
| **Metric** | A numeric column classified as business-meaningful and aggregatable — `analysis_role: "metric"`. Not every numeric column is a metric: identifiers, coordinates, and year-like columns are explicitly excluded (`kpi_detector.py:32-34`, `NON_KPI_NUMERIC_KEYWORDS`). |
| **KPI** | A metric promoted to a headline dashboard tile — every metric-classified column becomes *a* KPI candidate; only a bounded, priority-ranked subset (`kpi_detector.py:88-97`) actually renders as a tile. |
| **Attribute** | A numeric column that describes something but isn't a metric to sum/average on its own (e.g. a rating, a physical measurement) — excluded from outlier/negative-value scanning for the same reason dimensions are. |
| **Flag** | A binary/boolean-coded numeric or short-categorical column (e.g. `converted`, `churned`) — turned into a *rate* metric (see `outcome_rate` below), not a raw sum. |
| **Identifier** | A column that looks like an ID (`_looks_like_identifier_column`, `file_processor.py:1269`) — excluded from outlier detection, imputation, and KPI classification. |

---

## 2. KPI types and calculation logic

Source: `backend/app/analytics/kpi_detector.py`. Every numeric column with `analysis_role in {None, "metric"}` is matched against keyword lists (`_classify_column`) to assign a `kpi_type`; the type then decides both the **aggregation** (sum vs. average) and the **display format** (currency, percent, plain number).

| `kpi_type` | Keyword match (examples) | Aggregation | Currency? |
|---|---|---|---|
| `revenue` | revenue, sales, income, turnover, gmv, amount, price, value | **Sum** | Yes |
| `profit` | profit, margin, earnings, ebitda, net_income, gross_profit | **Sum** | Yes |
| `orders` | orders, transactions, purchases, bookings, invoices, quantity, units_sold | **Sum** | No |
| `customers` | customers, users, clients, accounts, buyers, leads | **Sum** | No |
| `cost` | cost, expense, cogs, opex, spend, budget | **Sum** | Yes |
| `mrr` / `arr` | mrr, monthly_recurring_revenue / arr, annual_recurring_revenue | **Sum** | Yes |
| `conversion` | conversion, cvr, win_rate, close_rate | **Average** | No |
| `growth` | growth, growth_rate, yoy, mom, trend | **Average** | No |
| `churn` | churn, churn_rate, cancellations, attrition | **Average** | No |
| `return_rate` | returns, refunds, return_rate, rma | **Average** | No |
| `margin` | margin, gross_margin, net_margin | **Average** | No |
| `retention` | retention, renewal, repeat_purchase | **Average** | No |
| `aov` | aov, average_order_value, avg_order_value, basket_size | **Average** | Yes |
| `average_metric` | rating, score, percentage, rate, ratio, nps, satisfaction | **Average** | No |
| `duration` | duration, hours, minutes, distance, cycle_time | Sum | No |
| `outcome_rate` | derived from a binary flag column (see below) | **Average** (it's already a rate) | No |

**`_uses_average()`** (`kpi_detector.py:164-172`): averages if `kpi_type` is one of `{margin, conversion, growth, retention, churn, return, average}`, or the column name contains `pct`/`percent`/`percentage`/`rate`. Everything else sums.

**Outcome-rate KPIs** (`_outcome_rate_kpis`, `kpi_detector.py:51`): a binary-coded column matching `OUTCOME_KEYWORDS` (`target, outcome, label, churned, converted, survived, fraud, clicked, purchased, responded, approved, won, success, disease, readmitted, defaulted`) is converted into a **rate** — `mean(column) × 100` — rather than exposed as a raw 0/1 sum. This is the mechanism that turns e.g. a `converted` column of 0s and 1s into a "Conversion Rate: 34%" KPI tile instead of a meaningless "Sum of converted: 340" tile.

**Currency detection** (`_is_currency`, `kpi_detector.py:159-161`): name contains `revenue, sales, profit, cost, price, amount, income, spend, value, valuation, gmv, mrr, arr, aov`. ⚠️ Defined independently (and slightly differently) in two other places — see `docs/analytics/01_Data_Architecture.md §8`.

**Priority ranking** (`kpi_detector.py:88-97`) — a fixed, hand-authored importance order used to decide which KPIs earn a dashboard tile when there are more candidates than slots: `outcome_rate` (highest) → `revenue` → `profit` → `orders` → `customers` → `mrr`/`arr` → ... → `other` (lowest). This is an editorial business judgment, not something derived from the data.

### Calculated fields (there are only two — everything else is a directly-aggregated column)

| Field | Formula | Where |
|---|---|---|
| `change_percent_next_month` | `(next_month_forecast − latest_actual) / latest_actual × 100` | `forecasting.py:85` |
| Outcome rate | `mean(binary_column) × 100` | `kpi_detector.py:_outcome_rate_kpis` |

There is **no** general "derived metric" engine (no `revenue / units = AOV` computation, for example) — if a dataset doesn't already contain an AOV-named column, no AOV KPI is produced. This is a real product boundary worth knowing: the system classifies and aggregates columns that exist; it does not synthesize new business ratios from raw columns.

---

## 3. Chart aggregation

`chart_selector.py:_aggregation()` (`:209-212`) decides sum vs. average **independently of the KPI detector**, using its own keyword whitelist: sums only if the name contains `revenue, sales, cost, amount, distance, quantity, units, spend`; averages everything else. See `docs/analytics/01_Data_Architecture.md §8` for the resulting KPI-vs-chart inconsistency on columns like `total_profit`, `mrr`, `arr`, `gmv`.

**Chart-type selection rules**, in the order they're evaluated (`chart_selector.py`):
- Time series requires a date column + a numeric column (`:62`).
- Multi-line only if ≥2 "dense" (non-sparse) numeric columns whose means are within a 10× ratio of each other (`_comparable_scales`, `:215-218`) — prevents a chart plotting `revenue` (thousands) against `discount_pct` (0–100) on the same axis.
- Sparse metrics (>70% null, the same `0.7` threshold used in cleaning) render as disconnected point markers instead of a smoothed line (`_SPARSE_METRIC_NULL_RATIO`, `:17`).
- Scatter plots pick only the single strongest `|correlation|` pair (`:117-130`).
- Donut charts require 2–8 unique category values (`:113`).
- Dimension columns are ranked by a hand-tuned point system for "which category should this bar chart group by" (`_dimension_score`, `:188-202`): +20 for a `source_file` column, +10 for company/organisation/sponsor/therapy/area/type/phase/status/country/category-named columns, +6 for a year column, +4 for 2–30 unique values, +2 for 31–100.
- Hard cap of 8 charts per dashboard (`:36`).

---

## 4. Forecast metrics

`analytics/forecasting.py` — **linear regression trend extrapolation**, not a seasonal/ARIMA-style time-series model. Documented plainly in the module's own docstring: *"This intentionally stays deterministic and transparent. It gives the LLM and UI grounded forecast ranges without claiming more certainty than the data supports."* (`forecasting.py:1-6`)

- Metric selection: KPIs typed `revenue/profit/orders/customers`, or any business-metric-named numeric column, up to 3 (`max_forecasts`, `:16-35`).
- Series: monthly `SUM(metric)` grouped by `DATE_TRUNC('month', date_column)` (`:51-62`), fit via `np.polyfit`.
- **Confidence formula** (`_confidence`, `:100-104`):
  ```
  history_score = min(observations / 12, 1.0)
  noise_ratio   = residual_std / |mean|
  noise_score   = max(0.2, 1.0 − min(noise_ratio, 0.8))
  confidence    = round(0.45 + 0.45 × history_score × noise_score, 2)
  ```
  In plain terms: confidence rises with more months of history (capped at a full year's worth of credit) and falls with how noisy the trend residuals are, bounded to a `[0.45, 0.90]` range.

## 5. Anomaly metrics

`analytics/anomaly_detection.py` — two independent checks:

1. **Distribution outlier**: `z_score = |(value − mean) / std|`, flagged at `z_score ≥ 3`, plus a `CUME_DIST()` percentile rank computed *before* filtering to outliers (so a minimum value doesn't misleadingly read as "100th percentile") — the single highest-`z_score` row per metric column is reported (`:68-79`).
2. **Monthly time-series anomaly**: `AVG`/`STDDEV` computed over monthly `SUM(metric)` via a window function, flagged at `z_score ≥ 2.5` (a different threshold than the row-level check, undocumented in code why the two differ), limited to the top 2 months (`:134-157`).

---

## 6. Filters (live slicers)

`analytics/live_filter.py` — the mechanism behind the dashboard's clickable cross-filters. Column eligibility is an **explicit allowlist by semantic role** (`ALLOWED_FILTER_ROLES`, `:38-58`) — a column can only be filtered on if its `analysis_role` is one of the roles deemed filter-safe (dimensions, flags, temporal — not free-text or identifier columns). Filter values are always passed as parameterized `?` placeholders. Supported filter operators: equality/`IN` (multi-select), `BETWEEN` (numeric/date ranges). See `docs/analytics/01_Data_Architecture.md §9` for the safety rationale.

---

## 7. Data quality metrics

See `docs/analytics/02_Data_Quality_Framework.md` for the full detail. Summary of what "quality" means numerically in this system:

| Concept | Formula | Where |
|---|---|---|
| Missing-value severity | `>50%→critical, >20%→high, else→low` | `data_quality.py:34` |
| Duplicate severity | `≥50%→critical, ≥20%→high, ≥5%→medium, else→low` | `data_quality.py:_ratio_severity` |
| Outlier bounds | Tukey IQR × 1.5 | `data_quality.py:93-95`, consistent with cleaning |
| Overall score | `100 − Σ(severity_weight × max(affected_ratio, 0.05))`, weight doubled past 50% impact | `data_quality.py:_quality_score` |

---

## 8. Confidence scores — every distinct meaning in this system

"Confidence" is used in **six different, non-interchangeable ways** across the codebase. Treating them as one concept is the single most common misunderstanding a reviewer could form about this system — each is listed with what it actually measures:

| Where | What it actually measures |
|---|---|
| `semantic_detector.py` column-type rules | A hand-authored constant per pattern (e.g. email regex match = 0.95) — not computed from the data at all |
| `forecasting.py:_confidence()` | A formula combining history length and residual noise (§4 above) — genuinely data-derived |
| `analysis_engine.py:186` | KPI insight confidence — hardcoded to `0.99` |
| `analysis_engine.py:242` | Anomaly insight confidence — `min(z_score / 5, 0.95)`, a rescaling of the z-score |
| `calibration.py` → `recommendations.py` | Deterministic recommendation confidence, per rule source (`rule:data_quality`, `rule:anomaly`, `rule:forecast`, `rule:tracking`). The benchmark-measured value from `calibration_table.json` when one exists with enough samples; otherwise the hand-set default (quality 0.9, anomaly 0.78, generic 0.72; forecast recommendations inherit the forecast's own formula confidence). See `10_Confidence_Calibration.md`. |
| `calibration.py` → `ai_service.py` | AI recommendation confidence, per priority tier (`ai:high` / `ai:medium` / `ai:low`). Measured value when available, else the original hand-set lookup `{"High": 0.85, "Medium": 0.7, "Low": 0.55}`. Each recommendation records which applied in `data.confidence_method`. See `10_Confidence_Calibration.md`. |

---

## 9. Assumptions

These are implicit business assumptions baked into the analytics logic — stated here so they're falsifiable rather than invisible:

- A column's business meaning can be inferred from its **name and value shape alone** — no user is ever asked "what does this column mean?" This is the product's core zero-configuration bet (`docs/01_Vision.md §6.1`), and it's why keyword-list drift (§2's currency detection, §3's aggregation choice) matters more here than it would in a system with explicit user-defined metric configuration.
- A metric with <70% null values is "core" to the dataset; sparser metrics are treated as optional/structurally-expected gaps, not quality defects (`_SPARSE_NUMERIC_METRIC_NULL_RATIO = 0.7`, reused for both cleaning and chart rendering).
- Outliers are always defined relative to the dataset's *own* distribution (IQR), never against an external/industry benchmark.
- A forecast is only offered where a date column exists; no metric is ever forecast without a temporal axis (`forecasting.py:23-25`).
- "Part exceeds whole" business-rule checks (`units_returned > units_sold`, etc.) only fire on exact, hardcoded column-name matches — they don't generalize to synonyms or renamed columns.
