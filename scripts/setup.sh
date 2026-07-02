#!/usr/bin/env bash
# ============================================================
# Development environment setup script
# ============================================================
set -euo pipefail

echo "🚀 Setting up AI Dashboard Generator development environment"

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || command -v docker >/dev/null 2>&1 || { echo "❌ Docker Compose is required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js 20+ is required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3.12+ is required"; exit 1; }

echo "✅ Prerequisites satisfied"

# Copy .env if not exists
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 Copied .env.example → .env (fill in your API keys)"
fi

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
cd ..

# Install backend dependencies
echo "🐍 Setting up Python virtual environment..."
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Start Docker services
echo "🐳 Starting Docker services..."
docker compose up -d postgres redis

# Wait for PostgreSQL
echo "⏳ Waiting for PostgreSQL..."
until docker compose exec postgres pg_isready -U ai_dashboard_user >/dev/null 2>&1; do
  sleep 1
done
echo "✅ PostgreSQL ready"

# Run migrations
echo "🗄️  Running database migrations..."
cd backend && .venv/bin/python -m alembic upgrade head && cd ..

echo ""
echo "✅ Setup complete!"
echo ""
echo "Start development:"
echo "  make dev"
echo ""
echo "Or individually:"
echo "  Frontend:  cd frontend && npm run dev"
echo "  Backend:   cd backend && uvicorn app.main:app --reload"
