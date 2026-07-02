# Zephyr — AI Dashboard Generator

**Users should never build dashboards.**

Upload any business file (CSV, Excel, JSON, Parquet, TSV) and get a fully rendered executive dashboard — KPIs, charts, AI insights, recommendations, and interactive chat — in seconds.

---

## Architecture

```
Frontend (Next.js 15)  →  Backend (FastAPI)  →  PostgreSQL
        ↓                        ↓                   ↑
  Supabase Auth            Celery Worker         Alembic
                                ↓
                        DuckDB (analytics)
                                ↓
                         OpenAI GPT-4o
```

| Layer     | Technology                             |
|-----------|----------------------------------------|
| Frontend  | Next.js 15 · React 19 · TypeScript     |
| Styling   | Tailwind CSS v4 · Framer Motion        |
| State     | TanStack Query 5 · Zustand 5           |
| Charts    | Apache ECharts                         |
| Auth      | Supabase Auth (SSR)                    |
| Backend   | FastAPI 0.115 · Python 3.12            |
| ORM       | SQLAlchemy 2.0 async + asyncpg         |
| Queue     | Celery 5 · Redis 7                     |
| Analytics | DuckDB 1.2 · Polars · Pandas           |
| AI        | OpenAI GPT-4o                          |
| Database  | PostgreSQL 16                          |
| Container | Docker · Docker Compose                |

---

## Quick Start

### Prerequisites

- Docker 24+ and Docker Compose
- Node.js 20+
- Python 3.12+

### 1. Clone and configure

```bash
git clone https://github.com/your-org/ai-dashboard-generator.git
cd ai-dashboard-generator
cp .env.example .env
```

Fill in `.env`:
- `OPENAI_API_KEY` — from https://platform.openai.com
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` — from your Supabase project

### 2. Start everything

```bash
make setup   # installs deps, runs migrations
make dev     # starts all services
```

App is available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/v1
- API Docs: http://localhost:8000/api/docs

### 3. Verify health

```bash
bash scripts/health_check.sh
```

---

## Development Commands

```bash
make dev          # Start all services (Docker + hot reload)
make test         # Run all tests
make lint         # Run ruff + mypy + eslint
make migrate      # Run pending DB migrations
make seed         # Seed DB with demo data
make logs         # Tail all service logs
make clean        # Stop all containers
```

---

## Project Structure

```
.
├── frontend/           # Next.js application
│   └── src/
│       ├── app/        # App Router pages
│       ├── components/ # UI components
│       ├── hooks/      # React Query hooks
│       ├── lib/        # API client, Supabase, utils
│       ├── stores/     # Zustand stores
│       └── types/      # TypeScript types
│
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── api/        # Route handlers
│   │   ├── analytics/  # Statistics, KPI, chart selection
│   │   ├── core/       # Config, logging, security
│   │   ├── db/         # SQLAlchemy session, models
│   │   ├── models/     # Database models
│   │   ├── schemas/    # Pydantic schemas
│   │   ├── services/   # Business logic
│   │   └── workers/    # Celery tasks
│   ├── alembic/        # Database migrations
│   └── tests/          # Test suite
│
├── docker/             # Dockerfiles + nginx config
├── scripts/            # Setup, seed, health check
└── .github/workflows/  # CI/CD pipelines
```

---

## Analysis Pipeline

```
Upload file
    ↓
Profile file (Polars) → row count, column types, sample values
    ↓
Load into DuckDB (in-memory columnar store)
    ↓
StatisticsEngine → numeric stats, categorical stats, correlations, data quality
    ↓
KPI Detector → identify revenue, profit, orders, customers, etc.
    ↓
Chart Selector → time series, bar, donut, scatter
    ↓
Populate chart data from DuckDB
    ↓
OpenAI GPT-4o → executive summary, AI insights, recommendations
    ↓
Persist to PostgreSQL → insights, charts, summary
    ↓
Frontend renders dashboard
```

The LLM receives only pre-computed statistics — it never touches raw data. This ensures:
- Speed (statistics are fast; LLM only interprets)
- Accuracy (numbers are exact, not hallucinated)
- Security (raw data never leaves the server)

---

## Environment Variables

See `.env.example` for all available options with descriptions.

Required for production:
| Variable | Description |
|---|---|
| `SECRET_KEY` | 32+ char random secret |
| `OPENAI_API_KEY` | OpenAI API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret |
| `POSTGRES_*` | PostgreSQL connection details |
| `REDIS_HOST` | Redis host |

---

## Deployment

### Vercel + Railway (recommended)

1. Deploy frontend to Vercel (connect GitHub repo)
2. Deploy backend + worker + Redis + Postgres to Railway
3. Set environment variables in both platforms

### Docker (self-hosted)

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## License

MIT — see [LICENSE](LICENSE)
