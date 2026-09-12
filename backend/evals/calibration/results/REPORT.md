# Confidence calibration — benchmark results

Generated 2026-09-11T18:07:33Z · benchmark `2026-09-11.1` · 48 datasets · analysis model `None` · judge `None`

Produced by `python -m evals.calibration.run_eval` — do not edit by hand. Method and caveats: `docs/analytics/10_Confidence_Calibration.md`.

## Per source

| Source | n | Datasets | Confidence shown | Hit rate (95% CI) | Brier shown | Brier recalibrated (LOO) | Recalibrated confidence |
|---|---|---|---|---|---|---|---|
| `rule:anomaly` | 47 | 47 | 0.78 | 0.49 (0.35–0.63) | 0.334 | 0.260 | 0.49 |
| `rule:data_quality` | 33 | 33 | 0.90 | 0.48 (0.33–0.65) | 0.422 | 0.265 | 0.49 |
| `rule:forecast` | 98 | 39 | 0.83 | 0.72 (0.63–0.80) | 0.212 | 0.209 | 0.72 |

All scored recommendations: n=178, Brier 0.2831, ECE 0.2124. Not scored (unverifiable / no ground truth): {'rule:forecast': 12}.

## Reliability (all sources, confidence as shown)

| Confidence bin | n | Mean confidence | Hit rate |
|---|---|---|---|
| 0.6-0.8 | 54 | 0.78 | 0.52 |
| 0.8-1.0 | 124 | 0.85 | 0.66 |

## Recall on planted findings

| Finding | Planted in | Found by rules | Found by AI |
|---|---|---|---|
| anomaly | 24 | 23 | — (offline run) |
| data_defect | 16 | 16 | — (offline run) |

## Judge check

Not run: this was an offline (`--no-ai`) run, so there are no AI recommendations and no judge. Rule-based recommendations are labeled deterministically.

## By scenario

| Slice | Source | n | Confidence shown | Hit rate |
|---|---|---|---|---|
| grain=monthly | `rule:anomaly` | 24 | 0.78 | 0.67 |
| grain=monthly | `rule:data_quality` | 17 | 0.90 | 0.47 |
| grain=monthly | `rule:forecast` | 40 | 0.82 | 0.65 |
| grain=weekly | `rule:anomaly` | 23 | 0.78 | 0.30 |
| grain=weekly | `rule:data_quality` | 16 | 0.90 | 0.50 |
| grain=weekly | `rule:forecast` | 58 | 0.84 | 0.78 |
| noise=high | `rule:anomaly` | 23 | 0.78 | 0.52 |
| noise=high | `rule:data_quality` | 20 | 0.90 | 0.45 |
| noise=high | `rule:forecast` | 44 | 0.83 | 0.68 |
| noise=low | `rule:anomaly` | 24 | 0.78 | 0.46 |
| noise=low | `rule:data_quality` | 13 | 0.90 | 0.54 |
| noise=low | `rule:forecast` | 54 | 0.83 | 0.76 |
| optional_sparse_column=False | `rule:anomaly` | 24 | 0.78 | 0.46 |
| optional_sparse_column=False | `rule:data_quality` | 9 | 0.90 | 1.00 |
| optional_sparse_column=False | `rule:forecast` | 50 | 0.83 | 0.78 |
| optional_sparse_column=True | `rule:anomaly` | 23 | 0.78 | 0.52 |
| optional_sparse_column=True | `rule:data_quality` | 24 | 0.90 | 0.29 |
| optional_sparse_column=True | `rule:forecast` | 48 | 0.83 | 0.67 |
| planted_anomaly=False | `rule:anomaly` | 23 | 0.78 | 0.00 |
| planted_anomaly=False | `rule:data_quality` | 18 | 0.90 | 0.50 |
| planted_anomaly=False | `rule:forecast` | 48 | 0.84 | 0.75 |
| planted_anomaly=True | `rule:anomaly` | 24 | 0.78 | 0.96 |
| planted_anomaly=True | `rule:data_quality` | 15 | 0.90 | 0.47 |
| planted_anomaly=True | `rule:forecast` | 50 | 0.82 | 0.70 |
