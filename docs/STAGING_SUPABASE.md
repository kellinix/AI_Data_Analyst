# Zephyr staging Supabase project

Project URL: `https://fpeeofqwylhxyglttlrg.supabase.co`

The staging environment template is [`.env.staging.example`](../.env.staging.example).
It uses a separate Compose Postgres database for Zephyr's application data;
the Supabase project supplies authentication. Its database connection string
shown in the dashboard is not an application database credential until a
password and architecture choice have been supplied.

The new project is healthy but currently has no users, Google sign-in is
disabled, its Auth Site URL is `http://localhost:3000`, and its redirect allow
list is empty (checked 22 October 2026). Zephyr's current local web, mobile and
backend `.env` files still point to the earlier project. Do not mix the earlier
project's publishable or service-role keys with this URL.

For a separate staging deployment, use this project's publishable key for
`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_ANON_KEY`, and
`EXPO_PUBLIC_SUPABASE_ANON_KEY` only where the corresponding client is deployed.
Put its service-role key only in the backend's private environment. Never put
that key in a `NEXT_PUBLIC_` or `EXPO_PUBLIC_` variable.

Before testing sign-in, set the Auth Site URL to the staging HTTPS website and
allow the exact web callback `https://<staging-host>/auth/callback`. If testing
the native app against this project, also allow `zephyr://auth/callback`.
Google sign-in needs a Google OAuth client configured for this new Supabase
project; enabling the provider requires its own client ID and secret. Email
confirmation is currently enabled.

Build the web image with `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY` set to staging
values. These are embedded at build time; changing the running container's
environment cannot replace them. Keep the existing local configuration intact.

Staging still needs its Railway HTTPS domains, staging credentials, and an
end-to-end sign-in, upload, analysis and export check before it can serve as a
release gate.

## Railway staging layout

Use Railway's generated HTTPS domain for the Next.js website and another for
the backend. Build the frontend with those final domains because `NEXT_PUBLIC_`
settings are embedded at build time. Set both domains in Supabase Auth only
after Railway has assigned them.

The private Railway project is `Zephyr Staging`, environment `staging`:
https://railway.com/project/8ca3a5c8-32a4-4f08-b18e-b5153f490f91?environmentId=bbc12aea-ffcb-4ebd-aad0-51da55113de1.
Postgres and Redis are online. The `zephyr-backend` and `zephyr-web` services
are staged and connected to `kellinix/AI_Data_Analyst` on the isolated
`staging/railway-2026-10-26` branch. They do not yet have environment variables
or domains; do not deploy them until those settings are complete. The backend
has a staged persistent volume mounted at `/app/uploads`. Railway's GitHub app
has access to only the Zephyr repository.

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
23 October 2026. The remaining deployment steps are configuring staging-only
credentials, assigning HTTPS domains,
and running end-to-end checks. Do not copy production credentials
into staging. Railway recommends rotating any sensitive variables stored
during the October 21 incident; this new workspace had none.

Railway volumes are scoped to a service, so separate API and worker services
cannot safely share Zephyr's current local file paths. Scaling those processes
independently requires a shared object storage implementation. This is a
private staging topology, not the final production scaling plan.
