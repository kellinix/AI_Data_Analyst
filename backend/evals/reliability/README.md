# Source reliability release gate

Run from `backend`: `python -m evals.reliability.run_eval`.
The CLI emits a JSON summary and exits nonzero on failure. The same cases run
automatically in the existing pytest CI job (`test_reliability_benchmark.py`).

Eight synthetic datasets cover missing revenue, refunds, repeated transactions,
leading-zero IDs/postal codes, distinct product codes, ratings, optional notes,
and published survey percentages. Each also runs with reversed source rows.
Checks exercise the real upload defaults, CSV parser, cleaned Parquet file,
and analysis pipeline. They verify recorded values, gaps, record counts,
revenue totals, identifier exclusions, rating aggregation, survey scope, and
the absence of forecasts without a time series.

AI and semantic display generation are disabled: this gate cannot certify AI
wording, authentication, device behavior, export layout, or hosting readiness.
Existing format, chart, forecast, and API tests complement these small fixtures.
Previously saved reports require re-analysis to benefit from import changes;
this gate does not rewrite customer reports.

For database integration tests, run
`docker compose exec -T backend python scripts/test_isolated_database.py`
from the repository root. It creates a randomly named test database, migrates
and tests only that database, and removes it afterward. The configured role
must have database creation permission. It never migrates the application DB.

## Public Kaggle file check

Download `index_1.csv` from Kaggle's `ihelon/coffee-sales` (CC0) and
`Supermarket Sales Data.csv` from `pimmadachirawat/supermarket-sales`
(Apache 2.0) into an ignored local directory. From `backend`, run:

```powershell
python -m evals.reliability.run_kaggle_eval --coffee "../tmp/kaggle/coffee/index_1.csv" --supermarket "../tmp/kaggle/supermarket/Supermarket Sales Data.csv"
```

This additional check derives row counts, measure totals, and category totals
directly from each source CSV, then compares the default cleaned analysis,
headline KPI, and category chart. It exits nonzero on disagreement. Source
files are deliberately not committed. It cannot certify AI prose, forecast
accuracy, web/mobile upload, export, authentication, or hosting behavior.
