# Zephyr staging Supabase project

Project URL: `https://fpeeofqwylhxyglttlrg.supabase.co`

The staging environment template is [`.env.staging.example`](../.env.staging.example).
It uses a separate Compose Postgres database for Zephyr's application data;
the Supabase project supplies authentication. Its database connection string
shown in the dashboard is not an application database credential until a
password and architecture choice have been supplied.

The new project is healthy. Its Auth Site URL is
`https://zephyr-web-staging.up.railway.app`, and its only allowed redirect is
`https://zephyr-web-staging.up.railway.app/auth/callback` (checked
27 October 2026). Email sign-in is enabled; Google sign-in is still disabled.
Zephyr's current local web, mobile and
backend `.env` files still point to the earlier project. Do not mix the earlier
project's publishable or service-role keys with this URL.

For this staging deployment, use this project's browser-safe legacy `anon` key
for `NEXT_PUBLIC_SUPABASE_ANON_KEY` and `SUPABASE_ANON_KEY`. The backend's
account deletion endpoint currently uses the legacy `service_role` JWT as a
Bearer token, so put this project's service-role key only in the backend's
private environment. Never put that key in a `NEXT_PUBLIC_` or `EXPO_PUBLIC_`
variable. New Supabase publishable and secret keys need a separate compatibility
check before replacing these legacy values.

The staging web Auth URL and callback are configured. If testing the native app
against this project, also allow `zephyr://auth/callback`.
Google sign-in needs a Google OAuth client configured for this new Supabase
project; enabling the provider requires its own client ID and secret. Email
confirmation is currently enabled.

Build the web image with `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY` set to staging
values. These are embedded at build time; changing the running container's
environment cannot replace them. Keep the existing local configuration intact.

Staging still needs a successful Railway deployment and an end-to-end sign-in,
upload, analysis and export check before it can serve as a release gate.

## Railway staging layout

Railway assigned `zephyr-web-staging.up.railway.app` to the Next.js website and
`zephyr-backend-staging.up.railway.app` to the backend during the first deployment.
The web build uses Railway reference variables so its embedded URLs use these
domains:

```text
NEXT_PUBLIC_APP_URL=https://${{RAILWAY_PUBLIC_DOMAIN}}
NEXT_PUBLIC_API_URL=https://${{zephyr-backend.RAILWAY_PUBLIC_DOMAIN}}
```

The backend's `BACKEND_CORS_ORIGINS` and `FRONTEND_URL` reference
`https://${{zephyr-web.RAILWAY_PUBLIC_DOMAIN}}`. Confirm the resolved URLs in
Railway after deployment, then set the exact web URL and callback in Supabase
Auth. Railway documents [reference variables](https://docs.railway.com/variables/reference)
and makes system variables available to [Dockerfile builds](https://docs.railway.com/builds/dockerfiles).

The private Railway project is `Zephyr Staging`, environment `staging`:
https://railway.com/project/8ca3a5c8-32a4-4f08-b18e-b5153f490f91?environmentId=bbc12aea-ffcb-4ebd-aad0-51da55113de1.
Postgres and Redis are online. The `zephyr-backend` and `zephyr-web` services
are connected to `kellinix/AI_Data_Analyst` on the isolated
`staging/railway-2026-10-26` branch. Their staging Supabase credentials and a
separate `OPENAI_API_KEY` are configured in Railway. The first deployment on
27 October 2026 left both services offline: Railway rejected the web build's
Next.js 15.3.3 security advisories, and the backend failed to start because
Pydantic Settings tried to decode a plain CORS URL as JSON. The approved second
deployment, commit `0d37bbb`, brought the web service online; its `/api/health`
returns `ok`. The backend still failed: Celery Beat tried to write its schedule
in the read-only app directory. The staging launcher now stores that schedule
on the writable upload volume. Verify backend health after deploying this fix
before end-to-end testing. The backend
has a staged persistent volume mounted at `/app/uploads`. Railway's GitHub app
has access to only the Zephyr repository.

The compatible frontend dependency updates leave two high-severity npm audit
findings: PostCSS bundled by Next.js 15 and Zod 3. Addressing them requires
major-version upgrades and regression testing before a production release.

Use a single backend service with root directory `/backend`. Configure its
Dockerfile builder, pre-deploy command `alembic upgrade head`, start command
`python scripts/run_railway_staging.py`, and health path `/api/v1/health` in
Railway's service settings. Railway no longer accepts config-as-code for new
services, so `railway.json` files are not used. The staging command runs
Gunicorn, one Celery worker and Celery Beat in the same service, so uploaded
files are visible to the worker. Keep its replica count at one. The website
uses root directory `/frontend`, Dockerfile builder, and health path
`/api/health` as a separate Railway service. Set `UPLOAD_DIR=/app/uploads`,
`DATABASE_URL`, `REDIS_URL` and the
Celery Redis URLs in the backend service's private environment. The backend
accepts Railway Postgres's standard `DATABASE_URL` and converts it to the
async driver for API requests. Attach the
volume before uploading test data. Railway mounts volumes as root, so set
`RAILWAY_RUN_UID=0` on the backend service while it uses this volume. The staging
launcher fixes the mount's ownership and drops to `appuser` before starting the
API and workers. This setup requires enough memory for the API plus DuckDB
analysis and is not assumed to fit a free 512 MB service.

Railway restored Trial builds and marked its October outage resolved on
23 October 2026. The remaining steps are confirming backend health, configuring Google
sign-in for this separate Supabase project if it is part of staging acceptance,
and running end-to-end checks. Do not copy production credentials
into staging. Railway recommends rotating any sensitive variables stored
during the October 21 incident; this new workspace had none.

Railway volumes are scoped to a service, so separate API and worker services
cannot safely share Zephyr's current local file paths. Scaling those processes
independently requires a shared object storage implementation. This is a
private staging topology, not the final production scaling plan.
