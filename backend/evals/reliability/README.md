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

This check derives row counts, measure totals, and category totals directly
from each source CSV. It compares the default cleaned analysis, headline KPI,
and category chart, then builds the same PDF and Excel reports used by the
export routes. It checks PDF chart labels and drawing data, Excel chart counts,
and the Excel category values against the source. Reports are written to the
ignored `tmp/kaggle/eval_artifacts/` directory; render and inspect their PDF
pages before a release. Use `--with-ai` for a local AI-backed wording pass.
Source files are deliberately not committed. This does not exercise the HTTP
upload route, database persistence, authentication, mobile UI, or hosting.

## Local upload-to-export check

With Docker Desktop running and the development backend container healthy, copy
the two downloaded CSVs into that container and run the disposable-database
smoke test from the repository root:

```powershell
docker cp "tmp/kaggle/coffee/index_1.csv" "ai_dashboard_backend:/tmp/zephyr_coffee_source.csv"
docker cp "tmp/kaggle/supermarket/Supermarket Sales Data.csv" "ai_dashboard_backend:/tmp/zephyr_supermarket_source.csv"
docker compose exec -T backend python scripts/test_local_upload_export.py /tmp/zephyr_coffee_source.csv /tmp/zephyr_supermarket_source.csv
```

The script creates a temporary PostgreSQL database, applies migrations, sends
both files through the upload and analysis ASGI routes, runs the persisted
analysis pipeline, requests both export routes, checks source totals and chart
presence, then drops the database. It replaces authentication and the Celery
queue in the test process and uses offline narrative generation, so it does
not certify Supabase sign-in, queue delivery, AI wording, or the browser UI.
