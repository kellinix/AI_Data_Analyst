# Confidence calibration — benchmark results

Generated 2026-09-11T14:31:07Z · benchmark `2026-09-11.1` · 48 datasets · analysis model `gpt-4o` · judge `gpt-4o`

Produced by `python -m evals.calibration.run_eval` — do not edit by hand. Method and caveats: `docs/analytics/10_Confidence_Calibration.md`.

## Per source

| Source | n | Datasets | Confidence shown | Hit rate (95% CI) | Brier shown | Brier recalibrated (LOO) | Recalibrated confidence |
|---|---|---|---|---|---|---|---|
| `ai:high` | 39 | 23 | 0.85 | 0.49 (0.34–0.64) | 0.382 | 0.267 | 0.49 |
| `ai:medium` | 37 | 24 | 0.70 | 0.54 (0.38–0.69) | 0.274 | 0.262 | 0.54 |
| `rule:anomaly` | 41 | 41 | 0.78 | 0.46 (0.32–0.61) | 0.349 | 0.261 | 0.47 |
| `rule:data_quality` | 28 | 28 | 0.90 | 0.50 (0.33–0.67) | 0.410 | 0.268 | 0.50 |
| `rule:forecast` | 74 | 32 | 0.83 | 0.73 (0.62–0.82) | 0.211 | 0.208 | 0.72 |

All scored recommendations: n=219, Brier 0.3032, ECE 0.2367. Not scored (unverifiable / no ground truth): {'ai:high': 5, 'ai:medium': 1, 'rule:forecast': 11}.

## Reliability (all sources, confidence as shown)

| Confidence bin | n | Mean confidence | Hit rate |
|---|---|---|---|
| 0.6-0.8 | 82 | 0.74 | 0.51 |
| 0.8-1.0 | 137 | 0.85 | 0.61 |

## Recall on planted findings

| Finding | Planted in | Found by rules | Found by AI |
|---|---|---|---|
| anomaly | 24 | 19 | 11 |
| data_defect | 16 | 14 | 8 |

## Judge check

The LLM judge also graded every rule-based recommendation, where deterministic labels exist. Agreement with those labels:

| Rule source | Agree / n | Rate |
|---|---|---|
| all | 122/135 | 0.9037 |
| rule:anomaly | 39/39 | 1.0 |
| rule:data_quality | 13/26 | 0.5 |
| rule:forecast | 70/70 | 1.0 |

Datasets with no AI recommendations (AI call failed; deterministic fallback used): 19 — 001_online_marketplace_weekly, 002_b2b_software_weekly, 008_outdoor_retail_weekly, 009_online_marketplace_weekly, 011_hotel_group_weekly, 016_outdoor_retail_weekly, 017_online_marketplace_weekly, 025_online_marketplace_weekly, 026_b2b_software_weekly, 032_outdoor_retail_weekly, 033_online_marketplace_weekly, 035_hotel_group_weekly, 038_b2b_software_monthly, 040_outdoor_retail_weekly, 041_online_marketplace_weekly, 042_b2b_software_weekly, 043_hotel_group_weekly, 044_outdoor_retail_monthly, 046_b2b_software_monthly.

## By scenario

| Slice | Source | n | Confidence shown | Hit rate |
|---|---|---|---|---|
| grain=monthly | `ai:high` | 27 | 0.85 | 0.48 |
| grain=monthly | `ai:medium` | 28 | 0.70 | 0.54 |
| grain=monthly | `rule:anomaly` | 20 | 0.78 | 0.65 |
| grain=monthly | `rule:data_quality` | 15 | 0.90 | 0.53 |
| grain=monthly | `rule:forecast` | 23 | 0.83 | 0.65 |
| grain=weekly | `ai:high` | 12 | 0.85 | 0.50 |
| grain=weekly | `ai:medium` | 9 | 0.70 | 0.56 |
| grain=weekly | `rule:anomaly` | 21 | 0.78 | 0.29 |
| grain=weekly | `rule:data_quality` | 13 | 0.90 | 0.46 |
| grain=weekly | `rule:forecast` | 51 | 0.83 | 0.76 |
| noise=high | `ai:high` | 27 | 0.85 | 0.48 |
| noise=high | `ai:medium` | 19 | 0.70 | 0.53 |
| noise=high | `rule:anomaly` | 20 | 0.78 | 0.45 |
| noise=high | `rule:data_quality` | 16 | 0.90 | 0.50 |
| noise=high | `rule:forecast` | 32 | 0.83 | 0.75 |
| noise=low | `ai:high` | 12 | 0.85 | 0.50 |
| noise=low | `ai:medium` | 18 | 0.70 | 0.56 |
| noise=low | `rule:anomaly` | 21 | 0.78 | 0.48 |
| noise=low | `rule:data_quality` | 12 | 0.90 | 0.50 |
| noise=low | `rule:forecast` | 42 | 0.83 | 0.71 |
| optional_sparse_column=False | `ai:high` | 17 | 0.85 | 0.82 |
| optional_sparse_column=False | `ai:medium` | 21 | 0.70 | 0.48 |
| optional_sparse_column=False | `rule:anomaly` | 20 | 0.78 | 0.45 |
| optional_sparse_column=False | `rule:data_quality` | 8 | 0.90 | 1.00 |
| optional_sparse_column=False | `rule:forecast` | 33 | 0.83 | 0.76 |
| optional_sparse_column=True | `ai:high` | 22 | 0.85 | 0.23 |
| optional_sparse_column=True | `ai:medium` | 16 | 0.70 | 0.62 |
| optional_sparse_column=True | `rule:anomaly` | 21 | 0.78 | 0.48 |
| optional_sparse_column=True | `rule:data_quality` | 20 | 0.90 | 0.30 |
| optional_sparse_column=True | `rule:forecast` | 41 | 0.83 | 0.71 |
| planted_anomaly=False | `ai:high` | 12 | 0.85 | 0.58 |
| planted_anomaly=False | `ai:medium` | 18 | 0.70 | 0.33 |
| planted_anomaly=False | `rule:anomaly` | 21 | 0.78 | 0.00 |
| planted_anomaly=False | `rule:data_quality` | 16 | 0.90 | 0.44 |
| planted_anomaly=False | `rule:forecast` | 39 | 0.84 | 0.72 |
| planted_anomaly=True | `ai:high` | 27 | 0.85 | 0.44 |
| planted_anomaly=True | `ai:medium` | 19 | 0.70 | 0.74 |
| planted_anomaly=True | `rule:anomaly` | 20 | 0.78 | 0.95 |
| planted_anomaly=True | `rule:data_quality` | 12 | 0.90 | 0.58 |
| planted_anomaly=True | `rule:forecast` | 35 | 0.82 | 0.74 |
