# Business Insights — Worked Example

Every figure below is computed directly from `backend/scripts/demo_data/northwind_outfitters_sales.csv` (936 rows, weekly sales, 3 regions × 4 categories, 2025-02-03 → 2026-07-27) — the same dataset used in this project's live demo. Nothing here is invented; the computation is reproducible (`docs/analytics/07_Business_Insights.md` sits next to the CSV it describes). This document exists to demonstrate one specific skill separate from writing SQL or Python: **how a Data Analyst communicates a finding** — headline first, then the evidence, then the "so what."

---

### 1. Revenue grew 11.7% between the first and last quarter of the dataset

**Finding.** Trailing-3-month revenue rose from £1.91M (Feb–Apr 2025) to £2.13M (May–Jul 2026), an 11.7% increase. Growth wasn't uniform across categories: Footwear (+12.5%) and Apparel (+12.3%) grew fastest, while Outdoor Gear lagged at +10.4%.

**So what.** If this were a real business review, Outdoor Gear's slower growth would be the next question to chase — is it a category losing relative share deliberately (a strategic shift toward apparel), or an execution gap (stock, marketing allocation, pricing) worth investigating before it compounds.

---

### 2. Holiday seasonality is real and quantifiable: +26.6% in November–December

**Finding.** Average weekly revenue per region/category combination was £16,118 in November–December versus £12,735 the rest of the year — a 26.6% seasonal lift. December alone (£982,909) was the single highest-revenue month in the dataset, nearly double January's £542,458 trough.

**So what.** This is exactly the kind of seasonal pattern a forecasting model needs to be told about explicitly rather than left to infer from a short history — see the confidence-formula discussion in `docs/analytics/03_Analytics_Glossary.md §4`: with only 18 months of history, a naive trend line risks reading December's spike as a step-change rather than a recurring pattern until it has seen at least one full repeat.

---

### 3. Anomaly: North America / Apparel lost 98.8% of a week's revenue right before the holiday peak

**Finding.** The week of 2025-11-17, North America/Apparel revenue was £268 — a 98.8% drop from the ~£22,262 average of the four surrounding weeks for that same region/category. This is not a data-quality artifact: the row's z-score on the pooled `revenue` column is ≈4.6, the single highest in the dataset (verified in `backend/scripts/demo_data/README.md`), and it survives independent of any per-category baseline comparison.

**The detail that makes it a real incident, not just a low week**: marketing spend for that same row was £2,997 — in line with the £2,366 neighboring-week average, not reduced. Spend didn't fall with revenue. That divergence is the signal a pure "revenue dropped" alert would miss and a spend-vs-outcome comparison catches immediately.

**So what.** In a real business, this is the shape of a platform outage or payment-processor failure, not a demand problem — the fix is operational (uptime, incident response) not commercial (pricing, promotion). Recommending a price change or a promotion in response to this specific anomaly would be actively wrong; recommending an incident post-mortem would be right. This is precisely the distinction `docs/analytics/08_AI_Analytics_and_Guardrails.md` covers under "why the model isn't allowed to guess at causation" — the Profile JSON this anomaly would generate contains the revenue collapse and the flat spend line as two separate facts; inferring "this was an outage, not weak demand" is a causal leap current guardrails correctly refuse to let the model make unprompted.

---

### 4. Marketing spend is a strong, near-linear driver of revenue (r ≈ 0.80); discounting is not (r ≈ 0.02)

**Finding.** Excluding the anomaly week, the correlation between `marketing_spend` and `revenue` across all 935 remaining rows is **0.798** — a strong positive relationship. The correlation between `discount_pct` and `revenue` is **0.021** — indistinguishable from no relationship at all.

**So what.** This is the difference between a real performance driver and a red herring. If a stakeholder's instinct were "let's discount harder to hit the revenue target," this dataset says that lever doesn't move revenue in any measurable way, while marketing spend does. A recommendation engine that only looked at "what's correlated with revenue" without a magnitude/significance check could easily surface discounting as an action item; the actual numbers rule it out. (This mirrors the real system's correlation significance cutoff of `|r| > 0.3`, `docs/analytics/03_Analytics_Glossary.md §5` — 0.021 wouldn't clear that bar; 0.798 clears it easily.)

---

### 5. Geographic pattern: North America leads on revenue, but not proportionally in every category

**Finding.** North America is the largest region overall (£4.65M, 37.8% of total revenue), ahead of Europe (£4.05M, 33.0%) and APAC (£3.59M, 29.2%) — consistent with its highest regional multiplier in the underlying demand model. But the gap isn't uniform: APAC's Accessories revenue (£715,582) is only 76% of North America's Accessories revenue (£937,757), a wider gap than the two regions' overall 1.30:1 revenue ratio would predict.

**So what.** A region-level summary ("North America is our biggest market") would miss this — Accessories specifically underperforms in APAC relative to how the rest of the portfolio performs there. Whether that's a genuine demand gap or a distribution/assortment issue is exactly the kind of follow-up question a flat regional KPI tile can't answer but a category-by-region breakdown can prompt.

---

### 6. Category mix: Apparel leads, but the portfolio is reasonably balanced

**Finding.** Apparel is the largest category at 29.4% of revenue, followed by Footwear (26.3%), Outdoor Gear (24.3%), and Accessories (20.1%) — no single category exceeds 30% of the portfolio, and the smallest is still one-fifth of total revenue.

**So what.** This is a business with no single point of category failure — useful context when interpreting the Outdoor Gear growth lag from finding #1: it's a relative underperformance, not a category in absolute decline, and not one large enough on its own to threaten the overall growth trend.

---

### 7. Discounting is fairly uniform across regions — so it can't explain regional performance gaps

**Finding.** Average discount rates are nearly identical across regions: North America 12.0%, Europe 11.9%, APAC 11.5%.

**So what.** Combined with finding #4 (discounting isn't correlated with revenue anyway), this rules out "APAC discounts less aggressively" as an explanation for its lower revenue share from finding #5. The gap is more likely driven by the underlying regional demand multiplier baked into how this dataset was generated (declared honestly here since this is synthetic data) — or, in a real dataset, would be the next thing to investigate via a factor the data doesn't yet capture (market size, channel mix, local competition).

---

## Recommendations, in priority order

Written the way this system's own Decision Feed would present them — problem, evidence, expected impact, priority:

| Priority | Recommendation | Evidence |
|---|---|---|
| **High** | Investigate the North America/Apparel outage the week of 2025-11-17 as an operational incident, not a demand issue | 98.8% single-week revenue collapse with flat marketing spend — findings #3 |
| **High** | Protect/expand marketing spend rather than deepening discounts to drive revenue | r=0.80 (spend) vs. r=0.02 (discount) — findings #4, #7 |
| **Medium** | Review Outdoor Gear's growth rate against the rest of the portfolio | +10.4% vs. +12.3-12.5% for other categories — finding #1 |
| **Medium** | Investigate APAC Accessories specifically, not APAC broadly | 76% of NA's Accessories revenue vs. an overall 90% NA:APAC revenue ratio in that period — finding #5 |
| **Low** | Build holiday seasonality into any forecasting model before it has seen a second holiday cycle | +26.6% Nov/Dec lift on only 18 months of history — finding #2 |

---

## Methodology note

Figures computed with plain Python (`statistics`/`csv` stdlib) directly against the CSV, independent of the application's own DuckDB pipeline — a deliberate choice so this document's numbers serve as an **independent check** on the live dashboard's output for the same file, not a restatement of it. Correlations use population standard deviation (`statistics.pstdev`) and Pearson's r; the anomaly z-score is computed identically to `anomaly_detection.py`'s method and cross-verified in `backend/scripts/demo_data/README.md`.
