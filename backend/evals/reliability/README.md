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
