# Dashboard Specification

This system actually powers two different dashboards, aimed at two different
audiences. Both are documented here — the one that ships today (§1), described
exactly as it exists, and a proposed executive/operational dashboard for
running the product itself as a business (§2), which is the "pretend this
powers executive dashboards" exercise, done against the real schema rather
than an imagined one.

---

## 1. The dashboard that ships — per-analysis, end-user facing

One dashboard per uploaded file, rendered from `analyses.metadata`/`.charts`
and the `insights` table. Sections, in render order (`analysis-dashboard.tsx`):

| Section | Content | Backing KPI/metric families (see `docs/analytics/03_Analytics_Glossary.md`) |
|---|---|---|
| **Executive Summary** | 3-5 paragraph AI-authored narrative, grounded in the Profile JSON | N/A — narrative, not a metric |
| **KPI grid** | Up to 8 tiles: value, trend arrow, % change vs. prior period | `revenue, profit, orders, customers, mrr, arr, aov, conversion, churn, ...` — see full type table in the glossary |
| **Charts** | Up to 8 auto-selected: bar, line, pie/donut, scatter | Trend (time series), category breakdown (bar/donut), correlation (scatter) |
| **AI Insights** | Model-authored observations, each grounded to Profile JSON figures | Narrative + supporting chart |
| **Recommendations (Decision Feed)** | Deterministic + AI-authored, deduplicated, priority-tagged | See `docs/analytics/08_AI_Analytics_and_Guardrails.md` for how deterministic vs. AI-authored recommendations differ |
| **Data Quality panel** | Score, top issues, suggested fixes | `docs/analytics/02_Data_Quality_Framework.md` |

This is an **operational/exploratory** dashboard by design (P4 "Progressive Disclosure" in `docs/01_Vision.md §6.2`) — it answers "what does this one dataset tell me," not "how is my business trending across everything I've ever uploaded." That second question is what §2 below addresses, and nothing in the current product answers it.

---

## 2. Proposed: Executive & Operational dashboard for running the product

This is the dashboard a Head of Product/Analytics would actually want, sitting *above* individual analyses — tracking the SaaS business itself. It doesn't exist in the codebase today. It's specified here against the **real** schema (`docs/analytics/05_Data_Modelling.md`) and the North Star/KPI targets already defined in `docs/01_Vision.md §9`, so every metric below is either genuinely computable now or explicitly flagged as requiring a schema addition — not aspirational hand-waving.

### 2.1 North Star

| Metric | Definition | Computable today? |
|---|---|---|
| **Weekly Active Analyses** | `COUNT(DISTINCT analyses.id) WHERE analyses.created_at >= now() - interval '7 days'` | ✅ Yes — `analyses.created_at` |

### 2.2 Executive KPI row (top-line, weekly cadence)

| KPI | Definition | Formula sketch | Computable today? |
|---|---|---|---|
| Weekly Active Analyses | See above | `COUNT(DISTINCT analyses.id)` in trailing 7d | ✅ |
| MRR | Monthly recurring revenue | `SUM(plan_price[subscriptions.plan]) WHERE subscriptions.status = 'active'` | ⚠️ Partial — `subscriptions.plan` exists; **no plan→price table exists in the schema**, price would need to come from a config lookup (plan prices are documented in `docs/02_Product_Requirements.md §12`: Free £0 / Pro £29 / Business £99 / Enterprise custom) rather than a queryable column |
| Paid Conversion Rate | % of trial users who convert to paid | `COUNT(users WHERE plan != 'free' AND created via trial) / COUNT(trial starts)` | ❌ No — there's no `trial_started_at` or trial-state column on `users`/`subscriptions`; `SubscriptionPlan` has no `trial` value at all (`user.py:17-21`) |
| Net Promoter Score | Standard NPS | N/A | ❌ No — no survey/feedback table exists anywhere in the schema |
| Monthly Churn Rate | % of paying users who cancel in a month | `COUNT(subscriptions WHERE cancel_at_period_end became true this month) / COUNT(active subs at month start)` | ⚠️ Partial — `subscriptions.cancel_at_period_end` and `.status` exist, but there's no subscription *history* table, so a point-in-time query can't reconstruct "who was active at the start of last month" without either a periodic snapshot job or a `subscription_events` audit table |

### 2.3 Operational KPIs

| KPI | Definition | Formula sketch | Computable today? |
|---|---|---|---|
| Time to First Insight (p95) | Seconds from upload to dashboard visible | `PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY updated_at - created_at) WHERE status='completed'` | ⚠️ Approximation only — there is no dedicated `completed_at` timestamp on `analyses`; `updated_at` also changes on unrelated actions (rename, share-link creation), so this formula would overstate TTFI for any analysis touched after completion. **Recommended fix**: add `analyses.completed_at`, set once, alongside the existing `status` transition in `analysis_engine.py:_persist_results` |
| Analysis Success Rate | % of analyses reaching `completed` vs. `failed` | `COUNT(status='completed') / COUNT(status IN ('completed','failed'))` | ✅ Yes — `analyses.status` |
| Data Quality Pass Rate | % of analyses with quality score ≥ 70 | `COUNT(*) WHERE (metadata->'data_quality'->>'score')::int >= 70 / COUNT(*)` | ✅ Yes — score lives inside `analyses.metadata` (JSONB); a Postgres JSON-path query works today, though a generated column would be faster at scale |
| Support Ticket Rate | Tickets per 100 active users/week | N/A | ❌ No — no support-system integration; would require joining an external system (Zendesk/Intercom) on `users.email` |

### 2.4 Trend metrics

| Metric | Definition | Computable today? |
|---|---|---|
| Weekly Active Analyses, 12-week trend | WAA computed per ISO week, trailing 12 weeks | ✅ — `DATE_TRUNC('week', analyses.created_at)` |
| MRR growth trend | MRR computed per calendar month | ⚠️ Same plan-price gap as §2.2 |
| Signup trend | New `users` per week | ✅ — `users.created_at` |

### 2.5 Forecast metrics

The product's own `analytics/forecasting.py` approach (linear trend extrapolation over a monthly series, confidence from history-length + residual noise — `docs/analytics/03_Analytics_Glossary.md §4`) generalizes directly to business metrics, not just customer data:

| Metric | Series | Computable today? |
|---|---|---|
| Forecasted Weekly Active Analyses (next 4 weeks) | `WAA` per week, same OLS approach already implemented | ✅ — same algorithm, different input table (`analyses` instead of an uploaded file's DuckDB table) |
| Forecasted MRR | Monthly MRR series | ⚠️ Blocked on the same plan-price gap as §2.2 |

### 2.6 Conversion metrics

| Metric | Definition | Formula sketch | Computable today? |
|---|---|---|---|
| Activation Rate | % of signups completing a first analysis within 24h | `COUNT(users u WHERE EXISTS (SELECT 1 FROM analyses a WHERE a.user_id=u.id AND a.created_at <= u.created_at + interval '24 hours')) / COUNT(users)` | ✅ Yes — both timestamps exist |
| Trial → Paid Conversion | See §2.2 | — | ❌ No trial state modeled |

### 2.7 Usage metrics

| Metric | Definition | Formula sketch | Computable today? |
|---|---|---|---|
| Analyses per active user | `COUNT(analyses) / COUNT(DISTINCT user_id)` in period | ✅ | ✅ |
| Chat Engagement Rate | % of analyses with ≥1 chat message | `COUNT(DISTINCT a.id WHERE EXISTS chat_sessions→chat_messages) / COUNT(a.id)` | ✅ — full join path exists (`analyses → chat_sessions → chat_messages`) |
| Dashboard Share Rate | % of analyses with an active share link | `COUNT(*) WHERE share_token IS NOT NULL / COUNT(*)` | ✅ Yes — `analyses.share_token` |
| Export Rate | % of analyses resulting in a PDF/Excel export | N/A | ❌ No — `GET /analyses/{id}/export/pdf` and `/export/excel` (`analyses.py`) generate files on demand and **persist no export event**. Recommended fix: log an `export_events(analysis_id, format, exported_at)` row, or at minimum bump a counter column, inside `export_service.py` |

### 2.8 Retention metrics

| Metric | Definition | Formula sketch | Computable today? |
|---|---|---|---|
| Week-4 Retention | % of a signup cohort with ≥1 analysis in week 4 post-signup | Cohort-by-week self-join on `users.created_at` vs. `analyses.created_at` | ✅ Yes — same two tables as Activation Rate, one more join condition |
| Monthly cohort retention curve | Standard cohort triangle (signup month × activity month) | Cohort SQL over `users`/`analyses` | ✅ Yes |

### 2.9 Revenue metrics

| Metric | Definition | Formula sketch | Computable today? |
|---|---|---|---|
| ARPU | `MRR / paying users` | — | ⚠️ Blocked on plan-price gap |
| LTV:CAC | Lifetime value ÷ customer acquisition cost | — | ❌ No — CAC requires marketing-spend data that doesn't exist anywhere in this schema; out of scope for this product's data model entirely, would need a separate marketing-attribution source |

### 2.10 Summary — what's blocking a real executive dashboard today

Three schema gaps recur across the list above and would be the actual first engineering ticket, in priority order:

1. **No plan→price mapping** (blocks MRR, ARPU, MRR forecast, MRR trend) — smallest fix, a static config lookup, not even a migration.
2. **No `analyses.completed_at`** (blocks accurate TTFI) — one migration, one line in `_persist_results`.
3. **No export/trial/NPS event tables** (blocks Export Rate, Trial Conversion, NPS) — genuinely new features, not queries against data that already exists.

This is the value of specifying a dashboard against the real schema instead of describing it in the abstract: it turns "what KPIs should we track" into a concrete, estimable backlog.
